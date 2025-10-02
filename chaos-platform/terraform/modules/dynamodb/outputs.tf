output "table_name" {
  description = "Name of the chaos-experiments DynamoDB table"
  value       = aws_dynamodb_table.chaos_experiments.name
}

output "table_arn" {
  description = "ARN of the chaos-experiments DynamoDB table"
  value       = aws_dynamodb_table.chaos_experiments.arn
}

output "lock_table_name" {
  description = "Name of the Terraform state lock DynamoDB table"
  value       = aws_dynamodb_table.terraform_lock.name
}
