output "report_generator_arn" {
  description = "ARN of the report-generator Lambda function"
  value       = aws_lambda_function.report_generator.arn
}

output "report_generator_function_name" {
  description = "Name of the report-generator Lambda function"
  value       = aws_lambda_function.report_generator.function_name
}

output "slack_notifier_arn" {
  description = "ARN of the slack-notifier Lambda function"
  value       = aws_lambda_function.slack_notifier.arn
}

output "experiment_scheduler_arn" {
  description = "ARN of the experiment-scheduler Lambda function"
  value       = aws_lambda_function.experiment_scheduler.arn
}

output "sns_topic_arn" {
  description = "ARN of the chaos-notifications SNS topic"
  value       = aws_sns_topic.chaos_notifications.arn
}

output "sns_topic_name" {
  description = "Name of the chaos-notifications SNS topic (used by chaos-engine and alertmanager)"
  value       = aws_sns_topic.chaos_notifications.name
}

output "lambda_security_group_id" {
  description = "Security group ID for VPC-attached Lambda functions"
  value       = aws_security_group.lambda.id
}

output "report_generator_log_group" {
  description = "CloudWatch log group for report-generator"
  value       = aws_cloudwatch_log_group.report_generator.name
}

output "slack_notifier_log_group" {
  description = "CloudWatch log group for slack-notifier"
  value       = aws_cloudwatch_log_group.slack_notifier.name
}

output "experiment_scheduler_log_group" {
  description = "CloudWatch log group for experiment-scheduler"
  value       = aws_cloudwatch_log_group.experiment_scheduler.name
}

output "nightly_eventbridge_rule_arn" {
  description = "ARN of the EventBridge rule triggering nightly chaos experiments"
  value       = aws_cloudwatch_event_rule.nightly_chaos.arn
}

output "weekly_report_eventbridge_rule_arn" {
  description = "ARN of the EventBridge rule triggering weekly reports"
  value       = aws_cloudwatch_event_rule.weekly_report.arn
}
