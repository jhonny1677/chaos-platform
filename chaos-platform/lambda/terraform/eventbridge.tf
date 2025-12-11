# ── EventBridge: Nightly Chaos Experiments ────────────────────────────────────
# Triggers the experiment-scheduler Lambda at 02:00 UTC Mon–Fri.
# 02:00 UTC is chosen because it is off-peak for most global engineering teams
# but still provides a daily "fire drill" for the on-call engineer.

resource "aws_cloudwatch_event_rule" "nightly_chaos" {
  name                = "${var.project_name}-nightly-chaos"
  description         = "Trigger scheduled chaos experiments at 02:00 UTC Mon–Fri"
  schedule_expression = var.nightly_chaos_schedule
  state               = "ENABLED"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "nightly_chaos_lambda" {
  rule      = aws_cloudwatch_event_rule.nightly_chaos.name
  target_id = "ExperimentSchedulerLambda"
  arn       = aws_lambda_function.experiment_scheduler.arn
  input     = jsonencode({ source = "eventbridge.nightly-chaos" })
}

# ── EventBridge: Weekly Summary Report ────────────────────────────────────────
# Triggers the report-generator Lambda at 08:00 UTC every Monday.
# The Monday timing means on-call engineers see the weekly summary at the
# start of the work week — useful for sprint planning and post-mortems.

resource "aws_cloudwatch_event_rule" "weekly_report" {
  name                = "${var.project_name}-weekly-report"
  description         = "Generate weekly summary report every Monday at 08:00 UTC"
  schedule_expression = var.weekly_report_schedule
  state               = "ENABLED"
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "weekly_report_lambda" {
  rule      = aws_cloudwatch_event_rule.weekly_report.name
  target_id = "ReportGeneratorLambda"
  arn       = aws_lambda_function.report_generator.arn
  input     = jsonencode({ detailType = "ScheduledWeeklySummary" })
}

# ── SNS Topic: chaos-notifications ───────────────────────────────────────────
# The chaos-notifications topic is the central event bus for the platform.
# Publishers: chaos-engine (Python SNS publish), alertmanager (webhook → Lambda → SNS),
#             report-generator Lambda, experiment-scheduler Lambda
# Subscribers: slack-notifier Lambda (all event types)

resource "aws_sns_topic_subscription" "slack_notifier" {
  topic_arn = aws_sns_topic.chaos_notifications.arn
  protocol  = "lambda"
  endpoint  = aws_lambda_function.slack_notifier.arn
}

# ── S3 Event Notification: Result files trigger report generation ──────────────
# When the chaos engine writes a result JSON to the results bucket,
# S3 triggers the report-generator Lambda within seconds.
# This provides sub-minute report generation after an experiment completes.

resource "aws_s3_bucket_notification" "results_trigger" {
  bucket = var.results_bucket_name

  lambda_function {
    lambda_function_arn = aws_lambda_function.report_generator.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "results/"
    filter_suffix       = ".json"
  }

  depends_on = [aws_lambda_permission.s3_invoke_report_generator]
}

# ── CloudWatch Alarms for Lambda health ───────────────────────────────────────
resource "aws_cloudwatch_metric_alarm" "report_generator_errors" {
  alarm_name          = "${var.project_name}-report-generator-errors"
  alarm_description   = "report-generator Lambda error rate > 1% for 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 2
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.report_generator.function_name
  }

  alarm_actions = [aws_sns_topic.chaos_notifications.arn]
  tags          = var.tags
}

resource "aws_cloudwatch_metric_alarm" "scheduler_errors" {
  alarm_name          = "${var.project_name}-scheduler-errors"
  alarm_description   = "experiment-scheduler Lambda error rate > 0 for 5 minutes"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  dimensions = {
    FunctionName = aws_lambda_function.experiment_scheduler.function_name
  }

  alarm_actions = [aws_sns_topic.chaos_notifications.arn]
  tags          = var.tags
}
