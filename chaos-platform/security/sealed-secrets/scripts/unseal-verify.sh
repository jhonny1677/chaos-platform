#!/usr/bin/env bash
# unseal-verify.sh — Verify a SealedSecret by applying it and reading the result.
#
# Usage:
#   bash security/sealed-secrets/scripts/unseal-verify.sh <sealed-secret.yaml>
#
# What this does:
#   1. Applies the SealedSecret to the cluster
#   2. Waits for the Sealed Secrets controller to decrypt it
#   3. Reads back the resulting K8s Secret and lists its keys (NOT values)
#   4. Optionally verifies specific keys exist
#
# NOTE: This script does NOT print secret values — it only confirms keys exist.
#       This is safe to run in CI.

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }

SEALED_SECRET_FILE="${1:-}"
[[ -z "${SEALED_SECRET_FILE}" ]] && err "Usage: $0 <sealed-secret.yaml>"
[[ -f "${SEALED_SECRET_FILE}" ]] || err "File not found: ${SEALED_SECRET_FILE}"

# ── Extract metadata from the SealedSecret file ───────────────────────────────
SECRET_NAME=$(grep -m1 "^  name:" "${SEALED_SECRET_FILE}" | awk '{print $2}')
SECRET_NAMESPACE=$(grep -m1 "^  namespace:" "${SEALED_SECRET_FILE}" | awk '{print $2}')

[[ -z "${SECRET_NAME}" ]]      && err "Could not parse secret name from ${SEALED_SECRET_FILE}"
[[ -z "${SECRET_NAMESPACE}" ]] && err "Could not parse namespace from ${SEALED_SECRET_FILE}"

info "Verifying SealedSecret: ${SECRET_NAME} in namespace ${SECRET_NAMESPACE}"

# ── Apply the SealedSecret ────────────────────────────────────────────────────
info "Applying SealedSecret..."
kubectl apply -f "${SEALED_SECRET_FILE}"
ok "SealedSecret applied"

# ── Wait for the controller to decrypt it ─────────────────────────────────────
info "Waiting for Secret '${SECRET_NAME}' to appear (controller decrypts asynchronously)..."
TIMEOUT=60
ELAPSED=0
until kubectl get secret "${SECRET_NAME}" -n "${SECRET_NAMESPACE}" &>/dev/null; do
  if [[ ${ELAPSED} -ge ${TIMEOUT} ]]; then
    err "Timed out after ${TIMEOUT}s waiting for Secret '${SECRET_NAME}' to appear"
  fi
  sleep 2
  ELAPSED=$((ELAPSED + 2))
done
ok "Secret appeared after ${ELAPSED}s"

# ── List keys (not values) ────────────────────────────────────────────────────
info "Keys present in the decrypted Secret:"
kubectl get secret "${SECRET_NAME}" -n "${SECRET_NAMESPACE}" \
  -o go-template='{{range $k,$v := .data}}  - {{$k}}{{"\n"}}{{end}}'

# ── Verify Secret is owned by the SealedSecret ───────────────────────────────
OWNER=$(kubectl get secret "${SECRET_NAME}" -n "${SECRET_NAMESPACE}" \
  -o jsonpath='{.metadata.ownerReferences[0].kind}' 2>/dev/null || echo "")

if [[ "${OWNER}" == "SealedSecret" ]]; then
  ok "Secret is owned by the SealedSecret controller (will be auto-deleted if SealedSecret is deleted)"
else
  warn "Secret is NOT owned by SealedSecret — it may have been created manually"
fi

# ── Check age ─────────────────────────────────────────────────────────────────
CREATED=$(kubectl get secret "${SECRET_NAME}" -n "${SECRET_NAMESPACE}" \
  -o jsonpath='{.metadata.creationTimestamp}' 2>/dev/null || echo "unknown")
info "Secret created at: ${CREATED}"

printf "\n${GREEN}Verification complete!${NC}\n"
printf "  Secret '${SECRET_NAME}' in '${SECRET_NAMESPACE}' is present and decrypted.\n"
printf "  Key count: $(kubectl get secret '${SECRET_NAME}' -n '${SECRET_NAMESPACE}' -o json | python3 -c 'import sys,json; print(len(json.load(sys.stdin)[\"data\"]))')\n"
printf "\n${YELLOW}REMINDER: Never kubectl describe or kubectl get -o json this secret in CI logs.${NC}\n\n"
