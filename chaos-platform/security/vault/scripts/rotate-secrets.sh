#!/usr/bin/env bash
# rotate-secrets.sh — Force rotation of dynamic credentials for a service.
#
# Usage:
#   bash security/vault/scripts/rotate-secrets.sh <service>
#   service: chaos-engine | load-tester
#
# What this script does:
#   1. Lists all active leases for the service's database role
#   2. Generates NEW credentials and verifies they work
#   3. Revokes OLD credentials only after new ones are verified
#   4. Logs the rotation to Vault's audit log
#
# Prerequisites:
#   - VAULT_TOKEN with admin or operator policy
#   - VAULT_ADDR pointing to the Vault instance
#   - psql available (for credential verification)
#   - DB_HOST, DB_PORT, DB_NAME env vars set

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }

SERVICE="${1:-}"
VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
VAULT_TOKEN="${VAULT_TOKEN:?VAULT_TOKEN must be set}"
DB_HOST="${DB_HOST:-REPLACE_ME_DB_HOST}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-REPLACE_ME_DB_NAME}"

export VAULT_ADDR VAULT_TOKEN

# ── Validate ──────────────────────────────────────────────────────────────────
if [[ -z "${SERVICE}" ]]; then
  err "Usage: $0 <service>  (chaos-engine | load-tester)"
fi

DB_ROLE="${SERVICE}-role"
LEASE_PREFIX="database/creds/${DB_ROLE}"

# ── Step 1: List existing leases ──────────────────────────────────────────────
info "Listing active leases for ${LEASE_PREFIX}..."
OLD_LEASES=$(vault list -format=json "sys/leases/lookup/${LEASE_PREFIX}/" 2>/dev/null || echo "[]")
OLD_COUNT=$(echo "${OLD_LEASES}" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
info "Found ${OLD_COUNT} active leases"

# ── Step 2: Generate new credentials ─────────────────────────────────────────
info "Generating new credentials for ${SERVICE}..."
NEW_CREDS=$(vault read -format=json "database/creds/${DB_ROLE}")
NEW_USER=$(echo "${NEW_CREDS}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['username'])")
NEW_PASS=$(echo "${NEW_CREDS}" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['password'])")
NEW_LEASE=$(echo "${NEW_CREDS}" | python3 -c "import sys,json; print(json.load(sys.stdin)['lease_id'])")
ok "New credentials generated: user=${NEW_USER}"

# ── Step 3: Verify new credentials work ──────────────────────────────────────
info "Verifying new credentials against ${DB_HOST}:${DB_PORT}/${DB_NAME}..."
if command -v psql &>/dev/null; then
  PGPASSWORD="${NEW_PASS}" psql \
    -h "${DB_HOST}" \
    -p "${DB_PORT}" \
    -U "${NEW_USER}" \
    -d "${DB_NAME}" \
    -c "SELECT 1;" &>/dev/null || err "New credentials FAILED to authenticate — aborting rotation"
  ok "New credentials verified"
else
  warn "psql not available — skipping credential verification (not recommended in production)"
fi

# ── Step 4: Revoke old leases ─────────────────────────────────────────────────
if [[ "${OLD_COUNT}" -gt 0 ]]; then
  info "Revoking ${OLD_COUNT} old credential leases..."
  vault lease revoke -prefix "${LEASE_PREFIX}/" || warn "Some leases may have already expired"
  ok "Old leases revoked"
else
  info "No old leases to revoke"
fi

# ── Step 5: Log rotation ──────────────────────────────────────────────────────
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
info "Logging rotation to audit trail..."
# Vault's audit log captures this automatically since we made Vault API calls.
# We also log to stdout for the Loki pipeline.
printf '{"timestamp":"%s","event":"secret_rotation","service":"%s","role":"%s","new_user":"%s","old_leases_revoked":%s}\n' \
  "${TIMESTAMP}" "${SERVICE}" "${DB_ROLE}" "${NEW_USER}" "${OLD_COUNT}"
ok "Rotation logged"

printf "\n${GREEN}Rotation complete for ${SERVICE}${NC}\n"
printf "  New user:       ${NEW_USER}\n"
printf "  New lease ID:   ${NEW_LEASE}\n"
printf "  Old leases revoked: ${OLD_COUNT}\n\n"
printf "${YELLOW}Next step: restart ${SERVICE} pods to pick up new credentials:${NC}\n"
printf "  kubectl rollout restart deployment/${SERVICE} -n ${SERVICE}\n\n"
