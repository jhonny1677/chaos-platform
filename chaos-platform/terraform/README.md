# Chaos Platform — Terraform Infrastructure (Phase 1)

This directory contains all Terraform code to provision the AWS infrastructure for the Chaos Engineering and Load Testing Platform.

---

## Module Overview

| Module | What it creates |
|--------|----------------|
| `vpc` | VPC (10.0.0.0/16), 2 public + 2 private subnets, Internet Gateway, NAT Gateway, route tables |
| `eks` | EKS cluster v1.29, managed node group (SPOT t3.medium, 2–5 nodes), OIDC provider for IRSA |
| `iam` | EKS cluster role, node group role, IRSA role for chaos-engine, IRSA role for external-secrets |
| `s3` | Experiment reports bucket, Terraform state bucket (versioning + AES-256 + block public access) |
| `dynamodb` | `chaos-experiments` table (experiment configs/results), `terraform-state-lock` table |

---

## Prerequisites

| Tool | Version |
|------|---------|
| Terraform | >= 1.6.0 |
| AWS CLI | >= 2.x |
| kubectl | >= 1.29 |

Configure AWS credentials before running any commands:

```bash
aws configure
# or
export AWS_ACCESS_KEY_ID=...
export AWS_SECRET_ACCESS_KEY=...
export AWS_DEFAULT_REGION=us-east-1
```

---

## Bootstrap (one-time setup)

There is a chicken-and-egg problem: the S3 backend stores Terraform state, but the S3 bucket is created by Terraform. Follow these steps once:

### Step 1 — Comment out the S3 backend

In `versions.tf`, comment out the entire `backend "s3"` block:

```hcl
# backend "s3" {
#   bucket         = "..."
#   ...
# }
```

### Step 2 — Initialize with local state and create only the S3 + DynamoDB resources

```bash
terraform init
terraform apply -target=module.s3 -target=module.dynamodb
```

### Step 3 — Get your account ID from the output

```bash
terraform output aws_account_id
```

### Step 4 — Enable the S3 backend

In `versions.tf`, uncomment the `backend "s3"` block and replace `ACCOUNT_ID` with the value from Step 3:

```hcl
backend "s3" {
  bucket         = "chaos-platform-tfstate-123456789012"
  key            = "global/terraform.tfstate"
  region         = "us-east-1"
  encrypt        = true
  dynamodb_table = "terraform-state-lock"
}
```

### Step 5 — Migrate local state to S3

```bash
terraform init -migrate-state
# Type "yes" when prompted
```

---

## Full Deployment (after bootstrap)

```bash
# 1. Download providers and modules
terraform init

# 2. Preview what will be created (~35 resources)
terraform plan

# 3. Deploy everything
terraform apply
# Type "yes" when prompted — EKS takes ~15 minutes
```

---

## Two-Stage Apply (if Terraform reports a module cycle)

The IAM module passes OIDC outputs from the EKS module back into itself for IRSA roles. Terraform resolves this at the resource level. If it reports a cycle error, use the two-stage approach:

```bash
# Stage 1: create IAM cluster/node roles + VPC + S3 + DynamoDB
terraform apply \
  -target=module.iam.aws_iam_role.eks_cluster \
  -target=module.iam.aws_iam_role.eks_node_group \
  -target=module.iam.aws_iam_role_policy_attachment.eks_cluster_policy \
  -target=module.iam.aws_iam_role_policy_attachment.eks_worker_node_policy \
  -target=module.iam.aws_iam_role_policy_attachment.eks_cni_policy \
  -target=module.iam.aws_iam_role_policy_attachment.eks_ecr_readonly \
  -target=module.vpc \
  -target=module.s3 \
  -target=module.dynamodb

# Stage 2: create EKS + IRSA roles
terraform apply
```

---

## Connect kubectl to the cluster

```bash
aws eks update-kubeconfig \
  --region us-east-1 \
  --name chaos-platform-eks
```

Verify:

```bash
kubectl get nodes
```

---

## Useful Commands

```bash
# View all outputs (endpoints, bucket names, role ARNs)
terraform output

# Destroy everything (careful — this deletes all resources)
# Note: the state bucket has prevent_destroy = true.
# Remove that lifecycle block before running destroy.
terraform destroy
```

---

## Variable Overrides

All defaults are in `variables.tf`. Override any variable via a `terraform.tfvars` file:

```hcl
# terraform.tfvars
aws_region              = "us-west-2"
cluster_name            = "my-chaos-cluster"
node_group_min_size     = 2
node_group_max_size     = 5
node_group_desired_size = 2
```

Or pass them inline:

```bash
terraform apply -var="aws_region=us-west-2" -var="environment=staging"
```

---

## Cost Estimate (dev environment)

| Resource | Approx. monthly cost |
|----------|----------------------|
| EKS control plane | ~$73 |
| 2x t3.medium SPOT nodes | ~$20–30 |
| NAT Gateway | ~$35 |
| S3 (minimal data) | < $1 |
| DynamoDB (PAY_PER_REQUEST, low traffic) | < $1 |
| **Total** | **~$130–140/month** |

To reduce costs while not actively testing: scale the node group to 0 or destroy the cluster and recreate it when needed.
