#!/usr/bin/env bash
# run-experiment.sh — CLI wrapper to trigger a chaos experiment via the API.
#
# Usage: bash scripts/run-experiment.sh [options]
#
# Options:
#   -t, --type        Experiment type (pod_kill|network_delay|cpu_stress|memory_stress) [default: pod_kill]
#   -n, --namespace   Target namespace [default: target-app]
#   -d, --duration    Duration in minutes [default: 5]
#   -p, --percentage  Kill/stress percentage [default: 30]
#   -a, --api-url     Chaos engine API URL [default: http://localhost:8001]
#       --wait        Wait for experiment to complete and print results [default: true]
#       --no-wait     Return immediately after creating experiment
#
# Example: bash scripts/run-experiment.sh -t network_delay -n target-app -d 10

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }

# ── Defaults ──────────────────────────────────────────────────────────────────
EXP_TYPE="pod_kill"
TARGET_NS="target-app"
DURATION_MIN="5"
PERCENTAGE="30"
API_URL="${CHAOS_API_URL:-http://localhost:8001}"
WAIT=true

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -t|--type)        EXP_TYPE="$2";    shift 2 ;;
    -n|--namespace)   TARGET_NS="$2";   shift 2 ;;
    -d|--duration)    DURATION_MIN="$2"; shift 2 ;;
    -p|--percentage)  PERCENTAGE="$2";  shift 2 ;;
    -a|--api-url)     API_URL="$2";     shift 2 ;;
    --wait)           WAIT=true;        shift ;;
    --no-wait)        WAIT=false;       shift ;;
    -h|--help)
      grep '^#' "$0" | head -20 | sed 's/^# \?//'
      exit 0 ;;
    *) err "Unknown argument: $1" ;;
  esac
done

# ── Validate type ─────────────────────────────────────────────────────────────
VALID_TYPES=(pod_kill network_delay cpu_stress memory_stress)
if [[ ! " ${VALID_TYPES[*]} " =~ " ${EXP_TYPE} " ]]; then
  err "Invalid type '${EXP_TYPE}'. Valid: ${VALID_TYPES[*]}"
fi

DURATION_SEC=$(( DURATION_MIN * 60 ))
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
EXP_NAME="manual-${EXP_TYPE}-${TIMESTAMP}"

printf "\n${BLUE}Running chaos experiment${NC}\n"
printf "  Type:      ${EXP_TYPE}\n"
printf "  Namespace: ${TARGET_NS}\n"
printf "  Duration:  ${DURATION_MIN}m\n"
printf "  Level:     ${PERCENTAGE}%%\n\n"

# ── Verify API reachable ──────────────────────────────────────────────────────
info "Checking chaos engine health..."
HEALTH=$(curl -sf --max-time 5 "${API_URL}/health" 2>/dev/null) || err "Cannot reach chaos engine at ${API_URL} — is port-forward running?"
ok "Chaos engine healthy"

# ── Create experiment ─────────────────────────────────────────────────────────
info "Creating experiment: ${EXP_NAME}"

PAYLOAD=$(cat <<EOF
{
  "name": "${EXP_NAME}",
  "description": "Manual run via run-experiment.sh",
  "chaos_type": "${EXP_TYPE}",
  "target_namespace": "${TARGET_NS}",
  "target_label_selector": "app=${TARGET_NS}",
  "parameters": {
    "kill_percentage": ${PERCENTAGE},
    "stress_percentage": ${PERCENTAGE},
    "delay_ms": 200
  },
  "steady_state_thresholds": {
    "error_rate_percent": 5.0,
    "latency_p99_ms": 2000,
    "min_ready_pods": 1
  }
}
EOF
)

RESP=$(curl -sf -X POST \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" \
  "${API_URL}/experiments") || err "Failed to create experiment"

EXP_ID=$(echo "${RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin)['experiment_id'])" 2>/dev/null) || \
  EXP_ID=$(echo "${RESP}" | grep -o '"experiment_id":"[^"]*"' | cut -d'"' -f4)

ok "Experiment created: ${EXP_ID}"
info "Track at: ${API_URL}/experiments/${EXP_ID}"

# ── Wait for completion ───────────────────────────────────────────────────────
if [[ "${WAIT}" == "true" ]]; then
  printf "\n${BLUE}Polling until experiment completes (Ctrl+C to stop polling)...${NC}\n"
  MAX_WAIT=$(( DURATION_SEC + 120 ))  # timeout = duration + 2 min buffer
  elapsed=0

  while [[ ${elapsed} -lt ${MAX_WAIT} ]]; do
    sleep 10; elapsed=$(( elapsed + 10 ))
    STATUS_RESP=$(curl -sf "${API_URL}/experiments/${EXP_ID}" 2>/dev/null) || { warn "API unreachable, retrying..."; continue; }
    STATUS=$(echo "${STATUS_RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")

    printf "\r  [%3ds] Status: %-12s" "${elapsed}" "${STATUS}"

    if [[ "${STATUS}" =~ ^(completed|failed|aborted)$ ]]; then
      echo ""
      HYPO=$(echo "${STATUS_RESP}"   | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result_summary',{}).get('hypothesis_passed','N/A'))" 2>/dev/null || echo "N/A")
      RECV=$(echo "${STATUS_RESP}"   | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('result_summary',{}).get('recovery_time_seconds','N/A'))" 2>/dev/null || echo "N/A")
      break
    fi
  done

  printf "\n\n${BLUE}Results:${NC}\n"
  printf "  Status:           ${STATUS}\n"
  printf "  Hypothesis passed: ${HYPO}\n"
  printf "  Recovery time:     ${RECV}s\n"
  printf "  Details:          ${API_URL}/experiments/${EXP_ID}\n\n"

  if [[ "${STATUS}" == "completed" && "${HYPO}" == "True" ]]; then
    ok "Experiment PASSED — system is resilient"
    exit 0
  elif [[ "${STATUS}" == "completed" && "${HYPO}" == "False" ]]; then
    warn "Experiment completed — hypothesis FAILED (system did not meet steady-state)"
    exit 1
  else
    err "Experiment ${STATUS}"
  fi
fi

printf "\n${GREEN}Experiment started (${EXP_ID}). Not waiting for completion.${NC}\n\n"
