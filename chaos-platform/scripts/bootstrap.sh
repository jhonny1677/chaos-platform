#!/usr/bin/env bash
# bootstrap.sh — Complete setup script for a fresh AWS account.
# Run once after cloning the repo to provision everything end-to-end.
#
# Usage: cd chaos-platform && bash scripts/bootstrap.sh
#
# Prerequisites: aws-cli, terraform >=1.6, kubectl, helm, helmfile

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }
banner() { printf "\n${BLUE}═══════════════════════════════════════════${NC}\n${BLUE} %s${NC}\n${BLUE}═══════════════════════════════════════════${NC}\n" "$*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Step 0: Check prerequisites ───────────────────────────────────────────────
banner "Step 0: Checking Prerequisites"

check_tool() {
  if command -v "$1" &>/dev/null; then ok "$1 found ($(command -v "$1"))"; else err "$1 not found — install it first"; exit 1; fi
}

check_tool aws
check_tool terraform
check_tool kubectl
check_tool helm
check_tool helmfile
check_tool argocd

# Verify AWS credentials are configured
info "Checking AWS credentials..."
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="${AWS_REGION:-$(aws configure get region || echo 'us-east-1')}"
ok "AWS account: ${AWS_ACCOUNT_ID} | region: ${AWS_REGION}"

# ── Step 1: Terraform Bootstrap (S3 + DynamoDB for state) ─────────────────────
banner "Step 1: Terraform Bootstrap — S3 + DynamoDB state backend"

TF_DIR="${PROJECT_DIR}/terraform"
STATE_BUCKET="chaos-platform-tf-state-${AWS_ACCOUNT_ID}"
LOCK_TABLE="chaos-platform-tf-locks"

info "Checking if state bucket exists..."
if aws s3 ls "s3://${STATE_BUCKET}" &>/dev/null; then
  ok "State bucket already exists: ${STATE_BUCKET}"
else
  info "Creating S3 state bucket..."
  aws s3api create-bucket \
    --bucket "${STATE_BUCKET}" \
    --region "${AWS_REGION}" \
    $([ "${AWS_REGION}" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=${AWS_REGION}")
  aws s3api put-bucket-versioning \
    --bucket "${STATE_BUCKET}" \
    --versioning-configuration Status=Enabled
  aws s3api put-bucket-encryption \
    --bucket "${STATE_BUCKET}" \
    --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  ok "Created state bucket: ${STATE_BUCKET}"
fi

info "Checking DynamoDB lock table..."
if aws dynamodb describe-table --table-name "${LOCK_TABLE}" &>/dev/null; then
  ok "Lock table already exists: ${LOCK_TABLE}"
else
  aws dynamodb create-table \
    --table-name "${LOCK_TABLE}" \
    --attribute-definitions AttributeName=LockID,AttributeType=S \
    --key-schema AttributeName=LockID,KeyType=HASH \
    --billing-mode PAY_PER_REQUEST \
    --region "${AWS_REGION}"
  ok "Created lock table: ${LOCK_TABLE}"
fi

# ── Step 2: Terraform Init + Apply ────────────────────────────────────────────
banner "Step 2: Terraform — Provisioning AWS Infrastructure"

cd "${TF_DIR}"
info "Running terraform init..."
terraform init \
  -backend-config="bucket=${STATE_BUCKET}" \
  -backend-config="region=${AWS_REGION}" \
  -backend-config="dynamodb_table=${LOCK_TABLE}"

info "Running terraform plan..."
terraform plan \
  -var="aws_region=${AWS_REGION}" \
  -var="aws_account_id=${AWS_ACCOUNT_ID}" \
  -out=tfplan

info "Running terraform apply..."
terraform apply -auto-approve tfplan
ok "AWS infrastructure provisioned (VPC, EKS, IAM, ECR, S3, DynamoDB)"
cd "${PROJECT_DIR}"

# ── Step 3: Configure kubectl ─────────────────────────────────────────────────
banner "Step 3: Configuring kubectl for EKS"

CLUSTER_NAME=$(terraform -chdir="${TF_DIR}" output -raw cluster_name 2>/dev/null || echo "chaos-platform")
info "Updating kubeconfig for cluster: ${CLUSTER_NAME}"
aws eks update-kubeconfig --name "${CLUSTER_NAME}" --region "${AWS_REGION}"
kubectl cluster-info
ok "kubectl configured"

# ── Step 4: Apply K8s base configuration ──────────────────────────────────────
banner "Step 4: Applying Kubernetes Base Configuration"

K8S_DIR="${PROJECT_DIR}/k8s"
info "Applying namespaces, RBAC, network policies, storage..."
kubectl apply -f "${K8S_DIR}/namespaces.yaml"
kubectl apply -f "${K8S_DIR}/rbac/"
kubectl apply -f "${K8S_DIR}/network-policies/"
kubectl apply -f "${K8S_DIR}/storage/"
kubectl apply -f "${K8S_DIR}/resource-quotas/"
ok "Base K8s configuration applied"

# ── Step 5: Install Helm charts via Helmfile ──────────────────────────────────
banner "Step 5: Installing Helm Releases (helmfile)"

info "Running helmfile sync — this installs: cert-manager, metrics-server, KEDA, ArgoCD, Prometheus, Loki, Vault, Sealed Secrets..."
helmfile --file "${K8S_DIR}/helmfile.yaml" sync
ok "All Helm releases installed"

# ── Step 6: Bootstrap ArgoCD ──────────────────────────────────────────────────
banner "Step 6: Bootstrapping ArgoCD"

info "Waiting for ArgoCD server to be ready..."
kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=300s

info "Applying AppProject..."
kubectl apply -f "${PROJECT_DIR}/argocd/projects/chaos-platform-project.yaml"

info "Applying App of Apps..."
kubectl apply -f "${PROJECT_DIR}/argocd/app-of-apps.yaml"

ARGOCD_PASSWORD=$(argocd admin initial-password -n argocd 2>/dev/null | head -1 || echo "(run: argocd admin initial-password -n argocd)")
ok "ArgoCD bootstrapped"

# ── Step 7: Health checks ─────────────────────────────────────────────────────
banner "Step 7: Health Checks"

info "Waiting for namespaces to have running pods (up to 5 minutes)..."
for ns in monitoring vault; do
  kubectl wait --for=condition=ready pod -l app.kubernetes.io/managed-by=Helm \
    -n "${ns}" --timeout=300s 2>/dev/null && ok "${ns} pods ready" || warn "${ns} pods not ready yet — check manually"
done

# ── Summary ───────────────────────────────────────────────────────────────────
banner "Bootstrap Complete!"

ARGOCD_LB=$(kubectl get svc argocd-server -n argocd -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "use port-forward")
GRAFANA_LB=$(kubectl get svc prometheus-grafana -n monitoring -o jsonpath='{.status.loadBalancer.ingress[0].hostname}' 2>/dev/null || echo "use port-forward")

printf "\n${GREEN}Services:${NC}\n"
printf "  ArgoCD:      https://${ARGOCD_LB} (user: admin, pass: ${ARGOCD_PASSWORD})\n"
printf "  Grafana:     http://${GRAFANA_LB} (user: admin, pass: prom-operator)\n"
printf "\n${YELLOW}Run 'bash scripts/port-forward.sh' for local access to all services.${NC}\n"
printf "${YELLOW}Then open: http://localhost:3001 for the Dashboard.${NC}\n\n"
