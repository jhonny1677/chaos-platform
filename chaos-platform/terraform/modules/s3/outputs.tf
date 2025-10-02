output "reports_bucket_id" {
  description = "Name (ID) of the experiment reports S3 bucket"
  value       = aws_s3_bucket.reports.id
}

output "reports_bucket_arn" {
  description = "ARN of the experiment reports S3 bucket"
  value       = aws_s3_bucket.reports.arn
}

output "state_bucket_id" {
  description = "Name (ID) of the Terraform state S3 bucket"
  value       = aws_s3_bucket.terraform_state.id
}

output "state_bucket_arn" {
  description = "ARN of the Terraform state S3 bucket"
  value       = aws_s3_bucket.terraform_state.arn
}
