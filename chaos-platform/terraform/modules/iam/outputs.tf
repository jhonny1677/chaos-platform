output "eks_cluster_role_arn" {
  description = "ARN of the IAM role for the EKS control plane"
  value       = aws_iam_role.eks_cluster.arn
}

output "eks_node_group_role_arn" {
  description = "ARN of the IAM role for EKS worker nodes"
  value       = aws_iam_role.eks_node_group.arn
}

output "chaos_engine_role_arn" {
  description = "ARN of the IRSA role for the chaos engine service account"
  value       = aws_iam_role.chaos_engine.arn
}

output "external_secrets_role_arn" {
  description = "ARN of the IRSA role for the external-secrets service account"
  value       = aws_iam_role.external_secrets.arn
}
