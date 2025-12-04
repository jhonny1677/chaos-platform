#!/usr/bin/env bash
# init-vault.sh — Initialize Vault for the first time and store unseal keys safely.
#
# Usage: bash security/vault/scripts/init-vault.sh
#
# Prerequisites:
#   - kubectl configured for the target cluster
#   - Vault pods running: kubectl get pods -n vault
#   - vault CLI installed
#
# What this script does:
#   1. Initializes Vault with 5 key shares, 3 required to unseal
#   2. Stores all unseal keys and root token as Kubernetes Secrets
#   3. Unseals Vault using 3 of the 5 keys
#   4. Prints manual backup instructions
#
# ⚠️  CRITICAL: Print and store the unseal keys and root token OFFLINE
#     (printed paper in a safe, hardware password manager) BEFORE deleting
#     the K8s Secrets that hold them. Losing all unseal keys = permanent
#     data loss — there is no recovery.

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }

VAULT_NAMESPACE="vault"
VAULT_POD="vault-0"
VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"

# ── Step 1: Wait for Vault to be running ──────────────────────────────────────
info "Waiting for Vault pod to be ready..."
kubectl wait pod/"${VAULT_POD}" -n "${VAULT_NAMESPACE}" \
  --for=condition=Ready --timeout=120s
ok "Vault pod is ready"

# ── Step 2: Check if already initialized ─────────────────────────────────────
info "Checking Vault initialization status..."
INIT_STATUS=$(kubectl exec -n "${VAULT_NAMESPACE}" "${VAULT_POD}" -- \
  vault status -format=json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('initialized', False))" 2>/dev/null || echo "false")

if [[ "${INIT_STATUS}" == "True" ]]; then
  warn "Vault is already initialized. Skipping initialization."
  warn "If you want to re-initialize, you must first delete all data volumes."
  exit 0
fi

# ── Step 3: Initialize Vault ──────────────────────────────────────────────────
info "Initializing Vault (5 key shares, 3 required to unseal)..."
INIT_OUTPUT=$(kubectl exec -n "${VAULT_NAMESPACE}" "${VAULT_POD}" -- \
  vault operator init \
    -key-shares=5 \
    -key-threshold=3 \
    -format=json)

ok "Vault initialized"

# Parse output
UNSEAL_KEY_1=$(echo "${INIT_OUTPUT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['unseal_keys_b64'][0])")
UNSEAL_KEY_2=$(echo "${INIT_OUTPUT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['unseal_keys_b64'][1])")
UNSEAL_KEY_3=$(echo "${INIT_OUTPUT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['unseal_keys_b64'][2])")
UNSEAL_KEY_4=$(echo "${INIT_OUTPUT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['unseal_keys_b64'][3])")
UNSEAL_KEY_5=$(echo "${INIT_OUTPUT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['unseal_keys_b64'][4])")
ROOT_TOKEN=$(echo "${INIT_OUTPUT}" | python3 -c "import sys,json; print(json.load(sys.stdin)['root_token'])")

# ── Step 4: Store keys as Kubernetes Secrets ──────────────────────────────────
# These secrets are the bootstrap safety net. In production, distribute
# keys to 5 different people — no single person should hold more than 2.
info "Storing unseal keys and root token as Kubernetes Secrets..."

kubectl create secret generic vault-unseal-keys \
  --namespace="${VAULT_NAMESPACE}" \
  --from-literal=key1="${UNSEAL_KEY_1}" \
  --from-literal=key2="${UNSEAL_KEY_2}" \
  --from-literal=key3="${UNSEAL_KEY_3}" \
  --from-literal=key4="${UNSEAL_KEY_4}" \
  --from-literal=key5="${UNSEAL_KEY_5}" \
  --from-literal=root-token="${ROOT_TOKEN}" \
  --dry-run=client -o yaml | kubectl apply -f -

ok "Unseal keys stored in Secret: vault/vault-unseal-keys"

# ── Step 5: Unseal Vault using 3 of the 5 keys ───────────────────────────────
info "Unsealing Vault..."
kubectl exec -n "${VAULT_NAMESPACE}" "${VAULT_POD}" -- \
  vault operator unseal "${UNSEAL_KEY_1}"
kubectl exec -n "${VAULT_NAMESPACE}" "${VAULT_POD}" -- \
  vault operator unseal "${UNSEAL_KEY_2}"
kubectl exec -n "${VAULT_NAMESPACE}" "${VAULT_POD}" -- \
  vault operator unseal "${UNSEAL_KEY_3}"
ok "Vault is unsealed"

# ── Step 6: Verify ────────────────────────────────────────────────────────────
info "Verifying Vault status..."
kubectl exec -n "${VAULT_NAMESPACE}" "${VAULT_POD}" -- vault status
ok "Vault is operational"

# ── Summary ───────────────────────────────────────────────────────────────────
printf "\n${GREEN}Vault initialization complete!${NC}\n\n"
printf "${YELLOW}⚠️  CRITICAL NEXT STEPS:${NC}\n"
printf "  1. Print these keys and store them in a physical safe:\n"
printf "     kubectl get secret vault-unseal-keys -n vault -o json | python3 -c 'import sys,json; d=json.load(sys.stdin); [print(k+\":\",v) for k,v in {k: __import__(\"base64\").b64decode(v).decode() for k,v in d[\"data\"].items()}.items()]'\n\n"
printf "  2. Distribute keys 1-5 to 5 different trusted operators.\n"
printf "     No single person should hold more than 2 keys.\n\n"
printf "  3. Consider deleting the K8s Secret once keys are safely stored offline:\n"
printf "     kubectl delete secret vault-unseal-keys -n vault\n\n"
printf "  4. Run configure-vault.sh to set up auth methods and secrets engines.\n\n"
printf "  Root token: ${ROOT_TOKEN}\n"
printf "  ${RED}Store the root token offline and do not use it day-to-day.${NC}\n"
printf "  Create admin tokens with configure-vault.sh instead.\n\n"
