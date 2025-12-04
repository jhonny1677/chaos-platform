# Vault admin policy.
#
# Used only by: the configure-vault.sh bootstrap script and break-glass human
# operators. This token MUST be stored offline (e.g. in a hardware password
# manager) and never used for automated service authentication.
#
# Rationale for full access: the admin needs to configure auth methods,
# enable secrets engines, and manage policies. Restricting the admin
# defeats the purpose. Access is controlled at the token level — the admin
# token has a short TTL (24h) and is not persisted in any service.

# ── System management ─────────────────────────────────────────────────────────
path "sys/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# ── KV secrets engine ─────────────────────────────────────────────────────────
path "secret/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# ── Auth methods ───────────────────────────────────────────────────────────────
path "auth/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# ── Database secrets engine ────────────────────────────────────────────────────
path "database/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# ── Kafka secrets engine ───────────────────────────────────────────────────────
path "kafka/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# ── PKI secrets engine ─────────────────────────────────────────────────────────
path "pki/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}

# ── Identity ───────────────────────────────────────────────────────────────────
path "identity/*" {
  capabilities = ["create", "read", "update", "delete", "list", "sudo"]
}
