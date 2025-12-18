# Deployment Guide

This document is the authoritative step-by-step reference for deploying, verifying, and destroying the Chaos Engineering and Load Testing Platform.

---

## Prerequisites

The following tools must be installed and available on your PATH before beginning.

| Tool | Minimum Version | Purpose |
|---|---|---|
| AWS CLI | 2.x | AWS resource management and authentication |
| Terraform | 1.7 | Infrastructure provisioning |
| kubectl | 1.29 | Kubernetes cluster interaction |
| Helm | 3.14 | Kubernetes package management |
| Helmfile | 0.162 | Declarative multi-chart Helm management |
| ArgoCD CLI | 2.10 | ArgoCD application management |
| kubeseal | 0.26 | Sealed Secrets encryption |
| Docker | 24 | Container image building |
| jq | 1.7 | JSON output parsing |

Your AWS credentials must be configured with sufficient permissions to create EKS clusters, VPCs, MSK clusters, RDS instances, ElastiCache clusters, S3 buckets, DynamoDB tables, Lambda functions, and IAM roles.

```bash
aws configure
aws sts get-caller-identity   # verify credentials are valid
```

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/jhonny1677/chaos-platform.git
cd chaos-platform/chaos-platform
```

---

## Step 2: Configure Terraform Variables

Create the variable file for the development environment. This file is excluded from version control.

```bash
cat > terraform/environments/dev/terraform.tfvars <<EOF
aws_region         = "us-east-1"
project            = "chaos-platform"
environment        = "dev"
vpc_cidr           = "10.0.0.0/16"
cluster_name       = "chaos-platform-dev"
notification_email = "your-email@example.com"
EOF
```

---

## Step 3: Bootstrap the S3 State Backend

On the first run, the S3 bucket for Terraform state does not yet exist. Comment out the `backend "s3"` block in `terraform/versions.tf`, then create the bucket:

```bash
cd terraform/environments/dev
terraform init
terraform apply -target=module.s3
```

Once the bucket exists, uncomment the backend block and re-initialise to migrate local state to S3:

```bash
terraform init -migrate-state
```

---

## Step 4: Deploy All AWS Infrastructure

```bash
terraform apply
```

This provisions approximately 80 AWS resources including:

- VPC with public and private subnets across two availability zones
- EKS cluster with managed node group (ON_DEMAND t3.medium)
- MSK Kafka cluster (kafka.t3.small, two brokers)
- ElastiCache Redis cluster (cache.t3.micro)
- RDS PostgreSQL instance (db.t3.micro, 20 GB)
- Four ECR repositories (target-app, chaos-engine, load-tester, dashboard)
- Three S3 buckets (Terraform state, experiment results, PDF reports)
- DynamoDB tables (experiment records, Terraform state lock)
- IAM roles with IRSA for each Kubernetes service account

Expected duration: 15 to 25 minutes.

### Verify

```bash
aws eks describe-cluster --name chaos-platform-dev --query 'cluster.status'
# Expected output: "ACTIVE"

aws eks list-nodegroups --cluster-name chaos-platform-dev
# Expected output: lists the worker node group
```

---

## Step 5: Configure kubectl

```bash
aws eks update-kubeconfig --region us-east-1 --name chaos-platform-dev
kubectl cluster-info
kubectl get nodes
# All nodes should show STATUS Ready
```

---

## Step 6: Bootstrap the Kubernetes Platform

```bash
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh
```

The bootstrap script:

1. Creates all required namespaces
2. Installs ArgoCD via Helm into the `argocd` namespace
3. Waits for all ArgoCD pods to reach Ready state
4. Creates the root App-of-Apps Application pointing to `argocd/apps/`

ArgoCD then deploys all remaining components automatically in sync wave order:

- Wave -2: kube-prometheus-stack, Loki, Grafana Tempo
- Wave -1: Vault, OPA/Gatekeeper, Kyverno, cert-manager, Sealed Secrets, Falco
- Wave 1 to 4: target-app, chaos-engine, load-tester, dashboard

### Verify

```bash
kubectl get applications -n argocd
# All applications should reach SYNC STATUS: Synced and HEALTH STATUS: Healthy
# This typically takes 10 to 15 minutes after the bootstrap completes

kubectl get pods -n monitoring
kubectl get pods -n security
kubectl get pods -n chaos-platform
```

---

## Step 7: Initialise Vault

```bash
chmod +x security/vault/scripts/init-vault.sh
./security/vault/scripts/init-vault.sh
```

This script initialises Vault with five key shares and a threshold of three, stores the unseal keys in a Kubernetes Secret, performs the initial unseal using three keys, enables the Kubernetes auth method, and applies the four access policies.

### Verify

```bash
kubectl exec -n vault vault-0 -- vault status
# Sealed: false
# HA Mode: active

kubectl exec -n vault vault-0 -- vault policy list
# Expected: chaos-engine, load-tester, dashboard, monitoring
```

---

## Step 8: Build and Push Container Images

```bash
REGISTRY=$(aws ecr describe-repositories \
  --query 'repositories[0].repositoryUri' \
  --output text | cut -d/ -f1)

aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $REGISTRY

for service in target-app chaos-engine load-tester dashboard; do
  docker build -t $REGISTRY/$service:latest apps/$service/
  docker push $REGISTRY/$service:latest
  echo "Pushed $service"
done
```

ArgoCD detects the updated image tags and triggers a rollout within approximately three minutes.

### Verify

```bash
kubectl rollout status deployment/target-app -n chaos-platform
kubectl rollout status deployment/chaos-engine -n chaos-platform
kubectl rollout status deployment/load-tester -n load-tester
kubectl rollout status deployment/dashboard -n chaos-platform
```

---

## Step 9: Deploy Lambda Functions

Store the Slack webhook URL in SSM Parameter Store before deploying:

```bash
aws ssm put-parameter \
  --name /chaos-platform/slack-webhook-url \
  --value "https://hooks.slack.com/services/YOUR/WEBHOOK/URL" \
  --type SecureString
```

Then deploy the Lambda functions:

```bash
cd lambda/terraform
terraform init
terraform apply \
  -var="results_bucket=chaos-platform-dev-results" \
  -var="reports_bucket=chaos-platform-dev-reports" \
  -var="experiments_table=chaos-platform-experiments"
```

### Verify

```bash
aws lambda invoke \
  --function-name chaos-platform-slack-notifier \
  --payload '{"test": true}' \
  /tmp/response.json
cat /tmp/response.json
# Expected: {"statusCode": 200}
```

---

## Step 10: Access the Platform

### Dashboard

```bash
kubectl port-forward svc/dashboard 8080:8080 -n chaos-platform
```

Open http://localhost:8080

### Grafana

```bash
kubectl port-forward svc/prometheus-grafana 3000:80 -n monitoring
```

Open http://localhost:3000

Retrieve the admin password:

```bash
kubectl get secret prometheus-grafana -n monitoring \
  -o jsonpath="{.data.admin-password}" | base64 --decode
```

### ArgoCD

```bash
kubectl port-forward svc/argocd-server 8443:443 -n argocd
```

Open https://localhost:8443

Retrieve the admin password:

```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 --decode
```

### Chaos Engine API

```bash
kubectl port-forward svc/chaos-engine 8001:8001 -n chaos-platform
curl http://localhost:8001/health
```

---

## Component Verification Checklist

Run these commands to confirm the full platform is operational before running experiments.

```bash
# All ArgoCD applications synced and healthy
kubectl get applications -n argocd

# All pods running across key namespaces
kubectl get pods -n chaos-platform
kubectl get pods -n monitoring
kubectl get pods -n security
kubectl get pods -n vault
kubectl get pods -n falco

# Vault unsealed
kubectl exec -n vault vault-0 -- vault status | grep Sealed

# Prometheus scraping targets
kubectl port-forward svc/prometheus-operated 9090:9090 -n monitoring
# Open http://localhost:9090/targets and verify all targets are UP

# Kafka brokers reachable
kubectl exec -n chaos-platform deploy/chaos-engine -- \
  python -c "from kafka import KafkaProducer; p = KafkaProducer(bootstrap_servers='$KAFKA_BROKERS'); print('OK')"

# Circuit breaker closed
curl http://localhost:8001/health | jq '.circuitBreaker.state'
# Expected: "closed"
```

---

## Destroying the Platform

### Step 1: Empty S3 Buckets

Terraform cannot delete non-empty S3 buckets. Empty them first:

```bash
for bucket in $(aws s3 ls | awk '{print $3}' | grep chaos-platform); do
  aws s3 rm s3://$bucket --recursive
  echo "Emptied $bucket"
done
```

### Step 2: Destroy Lambda Infrastructure

```bash
cd lambda/terraform
terraform destroy
```

### Step 3: Destroy Kubernetes Platform

```bash
cd terraform/environments/dev
terraform destroy -target=module.eks
```

Wait for the EKS cluster and all node groups to be fully deleted before proceeding. This ensures load balancers and ENIs created by Kubernetes are cleaned up properly.

### Step 4: Destroy Remaining AWS Infrastructure

```bash
terraform destroy
```

### Step 5: Verify Teardown

```bash
aws eks list-clusters
# Expected: no clusters listed

aws rds describe-db-instances
# Expected: no instances listed

aws kafka list-clusters
# Expected: no clusters listed

aws elasticache describe-cache-clusters
# Expected: no clusters listed
```

### Step 6: Clean Up Terraform State (Optional)

Only do this if you intend to start fresh with no record of the previous deployment.

```bash
aws s3 rb s3://chaos-platform-tfstate-YOUR_ACCOUNT_ID --force
aws dynamodb delete-table --table-name terraform-state-lock
```

---

## Troubleshooting Deployment Issues

For detailed diagnosis of common issues encountered during deployment, see [docs/runbooks/troubleshooting.md](docs/runbooks/troubleshooting.md).

For cost breakdown and strategies to reduce spend during development, see [docs/runbooks/cost-management.md](docs/runbooks/cost-management.md).
