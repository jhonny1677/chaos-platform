data "aws_caller_identity" "current" {}

module "s3" {
  source = "./modules/s3"

  environment = var.environment
  project     = var.project
  account_id  = data.aws_caller_identity.current.account_id
}

module "dynamodb" {
  source = "./modules/dynamodb"

  environment = var.environment
  project     = var.project
}

module "vpc" {
  source = "./modules/vpc"

  vpc_cidr           = var.vpc_cidr
  availability_zones = var.availability_zones
  cluster_name       = var.cluster_name
  environment        = var.environment
  project            = var.project
}

# IAM module is called with EKS OIDC outputs to build IRSA roles.
# Terraform resolves the internal resource graph correctly:
#   cluster_role/node_role have no EKS dependency → EKS cluster is created →
#   OIDC provider is created → IRSA roles are created.
# If Terraform reports a cycle, use the two-stage apply documented in README.md.
module "iam" {
  source = "./modules/iam"

  cluster_name      = var.cluster_name
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_provider_url = module.eks.oidc_provider_url
  environment       = var.environment
  project           = var.project
}

module "eks" {
  source = "./modules/eks"

  cluster_name       = var.cluster_name
  cluster_version    = var.cluster_version
  vpc_id             = module.vpc.vpc_id
  private_subnet_ids = module.vpc.private_subnet_ids
  cluster_role_arn   = module.iam.eks_cluster_role_arn
  node_role_arn      = module.iam.eks_node_group_role_arn
  min_size           = var.node_group_min_size
  max_size           = var.node_group_max_size
  desired_size       = var.node_group_desired_size
  instance_type      = var.node_instance_type
  environment        = var.environment
  project            = var.project
}
