#!/usr/bin/env bash
# port-forward.sh — Background port-forwards for all chaos platform services.
# Run once, then access services on localhost.
#
# Usage: bash scripts/port-forward.sh [stop]
#   stop: kill all active port-forwards started by this script

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }

PID_FILE="/tmp/chaos-platform-port-forwards.pids"
ACTION="${1:-start}"

# ── Stop existing port-forwards ───────────────────────────────────────────────
stop_forwards() {
  if [[ -f "${PID_FILE}" ]]; then
    info "Stopping existing port-forwards..."
    while IFS= read -r pid; do
      kill "${pid}" 2>/dev/null && ok "Stopped PID ${pid}" || true
    done < "${PID_FILE}"
    rm -f "${PID_FILE}"
    ok "All port-forwards stopped"
  else
    info "No active port-forwards found (${PID_FILE} missing)"
  fi
}

if [[ "${ACTION}" == "stop" ]]; then
  stop_forwards
  exit 0
fi

# Kill any existing forwards before starting new ones
stop_forwards 2>/dev/null || true

# ── Helper: start one port-forward in background ──────────────────────────────
fwd() {
  local name="$1" namespace="$2" resource="$3" local_port="$4" remote_port="$5"

  # Check if the resource exists before trying to forward
  if ! kubectl get "${resource%/*}" "${resource##*/}" -n "${namespace}" &>/dev/null 2>&1; then
    printf "${YELLOW}  ⚠ ${name}: not found in namespace ${namespace} — skipping${NC}\n"
    return
  fi

  kubectl port-forward "${resource}" "${local_port}:${remote_port}" -n "${namespace}" &>/dev/null &
  local pid=$!
  echo "${pid}" >> "${PID_FILE}"
  ok "${name}: localhost:${local_port} → ${namespace}/${resource}:${remote_port} (PID ${pid})"
}

# ── Start port-forwards ───────────────────────────────────────────────────────
printf "\n${BLUE}Starting port-forwards for all chaos platform services...${NC}\n\n"

# Application services
fwd "Target App"   "target-app"   "svc/target-app"   8000 8000
fwd "Chaos Engine" "chaos-engine" "svc/chaos-engine" 8001 8001
fwd "Load Tester"  "load-tester"  "svc/load-tester"  8002 8002
fwd "Dashboard"    "chaos-engine" "svc/dashboard"    3001 8080

# Infrastructure / ops
fwd "ArgoCD"    "argocd"     "svc/argocd-server"      8080 80
fwd "Jenkins"   "jenkins"    "svc/jenkins"            8090 8080
fwd "Grafana"   "monitoring" "svc/prometheus-grafana" 3000 80
fwd "Prometheus" "monitoring" "svc/prometheus-operated" 9090 9090
fwd "Vault"     "vault"      "svc/vault"              8200 8200

# Kafka UI (if deployed)
fwd "Kafka UI" "kafka" "svc/kafka-ui" 9000 8080 2>/dev/null || true

printf "\n${GREEN}Port-forwards active. Access services at:${NC}\n"
printf "  Dashboard:   http://localhost:3001\n"
printf "  Target App:  http://localhost:8000\n"
printf "  Chaos API:   http://localhost:8001\n"
printf "  Load Tester: http://localhost:8002\n"
printf "  ArgoCD:      http://localhost:8080\n"
printf "  Jenkins:     http://localhost:8090\n"
printf "  Grafana:     http://localhost:3000\n"
printf "  Prometheus:  http://localhost:9090\n"
printf "  Vault:       http://localhost:8200\n"
printf "\n${YELLOW}To stop all: bash scripts/port-forward.sh stop${NC}\n"
printf "${YELLOW}PIDs saved to: ${PID_FILE}${NC}\n\n"
