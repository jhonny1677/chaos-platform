# Vault policy for the Dashboard (React frontend served by nginx).
#
# The dashboard only needs API endpoint URLs and the Grafana embed token.
# It has absolutely no database or Kafka access — those services handle
# their own auth. This is the most restricted policy in the platform.
#
# If the dashboard pod is compromised, the attacker gains nothing useful
# from Vault — they cannot reach any data stores directly.

path "secret/data/dashboard/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/dashboard/*" {
  capabilities = ["read", "list"]
}

# ── Token self-management ─────────────────────────────────────────────────────
path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

# ── Explicit denies ────────────────────────────────────────────────────────────
path "database/*" {
  capabilities = ["deny"]
}

path "kafka/*" {
  capabilities = ["deny"]
}

path "sys/*" {
  capabilities = ["deny"]
}

path "auth/*" {
  capabilities = ["deny"]
}
