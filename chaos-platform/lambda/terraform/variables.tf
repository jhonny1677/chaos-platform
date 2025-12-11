variable "project_name" {
  description = "Project name prefix for all resources"
  type        = string
  default     = "chaos-platform"
}

variable "aws_region" {
  description = "AWS region to deploy Lambda functions"
  type        = string
  default     = "us-east-1"
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for experiment results"
  type        = string
  default     = "chaos-experiments"
}

variable "reports_bucket_name" {
  description = "S3 bucket name where PDF reports are stored"
  type        = string
}

variable "results_bucket_name" {
  description = "S3 bucket name where experiment result JSONs land (triggers report-generator)"
  type        = string
}

variable "chaos_engine_url" {
  description = "Internal Kubernetes service URL for the Chaos Engine REST API"
  type        = string
  default     = "http://chaos-engine.chaos-engine.svc.cluster.local:8001"
}

variable "slack_webhook_ssm_param" {
  description = "SSM Parameter Store path containing the Slack webhook URL (SecureString)"
  type        = string
  default     = "/chaos-platform/slack/webhook-url"
}

variable "slack_channel_experiments" {
  description = "Slack channel for experiment events"
  type        = string
  default     = "#chaos-experiments"
}

variable "slack_channel_alerts" {
  description = "Slack channel for fired alerts"
  type        = string
  default     = "#chaos-platform-alerts"
}

variable "slack_channel_reports" {
  description = "Slack channel for generated reports"
  type        = string
  default     = "#chaos-reports"
}

variable "vpc_id" {
  description = "VPC ID where Lambda functions should run (same VPC as EKS)"
  type        = string
}

variable "vpc_cidr" {
  description = "VPC CIDR block for security group egress rules"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_ids" {
  description = "Private subnet IDs for VPC-attached Lambda functions"
  type        = list(string)
}

variable "weasyprint_layer_arn" {
  description = "ARN of the Lambda layer containing WeasyPrint native libraries"
  type        = string
  default     = ""
}

variable "log_level" {
  description = "Python log level for all Lambda functions"
  type        = string
  default     = "INFO"
  validation {
    condition     = contains(["DEBUG", "INFO", "WARNING", "ERROR"], var.log_level)
    error_message = "log_level must be one of: DEBUG, INFO, WARNING, ERROR"
  }
}

variable "nightly_chaos_schedule" {
  description = "EventBridge cron expression for nightly chaos experiments (UTC)"
  type        = string
  default     = "cron(0 2 ? * MON-FRI *)"   # 02:00 UTC Monday–Friday
}

variable "weekly_report_schedule" {
  description = "EventBridge cron expression for weekly report generation (UTC)"
  type        = string
  default     = "cron(0 8 ? * MON *)"   # 08:00 UTC every Monday
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default = {
    Project     = "chaos-platform"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}
