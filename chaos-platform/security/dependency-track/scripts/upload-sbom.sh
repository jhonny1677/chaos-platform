#!/usr/bin/env bash
# upload-sbom.sh — Generate an SBOM with syft and upload to Dependency Track.
#
# Usage:
#   bash security/dependency-track/scripts/upload-sbom.sh \
#     --image ACCOUNT.dkr.ecr.REGION.amazonaws.com/chaos-platform/chaos-engine:abc1234 \
#     --project-name chaos-engine \
#     --project-version abc1234
#
# Prerequisites:
#   - syft CLI: curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh
#   - DT_API_KEY env var: API key from Dependency Track UI
#   - DT_API_URL env var: e.g., http://localhost:8080 (with port-forward active)
#   - AWS ECR credentials (for pulling the image to scan)
#
# What this does:
#   1. Pulls the Docker image
#   2. Generates a CycloneDX SBOM using syft (lists all dependencies + versions)
#   3. Uploads the SBOM to Dependency Track via REST API
#   4. Waits for analysis to complete and reports findings
#
# Why syft over docker sbom:
#   - syft supports more package ecosystems (pip, npm, go modules, java, etc.)
#   - Output is CycloneDX 1.4+ which DT supports natively
#   - Can scan both images and local filesystems

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }

IMAGE=""
PROJECT_NAME=""
PROJECT_VERSION="latest"
DT_API_URL="${DT_API_URL:-http://localhost:8080}"
DT_API_KEY="${DT_API_KEY:?DT_API_KEY env var required — get from DT UI: Settings → Teams → API Keys}"

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --image)           IMAGE="${2:?}"; shift 2;;
    --project-name)    PROJECT_NAME="${2:?}"; shift 2;;
    --project-version) PROJECT_VERSION="${2:?}"; shift 2;;
    --dt-url)          DT_API_URL="${2:?}"; shift 2;;
    *) err "Unknown argument: $1";;
  esac
done

[[ -z "${IMAGE}" ]]        && err "--image is required"
[[ -z "${PROJECT_NAME}" ]] && err "--project-name is required"

# ── Check prerequisites ───────────────────────────────────────────────────────
command -v syft   &>/dev/null || err "syft not found. Install: curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin"
command -v curl   &>/dev/null || err "curl not found"
command -v python3 &>/dev/null || err "python3 not found"

# ── Step 1: Generate SBOM ─────────────────────────────────────────────────────
SBOM_FILE="/tmp/sbom-${PROJECT_NAME}-${PROJECT_VERSION}.json"
info "Generating CycloneDX SBOM for ${IMAGE}..."
syft "${IMAGE}" -o cyclonedx-json > "${SBOM_FILE}"
SBOM_SIZE=$(wc -c < "${SBOM_FILE}")
ok "SBOM generated: ${SBOM_FILE} (${SBOM_SIZE} bytes)"

# ── Step 2: Get or create project in Dependency Track ────────────────────────
info "Looking up project '${PROJECT_NAME}' in Dependency Track..."
PROJECTS_RESPONSE=$(curl -sf \
  -H "X-Api-Key: ${DT_API_KEY}" \
  -H "Accept: application/json" \
  "${DT_API_URL}/api/v1/project?name=${PROJECT_NAME}&excludeInactive=true")

PROJECT_UUID=$(echo "${PROJECTS_RESPONSE}" | python3 -c "
import sys, json
projects = json.load(sys.stdin)
for p in projects:
    if p.get('name') == '${PROJECT_NAME}':
        print(p['uuid'])
        break
" 2>/dev/null || echo "")

if [[ -z "${PROJECT_UUID}" ]]; then
  info "Project not found — creating '${PROJECT_NAME}'..."
  CREATE_RESPONSE=$(curl -sf -X PUT \
    -H "X-Api-Key: ${DT_API_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"${PROJECT_NAME}\", \"version\": \"${PROJECT_VERSION}\", \"classifier\": \"APPLICATION\"}" \
    "${DT_API_URL}/api/v1/project")
  PROJECT_UUID=$(echo "${CREATE_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin)['uuid'])")
  ok "Project created: UUID=${PROJECT_UUID}"
else
  ok "Project found: UUID=${PROJECT_UUID}"
fi

# ── Step 3: Upload SBOM ───────────────────────────────────────────────────────
info "Uploading SBOM to Dependency Track..."
SBOM_B64=$(base64 -w0 "${SBOM_FILE}")

UPLOAD_RESPONSE=$(curl -sf -X PUT \
  -H "X-Api-Key: ${DT_API_KEY}" \
  -H "Content-Type: application/json" \
  -d "{
    \"projectName\": \"${PROJECT_NAME}\",
    \"projectVersion\": \"${PROJECT_VERSION}\",
    \"autoCreate\": true,
    \"bom\": \"${SBOM_B64}\"
  }" \
  "${DT_API_URL}/api/v1/bom")

TOKEN=$(echo "${UPLOAD_RESPONSE}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('token', ''))" 2>/dev/null || echo "")
ok "SBOM uploaded (analysis token: ${TOKEN})"

# ── Step 4: Wait for analysis to complete ────────────────────────────────────
if [[ -n "${TOKEN}" ]]; then
  info "Waiting for vulnerability analysis to complete..."
  MAX_WAIT=120
  ELAPSED=0
  while true; do
    STATUS=$(curl -sf \
      -H "X-Api-Key: ${DT_API_KEY}" \
      "${DT_API_URL}/api/v1/bom/token/${TOKEN}" | python3 -c "import sys,json; print(json.load(sys.stdin).get('processing', True))" 2>/dev/null || echo "true")
    if [[ "${STATUS}" == "False" ]]; then
      ok "Analysis complete"
      break
    fi
    if [[ ${ELAPSED} -ge ${MAX_WAIT} ]]; then
      info "Analysis still processing — check DT UI for results"
      break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
  done
fi

# ── Step 5: Report summary ────────────────────────────────────────────────────
rm -f "${SBOM_FILE}"
printf "\n${GREEN}SBOM upload complete!${NC}\n"
printf "  Project: ${PROJECT_NAME} @ ${PROJECT_VERSION}\n"
printf "  UUID:    ${PROJECT_UUID}\n"
printf "  View:    ${DT_API_URL}/projects/${PROJECT_UUID}\n\n"
printf "${YELLOW}Run check-vulnerabilities.sh to see findings${NC}\n\n"
