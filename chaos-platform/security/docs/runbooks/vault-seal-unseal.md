# Runbook: Vault Seal / Unseal

**Service:** HashiCorp Vault  
**Namespace:** `vault`  
**Severity when sealed:** P1 — all services lose secret access within TTL expiry  
**On-call escalation:** Platform Security Team

---

## Overview

Vault enters a **sealed** state when:
1. The pod restarts (planned or unplanned) and auto-unseal is not configured
2. An operator manually seals Vault (`vault operator seal`)
3. Vault detects a quorum loss in the Raft cluster

In sealed state, Vault holds all data encrypted and **refuses all API requests** — it cannot decrypt anything, including serving credentials to the chaos engine or load tester. Services that hold valid short-lived tokens continue to work until those tokens expire, after which they fail to renew and begin crashing.

**Time to impact after pod restart:** equal to the shortest dynamic credential TTL (1 hour in this platform).

---

## Detecting a Sealed Vault

### Alert: `VaultSealed` (Prometheus)
The Prometheus rule fires when `vault_core_unsealed == 0` for more than 2 minutes.

### Manual check
```bash
kubectl exec -n vault vault-0 -- vault status
```
Look for:
```
Sealed: true
```

### Health endpoint (no auth required)
```bash
kubectl port-forward svc/vault -n vault 8200:8200 &
curl http://localhost:8200/v1/sys/health | python3 -m json.tool
```
HTTP 503 = sealed. HTTP 200 = unsealed and active.

---

## Unseal Procedure

Vault uses **Shamir's Secret Sharing** (5 key shares, 3 required). You need 3 keys from 3 different key holders.

### Step 1: Confirm Vault is sealed
```bash
kubectl exec -n vault vault-0 -- vault status | grep Sealed
```

### Step 2: Obtain 3 unseal keys
Keys are distributed to 5 separate trusted operators. Contact at least 3 of them.

**Emergency only:** If no operators are available and you have the bootstrap secret:
```bash
# Read keys from the K8s Secret (only exists if it wasn't deleted after init)
kubectl get secret vault-unseal-keys -n vault -o json \
  | python3 -c "import sys,json,base64; d=json.load(sys.stdin)['data']; [print(k+':', base64.b64decode(v).decode()) for k,v in d.items()]"
```
⚠️ If the K8s Secret was deleted (as recommended in the init runbook), you MUST contact the key holders.

### Step 3: Unseal with 3 keys (one per key holder)
Each key holder runs ONE of these commands from their machine:
```bash
kubectl exec -n vault vault-0 -- vault operator unseal <KEY_N>
```
After each `unseal` command, the output shows `Unseal Progress: N/3`.
After the 3rd key, Vault prints `Sealed: false`.

### Step 4: Verify
```bash
kubectl exec -n vault vault-0 -- vault status
```
Expected:
```
Sealed:      false
HA Enabled:  false
```

### Step 5: Verify services can connect
```bash
# Check chaos-engine can authenticate
kubectl exec -n chaos-engine deployment/chaos-engine -- \
  curl -s http://vault.vault.svc.cluster.local:8200/v1/sys/health | python3 -m json.tool
```

---

## Auto-Unseal (Production Recommendation)

For production, configure AWS KMS auto-unseal to eliminate human intervention:

1. Create a KMS key in AWS Console → KMS → Customer Managed Keys
2. Grant the Vault pod's IRSA role `kms:Decrypt` and `kms:DescribeKey` permissions
3. Add to `vault-config.hcl`:
   ```hcl
   seal "awskms" {
     region     = "REPLACE_WITH_AWS_REGION"
     kms_key_id = "REPLACE_WITH_KMS_KEY_ID"
   }
   ```
4. Restart Vault — it will unseal itself automatically on every pod restart

With KMS auto-unseal, pod restarts (node upgrades, SPOT preemptions) are transparent.

---

## Manual Seal Procedure (Intentional)

If you need to seal Vault intentionally (security incident, maintenance):

```bash
# Requires a valid Vault token with sudo capability
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=<your-token>
vault operator seal
```

**After manual seal:** Vault will NOT auto-unseal — you must run the unseal procedure above.

---

## Raft Cluster Troubleshooting

For HA clusters (3 nodes), check the cluster state:

```bash
kubectl exec -n vault vault-0 -- vault operator raft list-peers
```

If a follower is unreachable:
```bash
# Remove the failed node from the cluster
kubectl exec -n vault vault-0 -- vault operator raft remove-peer vault-2
# Then restart the failed pod — it will rejoin on startup via retry_join
kubectl delete pod vault-2 -n vault
```

---

## Runbook Validation

Test this runbook quarterly by:
1. Sealing Vault manually: `vault operator seal`
2. Verifying alert fires within 3 minutes
3. Executing the unseal procedure with 3 real key holders
4. Confirming services recover within 5 minutes of unseal

Log the test in the security incident register.
