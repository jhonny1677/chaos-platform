# Runbook: Secret Rotation

**Service:** Vault + application secrets  
**Frequency:** Dynamic secrets: automatic (TTL-based). Static secrets: quarterly or on compromise.  
**On-call escalation:** Platform Security Team + Service Owner

---

## Overview

This runbook covers rotating secrets in the Chaos Platform. There are three categories:

| Secret Type | Storage | Rotation Method | Frequency |
|---|---|---|---|
| Dynamic DB credentials | Vault database engine | Automatic on TTL expiry | Every 1 hour |
| Kafka credentials | Vault / AWS MSK | Manual script | Quarterly |
| Slack webhook | Sealed Secrets + Vault | Manual | On suspected compromise |
| TLS certificates | cert-manager | Automatic (30d before expiry) | Every 90 days |
| Vault unseal keys | Offline / K8s Secret | Manual (break-glass) | Annually or on compromise |
| AWS access keys | IRSA (no static keys) | Automatic via STS | On token expiry (1h) |

---

## Dynamic Secret Rotation (Database Credentials)

Dynamic credentials expire automatically after 1 hour. No manual action is normally required.

### Verify auto-rotation is working
```bash
# Port-forward Vault
kubectl port-forward svc/vault -n vault 8200:8200 &

# List active database leases
VAULT_ADDR=http://localhost:8200 VAULT_TOKEN=$(cat ~/.vault-token) \
  vault list sys/leases/lookup/database/creds/chaos-engine-role/
```
If leases are accumulating and not expiring, check Vault logs:
```bash
kubectl logs -n vault vault-0 | grep "lease" | tail -50
```

### Force rotation (emergency — revoke all existing credentials)
```bash
bash security/vault/scripts/rotate-secrets.sh chaos-engine
bash security/vault/scripts/rotate-secrets.sh load-tester
```
This revokes all existing leases and generates fresh credentials. Services restart automatically or pick up new credentials on next TTL check.

### Restart services to pick up new credentials
```bash
kubectl rollout restart deployment/chaos-engine -n chaos-engine
kubectl rollout restart deployment/load-tester -n load-tester
```

---

## Static Secret Rotation (Kafka, Redis, Slack)

Use this procedure when:
- A secret is suspected compromised
- Quarterly rotation schedule is due
- An employee with secret access leaves the organization

### Step 1: Generate new credentials in the upstream system

**Kafka:**
```bash
# On your MSK cluster, create a new SCRAM user
kafka-configs.sh --bootstrap-server <broker> \
  --alter --add-config 'SCRAM-SHA-512=[password=<NEW_PASSWORD>]' \
  --entity-type users --entity-name chaos-engine
```

**Slack webhook:**
1. Go to api.slack.com/apps → Your App → Incoming Webhooks
2. Click "Add New Webhook to Workspace"
3. Copy the new webhook URL

**Redis:**
```bash
# Connect to Redis and change the auth password
redis-cli -h <redis-host> CONFIG SET requirepass <NEW_PASSWORD>
```

### Step 2: Update the secret in Vault
```bash
kubectl port-forward svc/vault -n vault 8200:8200 &
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=<admin-token>

vault kv put secret/chaos-engine/kafka \
  bootstrap-servers="REPLACE_WITH_MSK_BOOTSTRAP" \
  username="chaos-engine" \
  password="<NEW_KAFKA_PASSWORD>"
```

### Step 3: Reseal the Sealed Secret for the K8s Secret (if using Sealed Secrets)
```bash
bash security/sealed-secrets/scripts/seal-secret.sh \
  --name kafka-credentials \
  --namespace chaos-engine \
  --from-literal bootstrap-servers="<MSK_BOOTSTRAP>" \
  --from-literal username="chaos-engine" \
  --from-literal password="<NEW_KAFKA_PASSWORD>" \
  --output security/sealed-secrets/examples/kafka-credentials.yaml

kubectl apply -f security/sealed-secrets/examples/kafka-credentials.yaml
```

### Step 4: Restart affected services
```bash
kubectl rollout restart deployment/chaos-engine -n chaos-engine
kubectl rollout restart deployment/load-tester -n load-tester
```

### Step 5: Revoke the old credentials
**Only after confirming services work with new credentials.** Verify with:
```bash
kubectl get pods -n chaos-engine
kubectl logs -n chaos-engine deployment/chaos-engine --tail=50 | grep -i error
```
Then revoke the old Kafka user:
```bash
kafka-configs.sh --bootstrap-server <broker> \
  --alter --delete-config 'SCRAM-SHA-512' \
  --entity-type users --entity-name chaos-engine-old
```

---

## Vault Root Token Rotation

The root token should NEVER be used for regular operations. If it was used or exposed:

```bash
# Generate a new root token (requires 3 unseal key holders)
vault operator generate-root -init
# Provides an OTP. Each key holder runs:
vault operator generate-root -nonce=<nonce> <KEY_N>
# After 3 keys, decode the encoded root token:
vault operator generate-root -decode=<encoded> -otp=<otp>
```

After generating a new root token, revoke the old one:
```bash
vault token revoke <old-root-token>
```

---

## Vault Unseal Key Rotation

If a key holder leaves the organization or a key is compromised:

```bash
# This operation requires 3 current key holders to authorize
vault operator rekey -init -key-shares=5 -key-threshold=3

# Each of 3 current key holders provides their key:
vault operator rekey -nonce=<nonce> <CURRENT_KEY_N>

# After 3 keys, new key shares are displayed
# Distribute the NEW keys to the (possibly different) 5 key holders
# Revoke access for the departed key holder by destroying their old key
```

---

## Rotation Verification Checklist

After any rotation, verify:

- [ ] All pods restart without crash loops: `kubectl get pods -A`
- [ ] No Vault authentication errors: `kubectl logs -n chaos-engine deployment/chaos-engine | grep -i vault`
- [ ] Prometheus alerts not firing: check Alertmanager
- [ ] Chaos experiments can run: `bash scripts/run-experiment.sh -t pod-kill -n 1`
- [ ] Load tests can connect to Kafka: `bash scripts/run-load-test.sh -d 60`
- [ ] Log the rotation in the security change log with: timestamp, who rotated, what was rotated, reason

---

## Rotation Schedule

| Secret | Last Rotated | Next Due | Owner |
|---|---|---|---|
| DB credentials | Automatic | Automatic | Vault |
| Kafka credentials | FILL_IN | Quarterly | Platform Team |
| Slack webhook | FILL_IN | On compromise | Platform Team |
| Vault unseal keys | FILL_IN | Annually | Security Team |

Keep this table up to date. Stale entries = audit finding.
