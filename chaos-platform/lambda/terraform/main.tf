terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.0" }
  }
}

locals {
  lambda_src_base = "${path.module}/.."   # root of lambda/ directory
  common_env = {
    DYNAMODB_TABLE       = var.dynamodb_table_name
    SLACK_SNS_TOPIC_ARN  = aws_sns_topic.chaos_notifications.arn
    LOG_LEVEL            = var.log_level
  }
}

# ── Lambda source packaging ───────────────────────────────────────────────────
# archive_file zips the function directory at plan time.
# The zip is rebuilt automatically whenever any source file changes.

data "archive_file" "report_generator" {
  type        = "zip"
  source_dir  = "${local.lambda_src_base}/report-generator"
  output_path = "${path.module}/.build/report-generator.zip"
  excludes    = ["tests", "__pycache__", "*.pyc", ".pytest_cache"]
}

data "archive_file" "slack_notifier" {
  type        = "zip"
  source_dir  = "${local.lambda_src_base}/slack-notifier"
  output_path = "${path.module}/.build/slack-notifier.zip"
  excludes    = ["tests", "__pycache__", "*.pyc"]
}

data "archive_file" "experiment_scheduler" {
  type        = "zip"
  source_dir  = "${local.lambda_src_base}/experiment-scheduler"
  output_path = "${path.module}/.build/experiment-scheduler.zip"
  excludes    = ["tests", "__pycache__", "*.pyc"]
}

# ── Lambda: report-generator ──────────────────────────────────────────────────
resource "aws_lambda_function" "report_generator" {
  function_name = "${var.project_name}-report-generator"
  description   = "Generates PDF reports from experiment results and uploads to S3"

  filename         = data.archive_file.report_generator.output_path
  source_code_hash = data.archive_file.report_generator.output_base64sha256

  runtime = "python3.11"
  handler = "handler.lambda_handler"

  role    = aws_iam_role.report_generator.arn
  timeout = 300   # 5 min — WeasyPrint PDF rendering can be slow for large reports
  memory_size = 1024

  # WeasyPrint requires native libraries (libpango, libcairo, libgdk-pixbuf)
  # packaged as a Lambda layer built for Amazon Linux 2023
  layers = [var.weasyprint_layer_arn]

  environment {
    variables = merge(local.common_env, {
      REPORTS_BUCKET          = var.reports_bucket_name
      SLACK_WEBHOOK_SSM_PARAM = var.slack_webhook_ssm_param
    })
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  tracing_config {
    mode = "Active"   # X-Ray tracing
  }

  tags = var.tags
}

# ── Lambda: slack-notifier ────────────────────────────────────────────────────
resource "aws_lambda_function" "slack_notifier" {
  function_name = "${var.project_name}-slack-notifier"
  description   = "Routes SNS chaos events to appropriate Slack channels"

  filename         = data.archive_file.slack_notifier.output_path
  source_code_hash = data.archive_file.slack_notifier.output_base64sha256

  runtime     = "python3.11"
  handler     = "handler.lambda_handler"
  role        = aws_iam_role.slack_notifier.arn
  timeout     = 60
  memory_size = 256

  environment {
    variables = merge(local.common_env, {
      SLACK_WEBHOOK_SSM_PARAM = var.slack_webhook_ssm_param
      CHANNEL_EXPERIMENTS     = var.slack_channel_experiments
      CHANNEL_ALERTS          = var.slack_channel_alerts
      CHANNEL_REPORTS         = var.slack_channel_reports
    })
  }

  tracing_config { mode = "Active" }
  tags = var.tags
}

# ── Lambda: experiment-scheduler ─────────────────────────────────────────────
resource "aws_lambda_function" "experiment_scheduler" {
  function_name = "${var.project_name}-experiment-scheduler"
  description   = "Triggers scheduled chaos experiments via the Chaos Engine REST API"

  filename         = data.archive_file.experiment_scheduler.output_path
  source_code_hash = data.archive_file.experiment_scheduler.output_base64sha256

  runtime     = "python3.11"
  handler     = "handler.lambda_handler"
  role        = aws_iam_role.experiment_scheduler.arn
  timeout     = 60
  memory_size = 256

  environment {
    variables = merge(local.common_env, {
      CHAOS_ENGINE_URL = var.chaos_engine_url
    })
  }

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  tracing_config { mode = "Active" }
  tags = var.tags
}

# ── Security Group for VPC Lambdas ────────────────────────────────────────────
resource "aws_security_group" "lambda" {
  name        = "${var.project_name}-lambda-sg"
  description = "Security group for Lambda functions in VPC"
  vpc_id      = var.vpc_id

  # Allow all outbound within VPC (to reach chaos engine and DynamoDB VPC endpoint)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
    description = "Allow all outbound within VPC"
  }

  # Allow HTTPS outbound to AWS services (SSM, S3, DynamoDB via VPC endpoints or public)
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow HTTPS outbound to AWS services"
  }

  tags = merge(var.tags, { Name = "${var.project_name}-lambda-sg" })
}

# ── SNS Topic: chaos-notifications ───────────────────────────────────────────
# (detailed configuration in eventbridge.tf, defined here for reference by other resources)
resource "aws_sns_topic" "chaos_notifications" {
  name = "${var.project_name}-chaos-notifications"
  tags = var.tags
}

# ── CloudWatch Log Groups (explicit to set retention) ─────────────────────────
resource "aws_cloudwatch_log_group" "report_generator" {
  name              = "/aws/lambda/${aws_lambda_function.report_generator.function_name}"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "slack_notifier" {
  name              = "/aws/lambda/${aws_lambda_function.slack_notifier.function_name}"
  retention_in_days = 30
  tags              = var.tags
}

resource "aws_cloudwatch_log_group" "experiment_scheduler" {
  name              = "/aws/lambda/${aws_lambda_function.experiment_scheduler.function_name}"
  retention_in_days = 30
  tags              = var.tags
}
