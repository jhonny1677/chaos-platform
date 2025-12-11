data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.name
}

# ── Common Lambda assume-role policy ──────────────────────────────────────────
data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# ── Common Lambda VPC/logging policy (attached to all three roles) ─────────────
resource "aws_iam_policy" "lambda_basic" {
  name        = "${var.project_name}-lambda-basic"
  description = "Basic permissions for all Lambda functions: CloudWatch Logs + VPC networking + X-Ray"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${var.project_name}-*"
      },
      {
        Sid    = "VPCNetworking"
        Effect = "Allow"
        Action = [
          "ec2:CreateNetworkInterface",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DeleteNetworkInterface",
          "ec2:AssignPrivateIpAddresses",
          "ec2:UnassignPrivateIpAddresses",
        ]
        Resource = "*"
      },
      {
        Sid    = "XRayTracing"
        Effect = "Allow"
        Action = ["xray:PutTraceSegments", "xray:PutTelemetryRecords"]
        Resource = "*"
      },
    ]
  })
}

# ── IAM Role: report-generator ────────────────────────────────────────────────
resource "aws_iam_role" "report_generator" {
  name               = "${var.project_name}-report-generator"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "report_generator_basic" {
  role       = aws_iam_role.report_generator.name
  policy_arn = aws_iam_policy.lambda_basic.arn
}

resource "aws_iam_role_policy" "report_generator_inline" {
  name = "report-generator-permissions"
  role = aws_iam_role.report_generator.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBRead"
        Effect = "Allow"
        Action = ["dynamodb:GetItem", "dynamodb:Scan", "dynamodb:Query"]
        Resource = [
          "arn:aws:dynamodb:${local.region}:${local.account_id}:table/${var.dynamodb_table_name}",
          "arn:aws:dynamodb:${local.region}:${local.account_id}:table/${var.dynamodb_table_name}/index/*",
        ]
      },
      {
        Sid    = "S3ReportsBucketWrite"
        Effect = "Allow"
        Action = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
        Resource = "arn:aws:s3:::${var.reports_bucket_name}/reports/*"
      },
      {
        Sid    = "S3PresignedUrl"
        Effect = "Allow"
        Action = ["s3:GetObject"]
        Resource = "arn:aws:s3:::${var.reports_bucket_name}/*"
      },
      {
        Sid    = "SNSPublishSlack"
        Effect = "Allow"
        Action = ["sns:Publish"]
        Resource = aws_sns_topic.chaos_notifications.arn
      },
      {
        Sid    = "SSMGetWebhook"
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = "arn:aws:ssm:${local.region}:${local.account_id}:parameter${var.slack_webhook_ssm_param}"
      },
    ]
  })
}

# ── IAM Role: slack-notifier ──────────────────────────────────────────────────
resource "aws_iam_role" "slack_notifier" {
  name               = "${var.project_name}-slack-notifier"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "slack_notifier_basic" {
  role       = aws_iam_role.slack_notifier.name
  policy_arn = aws_iam_policy.lambda_basic.arn
}

resource "aws_iam_role_policy" "slack_notifier_inline" {
  name = "slack-notifier-permissions"
  role = aws_iam_role.slack_notifier.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "SSMGetWebhookUrl"
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        # Read access to the specific Slack webhook URL parameter only
        Resource = "arn:aws:ssm:${local.region}:${local.account_id}:parameter${var.slack_webhook_ssm_param}"
      },
      {
        Sid    = "SNSSubscribe"
        Effect = "Allow"
        Action = ["sns:GetTopicAttributes"]
        Resource = aws_sns_topic.chaos_notifications.arn
      },
    ]
  })
}

# Allow SNS to invoke the slack-notifier Lambda
resource "aws_lambda_permission" "sns_invoke_slack_notifier" {
  statement_id  = "AllowSNSInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.slack_notifier.function_name
  principal     = "sns.amazonaws.com"
  source_arn    = aws_sns_topic.chaos_notifications.arn
}

# ── IAM Role: experiment-scheduler ────────────────────────────────────────────
resource "aws_iam_role" "experiment_scheduler" {
  name               = "${var.project_name}-experiment-scheduler"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "experiment_scheduler_basic" {
  role       = aws_iam_role.experiment_scheduler.name
  policy_arn = aws_iam_policy.lambda_basic.arn
}

resource "aws_iam_role_policy" "experiment_scheduler_inline" {
  name = "experiment-scheduler-permissions"
  role = aws_iam_role.experiment_scheduler.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "DynamoDBReadUpdate"
        Effect = "Allow"
        Action = ["dynamodb:Scan", "dynamodb:UpdateItem", "dynamodb:GetItem"]
        Resource = "arn:aws:dynamodb:${local.region}:${local.account_id}:table/${var.dynamodb_table_name}"
      },
      {
        Sid    = "SNSPublishSlackAlert"
        Effect = "Allow"
        Action = ["sns:Publish"]
        Resource = aws_sns_topic.chaos_notifications.arn
      },
      # The chaos engine is accessed via internal VPC networking (HTTP, not IAM)
      # No IAM permission needed for the REST API call
    ]
  })
}

# Allow EventBridge to invoke both schedulable Lambda functions
resource "aws_lambda_permission" "eventbridge_invoke_scheduler" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.experiment_scheduler.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.nightly_chaos.arn
}

resource "aws_lambda_permission" "eventbridge_invoke_report" {
  statement_id  = "AllowEventBridgeInvokeWeekly"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.report_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_report.arn
}

# Allow S3 to invoke the report-generator Lambda on object creation
resource "aws_lambda_permission" "s3_invoke_report_generator" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.report_generator.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = "arn:aws:s3:::${var.results_bucket_name}"
}
