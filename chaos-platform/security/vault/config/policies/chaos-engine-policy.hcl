# Vault policy for the Chaos Engine service account.
#
# Principle of least privilege: chaos-engine can only READ its own secrets.
# It has no write access anywhere — if the chaos engine is compromised it
# cannot modify secrets, rotate credentials, or escalate privileges.
#
# Dynamic credentials (database, kafka) expire automatically and cannot be
# renewed beyond the max_ttl, limiting the window of exposure.

# ── KV static secrets ─────────────────────────────────────────────────────────
path "secret/data/chaos-engine/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/chaos-engine/*" {
  capabilities = ["read", "list"]
}

# ── Dynamic database credentials ───────────────────────────────────────────────
# The database secrets engine generates short-lived PostgreSQL credentials.
# Each chaos-engine pod gets its own unique username/password pair.
path "database/creds/chaos-engine-role" {
  capabilities = ["read"]
}

# Allow the service to renew its own lease before expiry
path "sys/leases/renew" {
  capabilities = ["update"]
}

# Allow the service to look up its own lease (for monitoring expiry)
path "sys/leases/lookup" {
  capabilities = ["update"]
}

# ── Kafka credentials ──────────────────────────────────────────────────────────
path "kafka/creds/chaos-engine" {
  capabilities = ["read"]
}

# ── Token self-management ─────────────────────────────────────────────────────
# Allow the service to renew and look up its own Vault token.
# Explicitly block creating new tokens — the chaos engine cannot hand out
# vault tokens to other services or escalate its own permissions.
path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

# ── Explicitly deny everything else ───────────────────────────────────────────
# Vault denies by default, but explicit deny makes the intention clear
# and prevents accidental policy merges from granting extra access.
path "sys/*" {
  capabilities = ["deny"]
}

path "auth/*" {
  capabilities = ["deny"]
}
