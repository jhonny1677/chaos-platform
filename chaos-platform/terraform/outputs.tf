output "vpc_id" {
  description = "ID of the VPC"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = module.vpc.private_subnet_ids
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = module.vpc.public_subnet_ids
}

output "eks_cluster_name" {
  description = "Name of the EKS cluster"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "API server endpoint for the EKS cluster"
  value       = module.eks.cluster_endpoint
}

output "eks_cluster_ca_data" {
  description = "Base64-encoded CA certificate for the EKS cluster"
  value       = module.eks.cluster_ca_data
  sensitive   = true
}

output "oidc_provider_arn" {
  description = "ARN of the OIDC provider for IRSA"
  value       = module.eks.oidc_provider_arn
}

output "chaos_engine_role_arn" {
  description = "ARN of the IRSA role for the chaos engine service account"
  value       = module.iam.chaos_engine_role_arn
}

output "external_secrets_role_arn" {
  description = "ARN of the IRSA role for the external-secrets service account"
  value       = module.iam.external_secrets_role_arn
}

output "reports_bucket_name" {
  description = "Name of the S3 bucket for experiment reports"
  value       = module.s3.reports_bucket_id
}

output "state_bucket_name" {
  description = "Name of the S3 bucket for Terraform state"
  value       = module.s3.state_bucket_id
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table for chaos experiments"
  value       = module.dynamodb.table_name
}

output "aws_account_id" {
  description = "AWS account ID — use this to fill in the backend bucket name in versions.tf"
  value       = data.aws_caller_identity.current.account_id
}
