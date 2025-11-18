#!/usr/bin/env bash
# deploy.sh — Build, push, and deploy a single service.
#
# Usage: bash scripts/deploy.sh <service>
#   service: target-app | chaos-engine | load-tester | dashboard
#
# Example: bash scripts/deploy.sh chaos-engine

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SERVICE="${1:-}"

# ── Validate input ────────────────────────────────────────────────────────────
if [[ -z "${SERVICE}" ]]; then
  err "Usage: $0 <service>"
  err "Valid services: target-app chaos-engine load-tester dashboard"
  exit 1
fi

VALID_SERVICES=(target-app chaos-engine load-tester dashboard)
if [[ ! " ${VALID_SERVICES[*]} " =~ " ${SERVICE} " ]]; then
  err "Unknown service: ${SERVICE}"
  err "Valid services: ${VALID_SERVICES[*]}"
  exit 1
fi

SERVICE_DIR="${PROJECT_DIR}/${SERVICE}"
if [[ ! -d "${SERVICE_DIR}" ]]; then
  err "Service directory not found: ${SERVICE_DIR}"
  exit 1
fi

# ── Resolve AWS config ────────────────────────────────────────────────────────
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
AWS_REGION="${AWS_REGION:-$(aws configure get region || echo 'us-east-1')}"
ECR_REGISTRY="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
ECR_REPO="${ECR_REGISTRY}/chaos-platform/${SERVICE}"
GIT_SHA=$(git -C "${PROJECT_DIR}" rev-parse --short HEAD 2>/dev/null || echo "local")

printf "\n${BLUE}Deploying ${SERVICE} (${GIT_SHA})${NC}\n\n"

# ── Step 1: Build Docker image ────────────────────────────────────────────────
info "Building Docker image..."
docker build \
  --label "org.opencontainers.image.revision=${GIT_SHA}" \
  --label "org.opencontainers.image.created=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  -t "${ECR_REPO}:${GIT_SHA}" \
  -t "${ECR_REPO}:latest" \
  "${SERVICE_DIR}/"
ok "Image built: ${ECR_REPO}:${GIT_SHA}"

# ── Step 2: Push to ECR ───────────────────────────────────────────────────────
info "Logging in to ECR..."
aws ecr get-login-password --region "${AWS_REGION}" | \
  docker login --username AWS --password-stdin "${ECR_REGISTRY}"

info "Pushing image to ECR..."
docker push "${ECR_REPO}:${GIT_SHA}"
docker push "${ECR_REPO}:latest"
ok "Pushed: ${ECR_REPO}:${GIT_SHA}"

# ── Step 3: Update k8s manifest ───────────────────────────────────────────────
MANIFEST="${SERVICE_DIR}/k8s/deployment.yaml"
if [[ -f "${MANIFEST}" ]]; then
  info "Updating image tag in ${MANIFEST}..."
  sed -i.bak "s|image: .*${SERVICE}.*|image: ${ECR_REPO}:${GIT_SHA}|g" "${MANIFEST}"
  rm -f "${MANIFEST}.bak"
  ok "Manifest updated to ${GIT_SHA}"
else
  warn "deployment.yaml not found at ${MANIFEST} — skipping manifest update"
fi

# ── Step 4: Wait for ArgoCD to sync ───────────────────────────────────────────
if command -v argocd &>/dev/null; then
  info "Triggering ArgoCD sync for ${SERVICE}..."
  argocd app sync "${SERVICE}" --timeout 120 2>/dev/null && ok "ArgoCD synced" || warn "ArgoCD sync failed or timed out — check ArgoCD UI"

  info "Waiting for ArgoCD health check to pass..."
  argocd app wait "${SERVICE}" --health --timeout 180 2>/dev/null && ok "${SERVICE} healthy" || warn "Health check pending — check ArgoCD UI"
else
  warn "argocd CLI not found — apply manifest manually: kubectl apply -f ${MANIFEST}"
fi

# ── Step 5: Verify deployment ─────────────────────────────────────────────────
info "Verifying deployment..."
NAMESPACE_MAP=(
  "target-app:target-app"
  "chaos-engine:chaos-engine"
  "load-tester:load-tester"
  "dashboard:chaos-engine"
)
for entry in "${NAMESPACE_MAP[@]}"; do
  svc="${entry%%:*}"; ns="${entry##*:}"
  if [[ "${svc}" == "${SERVICE}" ]]; then
    kubectl rollout status deployment/"${SERVICE}" -n "${ns}" --timeout=120s && ok "Rollout complete" || warn "Rollout pending"
    break
  fi
done

# ── Run health check ──────────────────────────────────────────────────────────
info "Running health check..."
bash "${SCRIPT_DIR}/health-check.sh" "${SERVICE}" && ok "Health check passed" || warn "Health check failed — investigate"

printf "\n${GREEN}Deploy complete: ${SERVICE}:${GIT_SHA}${NC}\n\n"
