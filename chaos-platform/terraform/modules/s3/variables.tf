variable "environment" {
  description = "Environment name"
  type        = string
}

variable "project" {
  description = "Project name"
  type        = string
}

variable "account_id" {
  description = "AWS account ID — used as a suffix to guarantee globally unique bucket names"
  type        = string
}
