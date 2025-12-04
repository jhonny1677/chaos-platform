# Vault server configuration for the Chaos Platform.
#
# Storage: Integrated Raft (survives pod restarts via PVC) — "not file" because
# the file backend is single-node only; Raft supports HA with automatic leader
# election when multiple Vault pods are running.
#
# TLS: disabled at the Vault level — cert-manager terminates TLS at the
# Kubernetes Ingress/Service mesh layer. Vault-to-Vault cluster traffic
# (Raft replication) uses its own internal TLS regardless.

storage "raft" {
  path    = "/vault/data"
  node_id = "vault-0"

  # Retry-join allows follower nodes to discover the cluster leader automatically.
  # In Kubernetes this resolves via the headless service DNS.
  retry_join {
    leader_api_addr = "http://vault-0.vault-internal.vault.svc.cluster.local:8200"
  }
}

# ── Main listener ──────────────────────────────────────────────────────────────
listener "tcp" {
  address       = "0.0.0.0:8200"
  cluster_address = "0.0.0.0:8201"
  tls_disable   = "true"   # TLS handled by cert-manager + Ingress

  # Telemetry endpoint — Prometheus scrapes /v1/sys/metrics
  telemetry {
    unauthenticated_metrics_access = true
  }
}

# ── Cluster addresses ──────────────────────────────────────────────────────────
# Injected at runtime via K8s downward API environment variables.
api_addr     = "VAULT_API_ADDR_PLACEHOLDER"   # overridden by POD_IP env var at startup
cluster_addr = "VAULT_CLUSTER_ADDR_PLACEHOLDER"

# ── UI ─────────────────────────────────────────────────────────────────────────
ui = true

# ── Audit logging ──────────────────────────────────────────────────────────────
# Stdout audit log so Promtail/Loki can collect it without extra configuration.
# Every request and response (with secrets redacted) is logged.
# In production add a file audit device as a secondary so stdout loss doesn't
# prevent Vault from serving requests.
# NOTE: Vault refuses to operate if ALL audit devices are unavailable.
#       Stdout is always available in a container, so this is safe for dev.

# Audit is enabled via vault audit enable after initialization.
# The config here just sets defaults for the built-in device.

# ── Seal ───────────────────────────────────────────────────────────────────────
# Using Shamir seal (default) for dev — unseal keys stored in K8s Secrets.
# For production, replace with:
#
# seal "awskms" {
#   region     = "REPLACE_WITH_AWS_REGION"
#   kms_key_id = "REPLACE_WITH_KMS_KEY_ID"
# }
#
# AWS KMS auto-unseal means Vault unseals itself on restart without human
# intervention, eliminating the operational burden of manual unsealing.

# ── Telemetry ──────────────────────────────────────────────────────────────────
telemetry {
  prometheus_retention_time = "30s"
  disable_hostname          = true
}

# ── Miscellaneous ─────────────────────────────────────────────────────────────
# Maximum lease duration for secrets. Dynamic DB credentials will expire no
# later than this time, forcing rotation.
max_lease_ttl         = "768h"   # 32 days
default_lease_ttl     = "768h"
