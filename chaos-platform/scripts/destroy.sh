#!/usr/bin/env bash
# destroy.sh — Ordered teardown of the entire chaos platform.
# Removes ArgoCD apps → K8s resources → Terraform-managed AWS infra.
#
# Usage: bash scripts/destroy.sh [--confirm]
# The --confirm flag skips the interactive prompt (for CI/CD pipelines).

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }
banner() { printf "\n${RED}═══════════════════════════════════════════${NC}\n${RED} %s${NC}\n${RED}═══════════════════════════════════════════${NC}\n" "$*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONFIRM="${1:-}"

# ── Safety prompt ─────────────────────────────────────────────────────────────
if [[ "${CONFIRM}" != "--confirm" ]]; then
  printf "\n${RED}WARNING: This will destroy ALL chaos-platform resources including:${NC}\n"
  printf "  • ArgoCD applications and managed workloads\n"
  printf "  • Kubernetes namespaces and all resources within them\n"
  printf "  • All AWS infrastructure (EKS, VPC, ECR, S3, DynamoDB)\n"
  printf "  • NOTE: S3 state bucket will NOT be deleted (preserves destroy record)\n\n"
  read -r -p "Type 'destroy' to confirm: " REPLY
  if [[ "${REPLY}" != "destroy" ]]; then
    err "Aborted — type 'destroy' to confirm."
    exit 1
  fi
fi

banner "Destroying Chaos Platform"

# ── Step 1: Remove ArgoCD applications (reverse wave order) ───────────────────
banner "Step 1: Removing ArgoCD Applications"

ARGOCD_APPS=(dashboard load-tester chaos-engine target-app security-stack monitoring-stack app-of-apps)

if command -v argocd &>/dev/null; then
  for app in "${ARGOCD_APPS[@]}"; do
    info "Deleting ArgoCD app: ${app}"
    argocd app delete "${app}" --cascade --yes 2>/dev/null && ok "${app} deleted" || warn "${app} not found or already gone"
  done
else
  warn "argocd CLI not found — deleting Application CRDs directly via kubectl"
  for app in "${ARGOCD_APPS[@]}"; do
    kubectl delete application "${app}" -n argocd --ignore-not-found=true 2>/dev/null && ok "${app} removed" || true
  done
fi

# Wait for cascaded deletion to finish
info "Waiting 30s for cascade deletes to propagate..."
sleep 30

# ── Step 2: Delete namespaces ─────────────────────────────────────────────────
banner "Step 2: Removing Kubernetes Namespaces"

NAMESPACES=(target-app chaos-engine load-tester monitoring jenkins vault)

for ns in "${NAMESPACES[@]}"; do
  info "Deleting namespace: ${ns}"
  kubectl delete namespace "${ns}" --ignore-not-found=true --timeout=120s 2>/dev/null && ok "${ns} deleted" || warn "${ns} deletion timed out — may still be terminating"
done

# ArgoCD itself
info "Removing ArgoCD..."
kubectl delete namespace argocd --ignore-not-found=true --timeout=120s 2>/dev/null && ok "argocd deleted" || warn "argocd deletion timed out"

# ── Step 3: Remove cluster-level resources ────────────────────────────────────
banner "Step 3: Removing Cluster-Level Resources"

info "Removing ClusterRoles and ClusterRoleBindings..."
kubectl delete clusterrole jenkins-cross-namespace-reader --ignore-not-found=true 2>/dev/null || true
kubectl delete clusterrolebinding jenkins-cross-namespace-reader --ignore-not-found=true 2>/dev/null || true
ok "Cluster RBAC removed"

# ── Step 4: Terraform destroy ─────────────────────────────────────────────────
banner "Step 4: Terraform Destroy — AWS Infrastructure"

TF_DIR="${PROJECT_DIR}/terraform"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
AWS_REGION="${AWS_REGION:-$(aws configure get region || echo 'us-east-1')}"

if [[ -d "${TF_DIR}" ]]; then
  info "Running terraform destroy..."
  cd "${TF_DIR}"
  terraform destroy \
    -var="aws_region=${AWS_REGION}" \
    -var="aws_account_id=${AWS_ACCOUNT_ID}" \
    -auto-approve
  ok "AWS infrastructure destroyed"
  cd "${PROJECT_DIR}"
else
  warn "Terraform directory not found at ${TF_DIR} — skipping"
fi

# ── Step 5: Clean up local kubeconfig ─────────────────────────────────────────
banner "Step 5: Cleaning Up Local State"

CLUSTER_NAME="chaos-platform"
if kubectl config get-contexts "${CLUSTER_NAME}" &>/dev/null; then
  kubectl config delete-context "${CLUSTER_NAME}" 2>/dev/null || true
  ok "Removed kubeconfig context: ${CLUSTER_NAME}"
fi

printf "\n${GREEN}Destroy complete.${NC}\n"
printf "${YELLOW}Note: S3 state bucket (chaos-platform-tf-state-${AWS_ACCOUNT_ID}) was intentionally preserved.${NC}\n"
printf "${YELLOW}Delete it manually if no longer needed: aws s3 rb s3://chaos-platform-tf-state-${AWS_ACCOUNT_ID} --force${NC}\n\n"
