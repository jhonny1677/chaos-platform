# Troubleshooting

## Problem 1: Vault Pods are CrashLoopBackOff

**Symptoms:** `kubectl get pods -n vault` shows `vault-0` in CrashLoopBackOff.

**Diagnosis:**
```bash
kubectl logs vault-0 -n vault --previous
kubectl describe pod vault-0 -n vault
```

**Common causes and fixes:**

**Cause A: PVC not bound**
```bash
kubectl get pvc -n vault
# If STATUS is Pending, check StorageClass
kubectl get storageclass
# The default StorageClass should have VOLUMEBINDINGMODE = WaitForFirstConsumer or Immediate
```

**Cause B: Vault is sealed after restart**
```bash
kubectl exec -n vault vault-0 -- vault status
# If Sealed: true, unseal it:
./security/vault/scripts/unseal-vault.sh
```

**Cause C: Init container failed (permission issue)**
```bash
kubectl logs vault-0 -n vault -c vault-init
# If "chown: changing ownership of '/vault/data': Operation not permitted"
# Delete and recreate the PVC (data loss — only do this on a fresh install):
kubectl delete pvc vault-data-vault-0 -n vault
kubectl delete pod vault-0 -n vault
```

---

## Problem 2: ArgoCD Application Stuck in Progressing

**Symptoms:** `kubectl get applications -n argocd` shows `Progressing` for more than 5 minutes.

**Diagnosis:**
```bash
kubectl describe application <app-name> -n argocd
# Look at the "Conditions" and "Health" sections

# Check the actual pod events
kubectl get events -n <target-namespace> --sort-by='.lastTimestamp' | tail -20
```

**Common causes and fixes:**

**Cause A: Container image not found in ECR**
```bash
kubectl get pods -n <namespace>
kubectl describe pod <pod-name> -n <namespace>
# Look for: "Failed to pull image"
# Fix: build and push the missing image
docker build -t $REGISTRY/chaos-engine:latest apps/chaos-engine/
docker push $REGISTRY/chaos-engine:latest
```

**Cause B: Readiness probe failing**
```bash
kubectl logs <pod-name> -n <namespace>
# If the app is crashing on startup, check environment variables:
kubectl exec -n <namespace> <pod-name> -- env | grep -E "KAFKA|REDIS|DB"
# Vault agent may not have fetched secrets yet — wait 30s and check again
```

**Cause C: Dependency not ready (sync waves)**
```bash
# Monitoring namespace must be Healthy before apps deploy
kubectl get application monitoring -n argocd
# If Degraded, fix monitoring first
```

---

## Problem 3: Chaos Engine Circuit Breaker Is Open

**Symptoms:** `POST /experiments` returns HTTP 503: `{"error": "circuit breaker is open"}`.

**Diagnosis:**
```bash
curl http://localhost:8001/health | jq '.circuitBreaker'
# {"state": "open", "failureCount": 3, "lastFailureAt": "2026-01-27T..."}
```

The circuit breaker opens after 3 consecutive experiments fail to reach a healthy state within the recovery timeout. This is a safety mechanism.

**Fix:**
1. Investigate why the last 3 experiments failed:
   ```bash
   curl http://localhost:8001/experiments?limit=5 | jq '.experiments[] | {id, type, status, failureReason}'
   ```
2. Ensure the target app is fully healthy:
   ```bash
   kubectl get pods -n chaos-platform -l app=target-app
   # All pods must be Running and 1/1 Ready
   ```
3. Reset the circuit breaker (only after confirming the system is healthy):
   ```bash
   curl -X POST http://localhost:8001/admin/circuit-breaker/reset
   ```

---

## Problem 4: Load Test Workers Are Not Scaling Up (KEDA)

**Symptoms:** Load test is running but `kubectl get pods -n load-tester` shows only 1 pod.

**Diagnosis:**
```bash
kubectl describe scaledobject load-tester -n load-tester
kubectl get hpa -n load-tester
```

**Common causes and fixes:**

**Cause A: Redis not reachable from KEDA**
```bash
kubectl exec -n load-tester deploy/load-tester -- redis-cli -h $REDIS_HOST ping
# Should return: PONG
# If not, check SecurityGroup rules and VPC CIDR configuration
```

**Cause B: KEDA operator not running**
```bash
kubectl get pods -n keda
# keda-operator and keda-operator-metrics-apiserver should be Running
kubectl logs -n keda deploy/keda-operator | tail -20
```

**Cause C: ScaledObject `minReplicaCount` misconfigured**
```bash
kubectl get scaledobject load-tester -n load-tester -o yaml | grep -A5 minReplicaCount
# Should be 1, not 0 (0 would scale to zero when idle, requiring a warm-up period)
```

---

## Problem 5: Falco Is Generating Unexpected Alerts

**Symptoms:** `#chaos-platform-alerts` in Slack is flooded with Falco alerts.

**Diagnosis:**
```bash
kubectl logs -n falco -l app.kubernetes.io/name=falco | grep -E "WARNING|ERROR|CRITICAL" | head -20
```

**Common causes:**

**Cause A: Chaos engine pod kill is triggering "unexpected process exit" rules**
This is expected during a chaos experiment. If you're running an experiment, these alerts can be acknowledged.

**Cause B: A legitimate rule is too broad**
Review the specific rule that's triggering:
```bash
kubectl logs -n falco -l app.kubernetes.io/name=falco | grep "rule:"
```
Locate the rule in `security/falco/falco-rules.yaml` and add a `condition:` exception for the specific container or namespace that's causing false positives.

**Cause C: An actual intrusion**
If alerts appear outside of a known maintenance window:
1. Identify the pod: the alert includes the pod name and namespace
2. Isolate immediately: `kubectl label pod <name> -n <ns> quarantine=true`
3. Add a NetworkPolicy that blocks all traffic from quarantined pods:
   ```bash
   kubectl apply -f security/docs/runbooks/quarantine-network-policy.yaml
   ```
4. Follow the full incident response procedure in `security/docs/runbooks/security-incident-response.md`

---

## Problem 6: Slack Notifications Not Arriving

**Symptoms:** Experiments complete but no Slack message appears in the channel.

**Diagnosis:**
```bash
# Check Lambda function logs
aws logs tail /aws/lambda/chaos-platform-slack-notifier --follow

# Check if SNS is publishing
aws sns list-subscriptions-by-topic --topic-arn $(aws sns list-topics --query 'Topics[?contains(TopicArn, `chaos-notifications`)].TopicArn' --output text)
```

**Common causes and fixes:**

**Cause A: SSM parameter missing**
```bash
aws ssm get-parameter --name /chaos-platform/slack-webhook-url
# If ParameterNotFound:
aws ssm put-parameter --name /chaos-platform/slack-webhook-url --value "https://hooks.slack.com/..." --type SecureString
```

**Cause B: Lambda function throttled or at concurrency limit**
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Throttles \
  --dimensions Name=FunctionName,Value=chaos-platform-slack-notifier \
  --start-time $(date -u -d '1 hour ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 60 --statistics Sum
```

**Cause C: Slack webhook URL expired or invalidated**
Regenerate the webhook in Slack → Manage → Apps → Incoming Webhooks, then update SSM.

---

## Problem 7: Terraform Apply Fails with "Error acquiring the state lock"

**Symptoms:** `terraform apply` fails with: `Error: Error acquiring the state lock`

**Diagnosis:**
```bash
aws dynamodb scan --table-name chaos-platform-terraform-lock
```

**Cause:** A previous `terraform apply` was interrupted before it could release the lock. The DynamoDB table still has a lock record.

**Fix:**
```bash
# Get the lock ID from the error message, then:
terraform force-unlock <LOCK_ID>
```

Only do this if you are certain no other Terraform operation is running. If another engineer is actively running Terraform, do NOT force-unlock.
