#!/usr/bin/env bash
# run-load-test.sh — CLI wrapper to trigger a load test via the API.
#
# Usage: bash scripts/run-load-test.sh [options]
#
# Options:
#   -s, --scenario    Scenario type (smoke|stress|spike|soak) [default: smoke]
#   -u, --url         Target URL [default: http://localhost:8000]
#   -v, --users       Virtual users [default: 20]
#   -d, --duration    Duration in minutes [default: 5]
#   -e, --max-errors  Max error rate % before failing [default: 5]
#   -a, --api-url     Load tester API URL [default: http://localhost:8002]
#       --no-wait     Return immediately after starting test
#
# Examples:
#   bash scripts/run-load-test.sh -s stress -v 100 -d 10
#   bash scripts/run-load-test.sh -s smoke --no-wait

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }

# ── Defaults ──────────────────────────────────────────────────────────────────
SCENARIO="smoke"
TARGET_URL="${TARGET_URL:-http://localhost:8000}"
VUS=20
DURATION_MIN=5
MAX_ERR_PCT=5
API_URL="${LOADTEST_API_URL:-http://localhost:8002}"
WAIT=true

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--scenario)   SCENARIO="$2";     shift 2 ;;
    -u|--url)        TARGET_URL="$2";   shift 2 ;;
    -v|--users)      VUS="$2";          shift 2 ;;
    -d|--duration)   DURATION_MIN="$2"; shift 2 ;;
    -e|--max-errors) MAX_ERR_PCT="$2";  shift 2 ;;
    -a|--api-url)    API_URL="$2";      shift 2 ;;
    --no-wait)       WAIT=false;        shift ;;
    -h|--help)
      grep '^#' "$0" | head -20 | sed 's/^# \?//'
      exit 0 ;;
    *) err "Unknown argument: $1" ;;
  esac
done

VALID_SCENARIOS=(smoke stress spike soak)
if [[ ! " ${VALID_SCENARIOS[*]} " =~ " ${SCENARIO} " ]]; then
  err "Invalid scenario '${SCENARIO}'. Valid: ${VALID_SCENARIOS[*]}"
fi

DURATION_SEC=$(( DURATION_MIN * 60 ))
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
TEST_NAME="manual-${SCENARIO}-${TIMESTAMP}"

printf "\n${BLUE}Running load test${NC}\n"
printf "  Scenario:   ${SCENARIO}\n"
printf "  Target:     ${TARGET_URL}\n"
printf "  Users:      ${VUS}\n"
printf "  Duration:   ${DURATION_MIN}m\n"
printf "  Max errors: ${MAX_ERR_PCT}%%\n\n"

# ── Verify API reachable ──────────────────────────────────────────────────────
info "Checking load tester health..."
curl -sf --max-time 5 "${API_URL}/health" &>/dev/null || err "Cannot reach load tester at ${API_URL} — is port-forward running?"
ok "Load tester healthy"

# ── Create test ───────────────────────────────────────────────────────────────
info "Starting test: ${TEST_NAME}"

PAYLOAD=$(cat <<EOF
{
  "name": "${TEST_NAME}",
  "target_url": "${TARGET_URL}",
  "scenario_type": "${SCENARIO}",
  "virtual_users": ${VUS},
  "duration_seconds": ${DURATION_SEC},
  "ramp_strategy": "step"
}
EOF
)

RESP=$(curl -sf -X POST \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" \
  "${API_URL}/tests") || err "Failed to start load test"

TEST_ID=$(echo "${RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin)['test_id'])" 2>/dev/null) || \
  TEST_ID=$(echo "${RESP}" | grep -o '"test_id":"[^"]*"' | cut -d'"' -f4)

ok "Test started: ${TEST_ID}"

if [[ "${WAIT}" == "false" ]]; then
  printf "\n${GREEN}Test started (${TEST_ID}). Not waiting for completion.${NC}\n"
  printf "  Live stats: ${API_URL}/results/live/${TEST_ID}\n\n"
  exit 0
fi

# ── Stream live stats ─────────────────────────────────────────────────────────
printf "\n${BLUE}Live stats (polling every 5s)...${NC}\n"
printf "%-8s %-12s %-12s %-12s %-10s\n" "TIME" "RPS" "ERRORS" "P99_MS" "STATUS"
printf "%-8s %-12s %-12s %-12s %-10s\n" "────────" "────────────" "────────────" "────────────" "──────────"

MAX_WAIT=$(( DURATION_SEC + 120 ))
elapsed=0
FINAL_STATUS="unknown"

while [[ ${elapsed} -lt ${MAX_WAIT} ]]; do
  sleep 5; elapsed=$(( elapsed + 5 ))

  LIVE=$(curl -sf "${API_URL}/results/live/${TEST_ID}" 2>/dev/null || echo '{}')
  RPS=$(echo "${LIVE}"    | python3 -c "import sys,json; print(f\"{json.load(sys.stdin).get('requests_per_second',0):.1f}\")" 2>/dev/null || echo "0.0")
  ERRS=$(echo "${LIVE}"   | python3 -c "import sys,json; print(json.load(sys.stdin).get('failed_requests',0))" 2>/dev/null || echo "0")
  P99=$(echo "${LIVE}"    | python3 -c "import sys,json; print(json.load(sys.stdin).get('latency_p99_ms',0))" 2>/dev/null || echo "0")

  TEST_RESP=$(curl -sf "${API_URL}/tests/${TEST_ID}" 2>/dev/null || echo '{"status":"unknown"}')
  FINAL_STATUS=$(echo "${TEST_RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")

  printf "\r%-8s %-12s %-12s %-12s %-10s" "${elapsed}s" "${RPS}" "${ERRS}" "${P99}" "${FINAL_STATUS}"

  if [[ "${FINAL_STATUS}" =~ ^(completed|stopped|failed)$ ]]; then
    echo ""
    break
  fi
done

# ── Print results ─────────────────────────────────────────────────────────────
echo ""
FINAL_RESP=$(curl -sf "${API_URL}/tests/${TEST_ID}" 2>/dev/null || echo '{}')
ERR_RATE=$(echo "${FINAL_RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('summary',{}).get('error_rate_pct',0))" 2>/dev/null || echo "0")
PEAK_RPS=$(echo "${FINAL_RESP}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('summary',{}).get('peak_rps',0))" 2>/dev/null || echo "0")
TOTAL=$(echo "${FINAL_RESP}"    | python3 -c "import sys,json; print(json.load(sys.stdin).get('summary',{}).get('total_requests',0))" 2>/dev/null || echo "0")

printf "\n${BLUE}Results:${NC}\n"
printf "  Status:          ${FINAL_STATUS}\n"
printf "  Total requests:  ${TOTAL}\n"
printf "  Peak RPS:        ${PEAK_RPS}\n"
printf "  Error rate:      ${ERR_RATE}%%\n"
printf "  Full report:     ${API_URL}/tests/${TEST_ID}\n\n"

# ── Evaluate ──────────────────────────────────────────────────────────────────
ERR_RATE_INT=$(echo "${ERR_RATE}" | cut -d'.' -f1)
if [[ ${ERR_RATE_INT} -gt ${MAX_ERR_PCT} ]]; then
  err "FAILED — error rate ${ERR_RATE}% exceeds threshold ${MAX_ERR_PCT}%"
fi
ok "PASSED — error rate ${ERR_RATE}% within threshold ${MAX_ERR_PCT}%"
