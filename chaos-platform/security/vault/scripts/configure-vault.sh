#!/usr/bin/env bash
# configure-vault.sh — Configure Vault auth methods, policies, and secrets engines.
#
# Usage: bash security/vault/scripts/configure-vault.sh
#
# Prerequisites:
#   - Vault initialized and unsealed (run init-vault.sh first)
#   - VAULT_TOKEN environment variable set to the root token
#     (or an admin token with sufficient permissions)
#   - VAULT_ADDR environment variable set (e.g. http://localhost:8200)
#   - Port-forward running: kubectl port-forward svc/vault -n vault 8200:8200
#   - DB_HOST, DB_PORT, DB_NAME, DB_USERNAME, DB_PASSWORD env vars set
#     for the PostgreSQL database secrets engine

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }
warn() { printf "${YELLOW}  ⚠ %s${NC}\n" "$*"; }
banner() { printf "\n${BLUE}── %s ──${NC}\n" "$*"; }

VAULT_ADDR="${VAULT_ADDR:-http://localhost:8200}"
VAULT_TOKEN="${VAULT_TOKEN:?VAULT_TOKEN must be set to the root or admin token}"
VAULT_NAMESPACE="vault"
K8S_HOST="${K8S_HOST:-https://kubernetes.default.svc}"
POLICY_DIR="${BASH_SOURCE%/*}/../config/policies"

export VAULT_ADDR VAULT_TOKEN

# ── Verify connectivity ───────────────────────────────────────────────────────
info "Connecting to Vault at ${VAULT_ADDR}..."
vault status || err "Cannot reach Vault. Is the port-forward running?"
ok "Connected to Vault"

# ── Enable Kubernetes auth method ─────────────────────────────────────────────
banner "Kubernetes Auth Method"
info "Enabling Kubernetes auth..."
vault auth enable kubernetes 2>/dev/null || warn "kubernetes auth already enabled"

info "Configuring Kubernetes auth to trust cluster service accounts..."
vault write auth/kubernetes/config \
  kubernetes_host="${K8S_HOST}" \
  kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
  token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)"
ok "Kubernetes auth configured"

# ── Upload policies ───────────────────────────────────────────────────────────
banner "Policies"
for policy_file in "${POLICY_DIR}"/*.hcl; do
  policy_name=$(basename "${policy_file}" .hcl)
  info "Writing policy: ${policy_name}"
  vault policy write "${policy_name}" "${policy_file}"
  ok "Policy applied: ${policy_name}"
done

# ── Enable KV secrets engine v2 ───────────────────────────────────────────────
banner "KV Secrets Engine"
info "Enabling KV v2 at secret/..."
vault secrets enable -version=2 -path=secret kv 2>/dev/null || warn "KV already enabled"

# Seed placeholder secrets for each service
for service in chaos-engine load-tester dashboard redis; do
  info "Creating placeholder secrets for ${service}..."
  vault kv put "secret/${service}/config" \
    placeholder="REPLACE_ME_see_configure-vault.sh" \
    service="${service}" \
    environment="dev"
done
ok "KV secrets engine ready"

# ── Enable Database secrets engine ────────────────────────────────────────────
banner "Database Secrets Engine"
info "Enabling database secrets engine..."
vault secrets enable database 2>/dev/null || warn "database secrets already enabled"

DB_HOST="${DB_HOST:-REPLACE_ME_DB_HOST}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-REPLACE_ME_DB_NAME}"
DB_USERNAME="${DB_USERNAME:-REPLACE_ME_DB_SUPERUSER}"
DB_PASSWORD="${DB_PASSWORD:-REPLACE_ME_DB_PASSWORD}"

info "Configuring PostgreSQL connection..."
vault write database/config/postgresql \
  plugin_name=postgresql-database-plugin \
  allowed_roles="chaos-engine-role,load-tester-role" \
  connection_url="postgresql://{{username}}:{{password}}@${DB_HOST}:${DB_PORT}/${DB_NAME}?sslmode=require" \
  username="${DB_USERNAME}" \
  password="${DB_PASSWORD}"
ok "PostgreSQL configured"

# chaos-engine dynamic role — 1 hour TTL, auto-expires
info "Creating chaos-engine database role..."
vault write database/roles/chaos-engine-role \
  db_name=postgresql \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO \"{{name}}\";" \
  revocation_statements="REVOKE ALL ON ALL TABLES IN SCHEMA public FROM \"{{name}}\"; DROP ROLE IF EXISTS \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="24h"

# load-tester dynamic role
info "Creating load-tester database role..."
vault write database/roles/load-tester-role \
  db_name=postgresql \
  creation_statements="CREATE ROLE \"{{name}}\" WITH LOGIN PASSWORD '{{password}}' VALID UNTIL '{{expiration}}'; GRANT SELECT, INSERT, UPDATE ON test_results, test_runs TO \"{{name}}\";" \
  revocation_statements="REVOKE ALL ON test_results, test_runs FROM \"{{name}}\"; DROP ROLE IF EXISTS \"{{name}}\";" \
  default_ttl="1h" \
  max_ttl="24h"
ok "Database roles created"

# ── Enable PKI secrets engine ─────────────────────────────────────────────────
banner "PKI Secrets Engine"
info "Enabling PKI at pki/..."
vault secrets enable pki 2>/dev/null || warn "PKI already enabled"
vault secrets tune -max-lease-ttl=8760h pki

info "Generating internal root CA..."
vault write -field=certificate pki/root/generate/internal \
  common_name="chaos-platform-internal-ca" \
  issuer_name="chaos-platform-root" \
  ttl=8760h > /tmp/ca-cert.pem
ok "Internal CA generated"

vault write pki/roles/internal-cert \
  allowed_domains="chaos-platform.local,chaos-platform.svc.cluster.local" \
  allow_subdomains=true \
  max_ttl=72h

# ── Create K8s auth roles binding service accounts to policies ─────────────────
banner "Kubernetes Auth Roles"
for binding in \
    "chaos-engine:chaos-engine:chaos-engine-policy" \
    "load-tester:load-tester:load-tester-policy" \
    "chaos-engine:dashboard:dashboard-policy"; do
  namespace="${binding%%:*}"
  rest="${binding#*:}"
  sa="${rest%%:*}"
  policy="${rest##*:}"
  info "Binding ${namespace}/${sa} → ${policy}"
  vault write "auth/kubernetes/role/${sa}" \
    bound_service_account_names="${sa}" \
    bound_service_account_namespaces="${namespace}" \
    policies="${policy}" \
    ttl=1h
  ok "Role created: ${sa}"
done

# ── Enable Audit Logging ───────────────────────────────────────────────────────
banner "Audit Logging"
info "Enabling stdout audit log..."
vault audit enable file file_path=stdout 2>/dev/null || warn "Audit already enabled"
ok "Audit logging active"

printf "\n${GREEN}Vault configuration complete!${NC}\n"
printf "  KV path:        secret/<service>/config\n"
printf "  Database roles: chaos-engine-role, load-tester-role\n"
printf "  K8s auth roles: chaos-engine, load-tester, dashboard\n\n"
