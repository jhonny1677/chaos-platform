# Runbook: Certificate Renewal

**Service:** cert-manager + TLS certificates  
**Namespace:** `cert-manager`  
**Severity if expired:** P1 — all HTTPS endpoints fail with SSL errors  
**On-call escalation:** Platform Team

---

## Overview

cert-manager automatically renews certificates **30 days before expiry** (configured via `renewBefore: 720h`). This runbook covers:
- Detecting failing renewals before expiry
- Manually triggering renewal
- Recovering from an already-expired certificate
- Rotating the Let's Encrypt account key

Under normal operation this runbook should never be needed — cert-manager handles everything. Use it when the automated renewal fails.

---

## Certificate Inventory

| Certificate | Namespace | Issuer | Domain | Expiry Alert |
|---|---|---|---|---|
| `chaos-platform-tls` | `chaos-platform` | letsencrypt-prod | your-domain.com | 30d before |
| `wildcard-chaos-platform-tls` | `ingress-nginx` | letsencrypt-prod-dns01 | *.your-domain.com | 30d before |
| `chaos-platform-ca` | `cert-manager` | selfsigned-issuer | internal CA | 60d before |

---

## Detecting Failing Renewals

### Alert: `CertificateNearExpiry` (Prometheus)
Fires when `certmanager_certificate_expiration_timestamp_seconds - time() < 86400 * 7` (7 days remaining).

### List all certificates and their status
```bash
kubectl get certificates -A
```
Look for `READY: False` — this means renewal is actively failing.

### Detailed certificate status
```bash
kubectl describe certificate chaos-platform-tls -n chaos-platform
```
Check the `Events` section for renewal errors like:
- `Failed to create Order` — ACME challenge failed
- `Error getting keypair for CSR` — key rotation issue
- `Certificate will expire` — renewal is attempted but stalled

### Check cert-manager logs
```bash
kubectl logs -n cert-manager deployment/cert-manager -f --tail=100
```
Filter for your domain:
```bash
kubectl logs -n cert-manager deployment/cert-manager | grep "your-domain.com"
```

---

## Manual Certificate Renewal

### Trigger renewal immediately (before it's expired)
```bash
# Annotate the certificate to trigger immediate renewal
kubectl annotate certificate chaos-platform-tls -n chaos-platform \
  cert-manager.io/issue-temporary-certificate="true" --overwrite

# OR delete the CertificateRequest to force a new one
kubectl delete certificaterequest -n chaos-platform \
  $(kubectl get certificaterequest -n chaos-platform -l \
    cert-manager.io/certificate-name=chaos-platform-tls \
    -o jsonpath='{.items[0].metadata.name}')
```

### Watch renewal progress
```bash
kubectl get certificaterequest -n chaos-platform -w
```
Progress:
1. `Pending` — challenge being set up
2. `Approved` — cert authority approved
3. `Ready: True` — certificate issued

### Verify the new certificate
```bash
kubectl get secret chaos-platform-tls -n chaos-platform -o jsonpath='{.data.tls\.crt}' \
  | base64 -d | openssl x509 -noout -dates -subject
```

---

## Recovering from an Expired Certificate

If a certificate has already expired, browsers show connection errors. Act immediately.

### Step 1: Check current expiry
```bash
kubectl get secret chaos-platform-tls -n chaos-platform \
  -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -enddate
```

### Step 2: Delete the stale TLS secret (forces cert-manager to issue a new one)
```bash
kubectl delete secret chaos-platform-tls -n chaos-platform
```
cert-manager detects the missing secret and immediately begins a new ACME challenge.

### Step 3: Watch renewal
```bash
kubectl describe certificate chaos-platform-tls -n chaos-platform
kubectl get events -n chaos-platform --sort-by='.lastTimestamp' | grep -i cert
```

### Step 4: While waiting — serve a self-signed cert (minimize downtime)
```bash
# Generate a temporary self-signed cert
openssl req -x509 -nodes -days 1 -newkey rsa:2048 \
  -keyout /tmp/tls.key -out /tmp/tls.crt \
  -subj "/CN=chaos-platform-emergency"

kubectl create secret tls chaos-platform-tls -n chaos-platform \
  --cert=/tmp/tls.crt --key=/tmp/tls.key \
  --dry-run=client -o yaml | kubectl apply -f -

rm /tmp/tls.key /tmp/tls.crt
```
Browsers will show a certificate warning but HTTPS will function. Replace with the real cert once issued.

---

## Let's Encrypt Rate Limit Recovery

If renewal fails with `too many certificates already issued` (429):

1. Check rate limit status: `https://letsencrypt.org/docs/rate-limits/`
2. Switch to staging issuer temporarily:
   ```bash
   kubectl patch certificate chaos-platform-tls -n chaos-platform \
     --type=json -p='[{"op":"replace","path":"/spec/issuerRef/name","value":"letsencrypt-staging"}]'
   ```
3. Wait for rate limit window to reset (1 week for the main limit)
4. Switch back to production issuer

---

## Rotating the ACME Account Key

If the Let's Encrypt account key is compromised:

```bash
# Delete the account key secret — cert-manager creates a new account automatically
kubectl delete secret letsencrypt-prod-account-key -n cert-manager

# Restart cert-manager to force account re-registration
kubectl rollout restart deployment/cert-manager -n cert-manager
```

**Note:** After rotating the account key, existing certificates remain valid. Only new issuance/renewals use the new account.

---

## Preventive Checks

Run weekly in CI (add to GitHub Actions `security-scan.yml`):
```bash
kubectl get certificates -A -o json | python3 -c "
import sys, json, datetime
certs = json.load(sys.stdin)
for item in certs['items']:
    name = item['metadata']['name']
    ns   = item['metadata']['namespace']
    cond = {c['type']: c for c in item.get('status', {}).get('conditions', [])}
    if cond.get('Ready', {}).get('status') != 'True':
        print(f'FAILING: {ns}/{name}')
    exp = item.get('status', {}).get('notAfter', '')
    if exp:
        expiry = datetime.datetime.fromisoformat(exp.rstrip('Z'))
        days   = (expiry - datetime.datetime.utcnow()).days
        if days < 14:
            print(f'WARNING: {ns}/{name} expires in {days} days')
"
```
