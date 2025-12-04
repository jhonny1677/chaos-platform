#!/usr/bin/env bash
# check-vulnerabilities.sh — Query Dependency Track for vulnerability findings.
#
# Usage:
#   bash security/dependency-track/scripts/check-vulnerabilities.sh \
#     --project-name chaos-engine \
#     --min-severity HIGH \
#     [--fail-on-critical]
#
# Options:
#   --project-name   Name of the project in Dependency Track
#   --min-severity   Minimum severity to report: CRITICAL|HIGH|MEDIUM|LOW|INFO
#   --fail-on-critical  Exit with code 1 if any CRITICAL CVEs found (for CI gating)
#
# Prerequisites:
#   - DT_API_KEY env var set
#   - DT_API_URL env var set (default: http://localhost:8080)

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }

PROJECT_NAME=""
MIN_SEVERITY="HIGH"
FAIL_ON_CRITICAL=false
DT_API_URL="${DT_API_URL:-http://localhost:8080}"
DT_API_KEY="${DT_API_KEY:?DT_API_KEY env var required}"

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --project-name)    PROJECT_NAME="${2:?}"; shift 2;;
    --min-severity)    MIN_SEVERITY="${2:?}"; shift 2;;
    --fail-on-critical) FAIL_ON_CRITICAL=true; shift;;
    --dt-url)          DT_API_URL="${2:?}"; shift 2;;
    *) err "Unknown argument: $1";;
  esac
done

[[ -z "${PROJECT_NAME}" ]] && err "--project-name is required"

# ── Get project UUID ──────────────────────────────────────────────────────────
info "Looking up project '${PROJECT_NAME}'..."
PROJECTS=$(curl -sf \
  -H "X-Api-Key: ${DT_API_KEY}" \
  -H "Accept: application/json" \
  "${DT_API_URL}/api/v1/project?name=${PROJECT_NAME}")

PROJECT_UUID=$(echo "${PROJECTS}" | python3 -c "
import sys, json
projects = json.load(sys.stdin)
for p in projects:
    if p.get('name') == '${PROJECT_NAME}':
        print(p['uuid'])
        break
" 2>/dev/null || echo "")

[[ -z "${PROJECT_UUID}" ]] && err "Project '${PROJECT_NAME}' not found in Dependency Track"
ok "Project UUID: ${PROJECT_UUID}"

# ── Get vulnerability findings ────────────────────────────────────────────────
info "Fetching vulnerability findings..."
FINDINGS=$(curl -sf \
  -H "X-Api-Key: ${DT_API_KEY}" \
  -H "Accept: application/json" \
  "${DT_API_URL}/api/v1/finding/project/${PROJECT_UUID}?suppressed=false")

SEVERITY_ORDER="CRITICAL HIGH MEDIUM LOW INFO UNASSIGNED"

# Parse and display findings per severity
CRITICAL_COUNT=0
HIGH_COUNT=0
MEDIUM_COUNT=0

SUMMARY=$(echo "${FINDINGS}" | python3 - <<'PYEOF'
import sys, json

findings = json.load(sys.stdin)
severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "UNASSIGNED"]
by_severity = {s: [] for s in severity_order}

for f in findings:
    vuln = f.get("vulnerability", {})
    sev = vuln.get("severity", "UNASSIGNED").upper()
    by_severity.setdefault(sev, []).append({
        "id":          vuln.get("vulnId", "N/A"),
        "component":   f.get("component", {}).get("name", "unknown"),
        "version":     f.get("component", {}).get("version", ""),
        "description": vuln.get("title", vuln.get("description", ""))[:80],
    })

counts = {s: len(v) for s, v in by_severity.items()}
print(f"CRITICAL:{counts['CRITICAL']} HIGH:{counts['HIGH']} MEDIUM:{counts['MEDIUM']} LOW:{counts['LOW']}")

for sev in severity_order:
    items = by_severity[sev]
    if not items:
        continue
    print(f"\n{'─'*60}")
    print(f"  {sev} ({len(items)} findings)")
    print(f"{'─'*60}")
    for item in items[:10]:  # show max 10 per severity
        print(f"  {item['id']:<18} {item['component']}:{item['version']}")
        if item['description']:
            print(f"    {item['description']}")
PYEOF
)

FIRST_LINE=$(echo "${SUMMARY}" | head -1)
CRITICAL_COUNT=$(echo "${FIRST_LINE}" | grep -oP 'CRITICAL:\K\d+')
HIGH_COUNT=$(echo "${FIRST_LINE}" | grep -oP 'HIGH:\K\d+')
MEDIUM_COUNT=$(echo "${FIRST_LINE}" | grep -oP 'MEDIUM:\K\d+')

printf "\n${BLUE}Vulnerability Summary: ${PROJECT_NAME}${NC}\n"
echo "${SUMMARY}" | tail -n +2

printf "\n${BLUE}Totals:${NC}\n"
printf "  ${RED}CRITICAL: ${CRITICAL_COUNT}${NC}\n"
printf "  ${YELLOW}HIGH:     ${HIGH_COUNT}${NC}\n"
printf "  MEDIUM:   ${MEDIUM_COUNT}\n"
printf "\n  View full report: ${DT_API_URL}/projects/${PROJECT_UUID}\n\n"

# ── CI gate ───────────────────────────────────────────────────────────────────
if [[ "${FAIL_ON_CRITICAL}" == "true" ]] && [[ "${CRITICAL_COUNT}" -gt 0 ]]; then
  err "Build FAILED: ${CRITICAL_COUNT} CRITICAL vulnerability(ies) found in ${PROJECT_NAME}. Update the affected dependencies."
fi

if [[ "${CRITICAL_COUNT}" -eq 0 ]] && [[ "${HIGH_COUNT}" -eq 0 ]]; then
  ok "No CRITICAL or HIGH vulnerabilities found"
else
  warn "${CRITICAL_COUNT} CRITICAL, ${HIGH_COUNT} HIGH vulnerabilities require review"
fi
