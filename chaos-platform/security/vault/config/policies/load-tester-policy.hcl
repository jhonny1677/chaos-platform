# Vault policy for the Load Tester service account.
#
# Load tester needs: database credentials (for result storage),
# Kafka credentials (for chaos event consumption), and Redis connection
# details (for live stats aggregation).

path "secret/data/load-tester/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/load-tester/*" {
  capabilities = ["read", "list"]
}

# Redis connection details (host, port, auth password)
path "secret/data/redis/*" {
  capabilities = ["read", "list"]
}

path "secret/metadata/redis/*" {
  capabilities = ["read", "list"]
}

# ── Dynamic database credentials ───────────────────────────────────────────────
path "database/creds/load-tester-role" {
  capabilities = ["read"]
}

path "sys/leases/renew" {
  capabilities = ["update"]
}

path "sys/leases/lookup" {
  capabilities = ["update"]
}

# ── Kafka credentials ──────────────────────────────────────────────────────────
path "kafka/creds/load-tester" {
  capabilities = ["read"]
}

# ── Token self-management ─────────────────────────────────────────────────────
path "auth/token/renew-self" {
  capabilities = ["update"]
}

path "auth/token/lookup-self" {
  capabilities = ["read"]
}

# ── Explicit denies ────────────────────────────────────────────────────────────
path "sys/*" {
  capabilities = ["deny"]
}

path "auth/*" {
  capabilities = ["deny"]
}
