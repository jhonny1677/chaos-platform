# Runbook: Security Incident Response

**Purpose:** Step-by-step guide for detecting, containing, and recovering from security incidents in the Chaos Platform.  
**Last reviewed:** 2026-06-27  
**Owner:** Platform Security Team  
**Escalation:** security@yourcompany.com → CISO → Legal (if data involved)

---

## Incident Severity Levels

| Level | Criteria | Response Time | Escalate To |
|---|---|---|---|
| P1 Critical | Active compromise, data exfiltration, all services down | 15 min | Security Team + CISO |
| P2 High | Suspicious activity, single service compromised, creds leaked | 1 hour | Security Team |
| P3 Medium | Policy violation, failed intrusion attempt, CVE in active use | 4 hours | Platform Team |
| P4 Low | Informational alerts, near-miss, configuration drift | Next business day | On-call engineer |

---

## Detection Sources

| Source | What it detects | Alert channel |
|---|---|---|
| Falco | Runtime anomalies (shell in container, unexpected syscalls) | PagerDuty + Slack #security-alerts |
| OPA/Gatekeeper | Policy violations at admission | K8s events + Grafana |
| Alertmanager | SLO burns, service downtime | PagerDuty + Slack #chaos-alerts |
| Dependency Track | Critical CVEs in deployed SBOMs | Slack #security-alerts + GitHub Issue |
| Vault audit log | Unusual secret access patterns | Loki query + Grafana |
| GitHub Actions | Gitleaks secret scan failures | PR checks + Slack |

---

## Phase 1: Detection and Triage (0–15 minutes)

### 1.1 Acknowledge the alert
```bash
# Check what Falco has flagged in the last hour
kubectl logs -n falco -l app=falco --since=1h | \
  python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line)
        if e.get('priority') in ['CRITICAL', 'ERROR']:
            print(e.get('time',''), e.get('rule',''), e.get('output',''))
    except: pass
"
```

### 1.2 Identify the affected pod and service
```bash
# Get recent pod events across all namespaces
kubectl get events -A --sort-by='.lastTimestamp' | tail -50

# Check for crash loops
kubectl get pods -A | grep -v Running | grep -v Completed
```

### 1.3 Classify the incident
- **Shell in container?** → Likely active exploitation. Escalate to P1.
- **Unexpected Vault connection?** → Credential theft attempt. P1.
- **OPA policy violation?** → Misconfiguration or deliberate bypass. P2–P3.
- **CVE alert from DTrack?** → No active exploitation if no Falco alert. P3.

---

## Phase 2: Containment (15–60 minutes)

### 2.1 Isolate the compromised pod (immediate)

**Option A: Delete the pod (fastest)**
```bash
# Document the pod first
kubectl describe pod <POD_NAME> -n <NAMESPACE> > /tmp/incident-pod-$(date +%Y%m%d-%H%M%S).txt
kubectl logs <POD_NAME> -n <NAMESPACE> --previous >> /tmp/incident-pod-$(date +%Y%m%d-%H%M%S).txt

# Delete the pod — this immediately stops any malicious process
kubectl delete pod <POD_NAME> -n <NAMESPACE>
```

**Option B: Network isolation (preserves pod for forensics)**
```bash
# Apply a deny-all NetworkPolicy to the specific pod using a label
kubectl label pod <POD_NAME> -n <NAMESPACE> security-incident=isolated

cat <<EOF | kubectl apply -f -
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: isolate-compromised-pod
  namespace: <NAMESPACE>
spec:
  podSelector:
    matchLabels:
      security-incident: isolated
  policyTypes: [Ingress, Egress]
  # No ingress or egress rules = deny all traffic
EOF
```

### 2.2 Revoke credentials immediately

If credentials may have been exposed:
```bash
# Revoke ALL leases for the affected service
kubectl port-forward svc/vault -n vault 8200:8200 &
export VAULT_ADDR=http://localhost:8200
export VAULT_TOKEN=<admin-token>

vault lease revoke -prefix database/creds/chaos-engine-role/
vault lease revoke -prefix database/creds/load-tester-role/
```

If the Vault token itself was leaked:
```bash
vault token revoke <compromised-token>
```

If GitHub secrets were leaked (Gitleaks alert):
1. Immediately rotate the secret in AWS/GitHub/etc.
2. Check GitHub audit log for unauthorized usage
3. Remove the secret from git history: `git filter-branch` or BFG Repo Cleaner

### 2.3 Scale down the affected deployment
```bash
# Prevent new pods from starting while investigation is in progress
kubectl scale deployment <DEPLOYMENT_NAME> -n <NAMESPACE> --replicas=0
```

### 2.4 Preserve evidence
```bash
# Before deleting anything, export all relevant state
INCIDENT_DIR="/tmp/incident-$(date +%Y%m%d-%H%M%S)"
mkdir -p "${INCIDENT_DIR}"

# Pod state
kubectl get pod <POD_NAME> -n <NAMESPACE> -o yaml > "${INCIDENT_DIR}/pod.yaml"
kubectl logs <POD_NAME> -n <NAMESPACE> > "${INCIDENT_DIR}/pod-logs.txt"
kubectl logs <POD_NAME> -n <NAMESPACE> --previous >> "${INCIDENT_DIR}/pod-logs-previous.txt" 2>/dev/null

# Falco events for the pod
kubectl logs -n falco -l app=falco --since=2h | \
  grep "<POD_NAME>" > "${INCIDENT_DIR}/falco-events.json"

# Vault audit log (if accessible)
kubectl logs -n vault vault-0 --since=2h > "${INCIDENT_DIR}/vault-audit.json"

# Network connections at time of incident (from existing Loki logs)
echo "Loki query: {app='<DEPLOYMENT_NAME>'} | json | line_format '{{.msg}}'" \
  > "${INCIDENT_DIR}/loki-query.txt"

echo "Evidence preserved in ${INCIDENT_DIR}"
tar -czf "${INCIDENT_DIR}.tar.gz" "${INCIDENT_DIR}"
```

---

## Phase 3: Investigation (1–4 hours)

### 3.1 Determine the attack vector

Common attack patterns in this platform:

**Container escape via privileged pod:**
```bash
# Check if Kyverno/OPA allowed a privileged pod through
kubectl get events -n <NAMESPACE> | grep -i "policy"
kubectl get pods -n <NAMESPACE> -o jsonpath='{..securityContext}'
```

**Vault credential theft:**
```bash
# Who accessed the secret path?
kubectl logs -n vault vault-0 | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line)
        req = e.get('request', {})
        if 'creds' in req.get('path', '') or 'secret' in req.get('path', ''):
            print(e.get('time',''), req.get('remote_address',''), req.get('path',''))
    except: pass
"
```

**Supply chain (malicious image):**
```bash
# Check what image was running
kubectl describe pod <POD_NAME> -n <NAMESPACE> | grep "Image:"
# Cross-reference with ECR push logs in CloudTrail
```

### 3.2 Determine blast radius
- What secrets did the compromised service have access to?
- Were those secrets accessed during the incident window?
- Which other services use those secrets?

---

## Phase 4: Eradication and Recovery (2–8 hours)

### 4.1 Patch the vulnerability
- CVE in application code → update the image, trigger new CI build
- CVE in base image → update `FROM` in Dockerfile, rebuild
- Misconfigured RBAC → fix and apply updated RBAC manifests
- Weak OPA/Kyverno policy → tighten the policy, apply, audit existing resources

### 4.2 Rotate all potentially compromised secrets

Follow `secret-rotation.md` for each affected secret.

### 4.3 Deploy patched version
```bash
# After new image is built and scanned in CI
kubectl scale deployment <DEPLOYMENT_NAME> -n <NAMESPACE> --replicas=2
kubectl rollout status deployment/<DEPLOYMENT_NAME> -n <NAMESPACE>
```

### 4.4 Remove isolation
```bash
kubectl delete networkpolicy isolate-compromised-pod -n <NAMESPACE>
kubectl label pod --all -n <NAMESPACE> security-incident-
```

---

## Phase 5: Post-Incident (within 5 business days)

### 5.1 Write the post-mortem

Required sections:
1. **Timeline** — when was it detected, contained, eradicated?
2. **Root cause** — what was the exploited vulnerability?
3. **Impact** — which services were affected? Any data accessed?
4. **Detection gap** — why didn't existing controls catch this sooner?
5. **Action items** — specific changes with owners and due dates

### 5.2 Update detection rules

If Falco didn't catch the attack:
```yaml
# Add a new rule to falco-rules.yaml targeting the specific behavior
- rule: <Name of new attack pattern>
  condition: <sysdig filter>
  output: <log format>
  priority: ERROR
  tags: [new-attack, chaos-platform]
```

### 5.3 Update this runbook

If you found a gap in the response procedure, update this document immediately — before the next incident happens.

---

## Emergency Contacts

| Role | Contact Method | When to use |
|---|---|---|
| Platform On-Call | PagerDuty escalation | Any P1/P2 incident |
| Security Team | security@yourcompany.com | Confirmed compromise |
| CISO | pager + email | Data breach, regulatory event |
| AWS Support | Support console (Business/Enterprise plan) | AWS infrastructure incident |

---

## Quick Reference: One-Liners

```bash
# All pod security violations in last 1h
kubectl get events -A --sort-by='.lastTimestamp' | grep -i "violat"

# All Falco CRITICAL events today
kubectl logs -n falco -l app=falco --since=24h | python3 -c "import sys,json; [print(json.loads(l).get('rule')) for l in sys.stdin if 'CRITICAL' in l]" 2>/dev/null

# All Vault audit entries for a specific namespace
kubectl logs -n vault vault-0 --since=1h | python3 -c "import sys,json; [print(l) for l in sys.stdin if '<NAMESPACE>' in l]"

# Force-revoke all leases (nuclear option)
vault lease revoke -prefix /
```
