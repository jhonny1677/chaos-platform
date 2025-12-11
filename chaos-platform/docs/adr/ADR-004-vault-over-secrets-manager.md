# ADR-004: HashiCorp Vault Instead of AWS Secrets Manager

**Status:** Accepted  
**Date:** 2026-03-01  
**Deciders:** Platform Team

---

## Context

The platform handles sensitive credentials:
- PostgreSQL usernames and passwords (chaos engine and load tester)
- Kafka SASL credentials
- Slack webhook URLs
- Vault's own unseal keys and root token

We needed a secrets management system that provides:
1. **Fine-grained access control** — chaos engine should not be able to read dashboard secrets
2. **Dynamic credentials** — database passwords that expire automatically (reduces risk if leaked)
3. **Audit logging** — who read which secret, and when?
4. **Rotation** — ability to rotate credentials without downtime

---

## Decision

We chose **HashiCorp Vault** deployed as a StatefulSet in the `vault` namespace with Raft integrated storage.

The key features we use:
- **Kubernetes Auth Method**: pods authenticate using their ServiceAccount JWT — no static credentials needed
- **Database Secrets Engine**: generates unique PostgreSQL credentials per pod, automatically expiring after 1 hour
- **KV v2 Secrets Engine**: for static secrets (Kafka credentials, Slack webhook)
- **Audit Log**: every request logged to stdout, captured by Promtail/Loki

---

## Consequences

**Good:**
- Dynamic database credentials are a significant security improvement over static passwords. If a chaos-engine pod is compromised, its credentials expire in 1 hour and cannot be renewed without the Vault token.
- The Kubernetes auth method eliminates the need for any static credentials in the pod environment — the pod identity (ServiceAccount + namespace) IS the authentication.
- Vault audit log provides a detailed trail of every secret access. We can answer: "Did anything read the Kafka credentials in the last 24 hours?" in seconds via Loki.
- Vault is not AWS-specific. This configuration would work on GKE or on-premises with minor changes.
- OPA and Vault work together: OPA enforces which pods are allowed to exist (Kubernetes admission), Vault controls what secrets those pods can access.

**Bad / Trade-offs:**
- Vault requires operational knowledge: initialization, unsealing, policy management. AWS Secrets Manager is entirely managed.
- Unsealing is a manual step after every Vault pod restart (mitigated by the KMS auto-unseal option documented in the runbook).
- Vault adds latency to pod startup: the Vault agent sidecar must authenticate and fetch secrets before the main container starts. Adds ~2-3 seconds to pod cold start.
- Three team members must coordinate to unseal Vault (3-of-5 Shamir key shares) — this is intentional for security but operationally inconvenient.

---

## Alternatives Considered

**AWS Secrets Manager:**  
- Fully managed, excellent AWS integration (IAM policies, automatic rotation for some services)  
- Rejected because: AWS-specific (vendor lock-in), no equivalent to Vault's dynamic database credentials engine, no fine-grained sub-resource policies (can restrict access to a secret but not a field within a secret), no Kubernetes-native auth method  

**Kubernetes Secrets (native):**  
- Zero operational overhead, built into every cluster  
- Rejected because: base64-encoded (not encrypted), stored in etcd (requires etcd encryption at rest), no audit logging, no dynamic credentials, no expiry  

**External Secrets Operator (with Secrets Manager):**  
- Would sync AWS Secrets Manager secrets into K8s Secrets  
- Hybrid approach we considered — still has the AWS lock-in issue and no dynamic credentials  
