# ── EKS Cluster Role ─────────────────────────────────────────────────────────

data "aws_iam_policy_document" "eks_cluster_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["eks.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "eks_cluster" {
  name               = "${var.cluster_name}-cluster-role"
  assume_role_policy = data.aws_iam_policy_document.eks_cluster_assume.json

  tags = {
    Name = "${var.cluster_name}-cluster-role"
  }
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

# ── EKS Node Group Role ───────────────────────────────────────────────────────

data "aws_iam_policy_document" "eks_node_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "eks_node_group" {
  name               = "${var.cluster_name}-node-role"
  assume_role_policy = data.aws_iam_policy_document.eks_node_assume.json

  tags = {
    Name = "${var.cluster_name}-node-role"
  }
}

resource "aws_iam_role_policy_attachment" "eks_worker_node_policy" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSWorkerNodePolicy"
}

resource "aws_iam_role_policy_attachment" "eks_cni_policy" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKS_CNI_Policy"
}

resource "aws_iam_role_policy_attachment" "eks_ecr_readonly" {
  role       = aws_iam_role.eks_node_group.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# ── IRSA: Chaos Engine ────────────────────────────────────────────────────────
# The chaos engine runs inside Kubernetes and needs AWS permissions to:
# - Describe EKS cluster info (kubeconfig generation)
# - Write experiment reports to S3
# - Push custom metrics to CloudWatch
# Pod deletion itself happens via Kubernetes RBAC (not AWS IAM).

data "aws_iam_policy_document" "chaos_engine_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    actions = ["sts:AssumeRoleWithWebIdentity"]
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:chaos-engine:chaos-engine-sa"]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "chaos_engine" {
  name               = "${var.project}-chaos-engine-irsa"
  assume_role_policy = data.aws_iam_policy_document.chaos_engine_assume.json

  tags = {
    Name = "${var.project}-chaos-engine-irsa"
  }
}

data "aws_iam_policy_document" "chaos_engine_permissions" {
  statement {
    sid    = "EKSDescribe"
    effect = "Allow"
    actions = [
      "eks:DescribeCluster",
      "eks:ListClusters",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "S3Reports"
    effect = "Allow"
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
    ]
    resources = [
      "arn:aws:s3:::${var.project}-reports-*",
      "arn:aws:s3:::${var.project}-reports-*/*",
    ]
  }

  statement {
    sid    = "CloudWatchMetrics"
    effect = "Allow"
    actions = [
      "cloudwatch:PutMetricData",
      "cloudwatch:GetMetricData",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = ["arn:aws:dynamodb:*:*:table/chaos-experiments"]
  }
}

resource "aws_iam_policy" "chaos_engine" {
  name        = "${var.project}-chaos-engine-policy"
  description = "Permissions for the chaos engine service account"
  policy      = data.aws_iam_policy_document.chaos_engine_permissions.json
}

resource "aws_iam_role_policy_attachment" "chaos_engine" {
  role       = aws_iam_role.chaos_engine.name
  policy_arn = aws_iam_policy.chaos_engine.arn
}

# ── IRSA: External Secrets ────────────────────────────────────────────────────
# external-secrets operator pulls secrets from AWS Secrets Manager into
# Kubernetes Secret objects.

data "aws_iam_policy_document" "external_secrets_assume" {
  statement {
    effect = "Allow"
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    actions = ["sts:AssumeRoleWithWebIdentity"]
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:sub"
      values   = ["system:serviceaccount:external-secrets:external-secrets-sa"]
    }
    condition {
      test     = "StringEquals"
      variable = "${var.oidc_provider_url}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "external_secrets" {
  name               = "${var.project}-external-secrets-irsa"
  assume_role_policy = data.aws_iam_policy_document.external_secrets_assume.json

  tags = {
    Name = "${var.project}-external-secrets-irsa"
  }
}

data "aws_iam_policy_document" "external_secrets_permissions" {
  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
      "secretsmanager:ListSecretVersionIds",
    ]
    resources = ["arn:aws:secretsmanager:*:*:secret:${var.project}/*"]
  }
}

resource "aws_iam_policy" "external_secrets" {
  name        = "${var.project}-external-secrets-policy"
  description = "Allows external-secrets to read from AWS Secrets Manager"
  policy      = data.aws_iam_policy_document.external_secrets_permissions.json
}

resource "aws_iam_role_policy_attachment" "external_secrets" {
  role       = aws_iam_role.external_secrets.name
  policy_arn = aws_iam_policy.external_secrets.arn
}
