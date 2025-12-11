# Getting Started

## Prerequisites

You need the following tools installed locally before running any commands:

| Tool | Version | Install |
|---|---|---|
| AWS CLI | 2.x | `brew install awscli` or [official installer](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) |
| Terraform | 1.7+ | `brew install terraform` |
| kubectl | 1.29+ | `brew install kubectl` |
| Helm | 3.14+ | `brew install helm` |
| helmfile | 0.162+ | `brew install helmfile` |
| ArgoCD CLI | 2.10+ | `brew install argocd` |
| kubeseal | 0.26+ | `brew install kubeseal` |
| jq | 1.7+ | `brew install jq` |
| Docker | 24+ | Docker Desktop |

You also need:
- An AWS account with admin access
- AWS credentials configured: `aws configure`
- A GitHub account with the repo forked

---

## Step 1: Clone and Configure

```bash
git clone https://github.com/YOUR_USERNAME/chaos-platform.git
cd chaos-platform/chaos-platform
```

Create your local variable file (this file is gitignored):

```bash
cat > terraform/environments/dev/terraform.tfvars <<EOF
aws_region        = "us-east-1"
project_name      = "chaos-platform"
environment       = "dev"
vpc_cidr          = "10.0.0.0/16"
cluster_name      = "chaos-platform-dev"
notification_email = "your-email@example.com"
EOF
```

---

## Step 2: Deploy Infrastructure with Terraform

```bash
cd terraform/environments/dev

# Initialize backend (S3 + DynamoDB state locking)
terraform init

# Preview what will be created (~80 resources)
terraform plan

# Deploy — takes 15-20 minutes
terraform apply
```

This creates:
- VPC with public/private subnets across 3 AZs
- EKS cluster (SPOT t3.medium nodes)
- NAT Gateway, Internet Gateway
- ECR repositories for all 4 services
- S3 buckets (state, results, reports, Loki backend)
- DynamoDB tables (experiments, state lock)
- MSK Kafka cluster
- ElastiCache Redis cluster
- IAM roles with IRSA for each service

**Verify:**
```bash
aws eks describe-cluster --name chaos-platform-dev --query 'cluster.status'
# Expected: "ACTIVE"
```

---

## Step 3: Configure kubectl

```bash
aws eks update-kubeconfig --region us-east-1 --name chaos-platform-dev

kubectl cluster-info
# Expected: Kubernetes control plane is running at https://...
```

---

## Step 4: Bootstrap the Platform

The bootstrap script installs ArgoCD, seeds the App-of-Apps, and then ArgoCD takes over for everything else:

```bash
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

This script:
1. Installs ArgoCD via Helm
2. Waits for ArgoCD pods to be Ready
3. Creates the root ArgoCD Application pointing at `argocd/apps/`
4. ArgoCD then deploys (in sync wave order): monitoring → security → applications

**Watch the deployment progress:**
```bash
kubectl get applications -n argocd --watch
```

Expected final state (takes 10-15 minutes):
```
NAME           SYNC STATUS   HEALTH STATUS
monitoring     Synced        Healthy
security       Synced        Healthy
vault          Synced        Healthy
target-app     Synced        Healthy
chaos-engine   Synced        Healthy
load-tester    Synced        Healthy
dashboard      Synced        Healthy
```

---

## Step 5: Initialize Vault

```bash
chmod +x security/vault/scripts/init-vault.sh
./security/vault/scripts/init-vault.sh
```

This script:
1. Calls `vault operator init` with 5 key shares, 3 threshold
2. Stores the unseal keys as a K8s Secret (base64-encoded)
3. Unseals Vault using 3 of the 5 keys
4. Configures Kubernetes auth method
5. Applies the 4 Vault policies

**Verify Vault is unsealed:**
```bash
kubectl exec -n vault vault-0 -- vault status
# Expected: Sealed: false, HA Mode: active
```

---

## Step 6: Build and Push Container Images

```bash
# Get the ECR registry URL
REGISTRY=$(aws ecr describe-repositories --query 'repositories[0].repositoryUri' --output text | cut -d/ -f1)
aws ecr get-login-password | docker login --username AWS --password-stdin $REGISTRY

# Build and push all 4 images
for service in target-app chaos-engine load-tester dashboard; do
  docker build -t $REGISTRY/$service:latest apps/$service/
  docker push $REGISTRY/$service:latest
done
```

ArgoCD will detect the new image tags and deploy within 3 minutes.

---

## Step 7: Deploy Lambda Functions

```bash
cd lambda/terraform
terraform init
terraform apply \
  -var="weasyprint_layer_arn=arn:aws:lambda:us-east-1:123456789012:layer:weasyprint:1" \
  -var="results_bucket=chaos-platform-dev-results" \
  -var="reports_bucket=chaos-platform-dev-reports" \
  -var="experiments_table=chaos-platform-experiments"
```

Note: The WeasyPrint Lambda layer must be built separately. See `lambda/report-generator/README.md`.

---

## Step 8: Verify Everything Is Running

```bash
# All pods should be Running or Completed
kubectl get pods --all-namespaces

# Access the dashboard
kubectl port-forward svc/dashboard 8080:8080 -n chaos-platform
# Open http://localhost:8080

# Access Grafana
kubectl port-forward svc/grafana 3000:3000 -n monitoring
# Open http://localhost:3000
# Default credentials: admin / (check grafana secret)

# Access ArgoCD UI
kubectl port-forward svc/argocd-server 8443:443 -n argocd
# Open https://localhost:8443
# Password: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath="{.data.password}" | base64 -d
```

---

## Common Errors

**Error: `Error: creating EKS Cluster: operation error EKS: CreateCluster, failed to assume role`**  
Your AWS credentials don't have sufficient permissions. Ensure the IAM user/role has `AdministratorAccess` or the specific EKS permissions listed in `terraform/iam-bootstrap-policy.json`.

**Error: `Vault is sealed`**  
Vault pod restarted and needs unsealing. Run: `./security/vault/scripts/unseal-vault.sh`

**Error: `ArgoCD application stuck in Progressing`**  
Usually a missing ECR image or failing pod readiness probe. Check: `kubectl describe application <name> -n argocd` and `kubectl get events -n <namespace> --sort-by='.lastTimestamp'`

**Error: `kubeseal: error: cannot fetch certificate`**  
The Sealed Secrets controller is not running. Check: `kubectl get pods -n kube-system | grep sealed`

**Error: `Lambda function: task timed out after 60.00 seconds` (slack-notifier)**  
The SSM Parameter `/chaos-platform/slack-webhook-url` is missing. Create it:
```bash
aws ssm put-parameter \
  --name /chaos-platform/slack-webhook-url \
  --value "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK" \
  --type SecureString
```
