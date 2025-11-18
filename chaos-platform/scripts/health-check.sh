#!/usr/bin/env bash
# health-check.sh — Check health of all (or one specific) chaos platform services.
# Prints a pass/fail table. Exits 0 if all services pass, 1 if any fail.
#
# Usage: bash scripts/health-check.sh [service]
#   service: optional — check only this service (target-app|chaos-engine|load-tester|dashboard)
#   No argument: check all services

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'

ONLY_SERVICE="${1:-all}"
FAILED=0

# ── Helper: HTTP health check ─────────────────────────────────────────────────
check_http() {
  local name="$1" url="$2" expect_field="${3:-status}"
  local resp
  resp=$(curl -sf --max-time 5 "${url}" 2>/dev/null) && \
    echo "${resp}" | python3 -c "import sys,json; d=json.load(sys.stdin); exit(0 if d.get('${expect_field}') else 0)" 2>/dev/null && \
    printf "${GREEN}  PASS  ${NC}%-20s %s\n" "${name}" "${url}" || \
    { printf "${RED}  FAIL  ${NC}%-20s %s\n" "${name}" "${url}"; FAILED=$(( FAILED + 1 )); }
}

# ── Helper: Kubernetes deployment check ───────────────────────────────────────
check_deploy() {
  local name="$1" namespace="$2" deploy="$3"
  local ready total
  if kubectl get deployment "${deploy}" -n "${namespace}" &>/dev/null 2>&1; then
    ready=$(kubectl get deployment "${deploy}" -n "${namespace}" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo "0")
    total=$(kubectl get deployment "${deploy}" -n "${namespace}" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")
    ready="${ready:-0}"
    if [[ "${ready}" -ge 1 ]]; then
      printf "${GREEN}  PASS  ${NC}%-20s %s/%s pods ready (ns: %s)\n" "${name}" "${ready}" "${total}" "${namespace}"
    else
      printf "${RED}  FAIL  ${NC}%-20s 0/%s pods ready (ns: %s)\n" "${name}" "${total}" "${namespace}"
      FAILED=$(( FAILED + 1 ))
    fi
  else
    printf "${YELLOW}  SKIP  ${NC}%-20s deployment not found (ns: %s)\n" "${name}" "${namespace}"
  fi
}

# ── Service definitions ───────────────────────────────────────────────────────
TARGET_APP_URL="${TARGET_URL:-http://localhost:8000}"
CHAOS_API_URL="${CHAOS_API_URL:-http://localhost:8001}"
LOADTEST_URL="${LOADTEST_API_URL:-http://localhost:8002}"
DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:3001}"

printf "\n${BLUE}════════════════════════════════════════════════════${NC}\n"
printf "${BLUE}  Chaos Platform Health Check${NC}\n"
printf "${BLUE}════════════════════════════════════════════════════${NC}\n"
printf "  %-6s %-20s %s\n" "STATUS" "SERVICE" "ENDPOINT / DETAILS"
printf "  %-6s %-20s %s\n" "──────" "────────────────────" "──────────────────────────────────"

run_all=true
[[ "${ONLY_SERVICE}" != "all" ]] && run_all=false

# ── Application APIs ──────────────────────────────────────────────────────────
printf "\n${BLUE}Application APIs:${NC}\n"

if ${run_all} || [[ "${ONLY_SERVICE}" == "target-app" ]]; then
  check_http "target-app"    "${TARGET_APP_URL}/health"     "status"
  check_http "target-app /api" "${TARGET_APP_URL}/api/products" "products"
  check_deploy "target-app (k8s)" "target-app" "target-app"
fi

if ${run_all} || [[ "${ONLY_SERVICE}" == "chaos-engine" ]]; then
  check_http "chaos-engine"  "${CHAOS_API_URL}/health"      "status"
  check_http "chaos metrics" "${CHAOS_API_URL%:*}:9091/metrics" "contentLength"
  check_deploy "chaos-engine (k8s)" "chaos-engine" "chaos-engine"
fi

if ${run_all} || [[ "${ONLY_SERVICE}" == "load-tester" ]]; then
  check_http "load-tester"   "${LOADTEST_URL}/health"       "status"
  check_deploy "load-tester (k8s)" "load-tester" "load-tester"
fi

if ${run_all} || [[ "${ONLY_SERVICE}" == "dashboard" ]]; then
  check_http "dashboard"     "${DASHBOARD_URL}/"            "contentLength"
  check_deploy "dashboard (k8s)" "chaos-engine" "dashboard"
fi

# ── Infrastructure (only when checking all) ───────────────────────────────────
if ${run_all}; then
  printf "\n${BLUE}Infrastructure:${NC}\n"
  check_http "argocd"    "http://localhost:8080/healthz"    "status"   2>/dev/null || true
  check_http "grafana"   "http://localhost:3000/api/health" "database" 2>/dev/null || true
  check_http "prometheus" "http://localhost:9090/-/healthy" "status"   2>/dev/null || true

  printf "\n${BLUE}Kubernetes Nodes:${NC}\n"
  if kubectl get nodes &>/dev/null 2>&1; then
    TOTAL=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
    READY=$(kubectl get nodes --no-headers 2>/dev/null | grep -c ' Ready ' || echo "0")
    if [[ "${READY}" == "${TOTAL}" ]]; then
      printf "${GREEN}  PASS  ${NC}%-20s %s/%s nodes Ready\n" "EKS cluster" "${READY}" "${TOTAL}"
    else
      printf "${RED}  FAIL  ${NC}%-20s %s/%s nodes Ready\n" "EKS cluster" "${READY}" "${TOTAL}"
      FAILED=$(( FAILED + 1 ))
    fi
  else
    printf "${YELLOW}  SKIP  ${NC}%-20s kubectl not configured or unreachable\n" "EKS cluster"
  fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────
printf "\n${BLUE}════════════════════════════════════════════════════${NC}\n"
if [[ ${FAILED} -eq 0 ]]; then
  printf "${GREEN}  All health checks PASSED${NC}\n"
else
  printf "${RED}  ${FAILED} health check(s) FAILED${NC}\n"
fi
printf "${BLUE}════════════════════════════════════════════════════${NC}\n\n"

exit ${FAILED}
