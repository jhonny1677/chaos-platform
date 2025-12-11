# Cost Management

## Monthly AWS Cost Breakdown (Development Environment)

This estimate is for the development configuration: SPOT t3.medium nodes, single NAT Gateway, minimal data transfer.

| Service | Configuration | Estimated Monthly Cost |
|---|---|---|
| EKS Control Plane | 1 cluster | $73.00 |
| EC2 (SPOT t3.medium) | 3 nodes × 24h × 30 days × ~$0.015/hr | ~$32.00 |
| NAT Gateway | 1 gateway + data processing | ~$35.00 |
| MSK (Kafka) | kafka.t3.small × 2 brokers | ~$100.00 |
| ElastiCache Redis | cache.t3.micro × 1 node | ~$25.00 |
| RDS PostgreSQL | db.t3.micro, 20GB storage | ~$18.00 |
| S3 | ~50GB across all buckets | ~$1.15 |
| DynamoDB | On-demand, low traffic | ~$2.00 |
| ECR | 4 repos × ~500MB | ~$2.00 |
| Lambda | 1M invocations, 512MB | ~$3.00 |
| CloudWatch Logs | ~10GB/month | ~$5.00 |
| X-Ray Traces | 100K traces/month | ~$0.50 |
| EventBridge | Minimal | ~$0.10 |
| SNS | Minimal | ~$0.10 |
| **Total** | | **~$297/month** |

**Note:** The two largest costs are EKS control plane ($73) and MSK ($100). These are fixed costs regardless of usage.

---

## Running Cost Estimate

Before starting a session, estimate the cost:

```bash
# Check how long the cluster has been running
aws eks describe-cluster --name chaos-platform-dev \
  --query 'cluster.createdAt' --output text

# Check current month's EC2 spend
aws ce get-cost-and-usage \
  --time-period Start=$(date +%Y-%m-01),End=$(date +%Y-%m-%d) \
  --granularity MONTHLY \
  --filter '{"Dimensions": {"Key": "SERVICE", "Values": ["Amazon EC2"]}}' \
  --metrics BlendedCost \
  --query 'ResultsByTime[0].Total.BlendedCost.Amount' \
  --output text
```

---

## Cost Reduction Strategies

### Option 1: Tear Down When Not in Use (Maximum Savings)

Destroy the entire environment at the end of each work session. Takes 15 minutes to restore via Terraform.

```bash
# Save your work first
git add -A && git commit -m "save state before teardown"

# Destroy everything
cd terraform/environments/dev
terraform destroy -auto-approve

# Next session: rebuild
terraform apply -auto-approve
./scripts/bootstrap.sh
./security/vault/scripts/init-vault.sh
```

**Savings: ~$280/month if only running 8 hours per weekday**

### Option 2: Scale Down Nodes When Idle (Moderate Savings)

Keep the cluster alive but scale node groups to 0 when not in use. EKS control plane still costs $73/month.

```bash
# Scale down (end of day)
aws eks update-nodegroup-config \
  --cluster-name chaos-platform-dev \
  --nodegroup-name chaos-platform-dev-nodes \
  --scaling-config minSize=0,maxSize=5,desiredSize=0

# Scale up (start of day)
aws eks update-nodegroup-config \
  --cluster-name chaos-platform-dev \
  --nodegroup-name chaos-platform-dev-nodes \
  --scaling-config minSize=1,maxSize=5,desiredSize=3
```

**Savings: ~$32/month on EC2 (node costs only)**

### Option 3: Replace MSK with a Single-Node Kafka (Large Savings)

MSK requires 2 brokers minimum. For development, deploy a single Kafka pod inside the cluster instead:

```bash
helm install kafka bitnami/kafka \
  --set replicaCount=1 \
  --set zookeeper.replicaCount=1 \
  -n kafka --create-namespace
```

**Savings: ~$100/month** (but: no MSK managed ops, manual SASL config)

### Option 4: Spot Interruption Handling

Already implemented — nodes use SPOT instances. The cluster uses Cluster Autoscaler with node draining to handle SPOT interruptions gracefully.

---

## Setting Up Billing Alerts

The Terraform creates a $300 CloudWatch billing alarm automatically. To verify:

```bash
aws cloudwatch describe-alarms \
  --alarm-name-prefix chaos-platform \
  --query 'MetricAlarms[].{Name:AlarmName,Threshold:Threshold,State:StateValue}'
```

To add a lower warning threshold:
```bash
aws cloudwatch put-metric-alarm \
  --alarm-name chaos-platform-cost-warning \
  --alarm-description "Chaos Platform monthly cost warning at $150" \
  --metric-name EstimatedCharges \
  --namespace AWS/Billing \
  --statistic Maximum \
  --period 86400 \
  --evaluation-periods 1 \
  --threshold 150 \
  --comparison-operator GreaterThanThreshold \
  --dimensions Name=Currency,Value=USD \
  --alarm-actions arn:aws:sns:us-east-1:ACCOUNT_ID:chaos-platform-alerts \
  --ok-actions arn:aws:sns:us-east-1:ACCOUNT_ID:chaos-platform-alerts
```

---

## Complete Teardown

To destroy all resources and stop all billing:

```bash
# 1. Empty S3 buckets (Terraform cannot delete non-empty buckets)
for bucket in $(aws s3 ls | awk '{print $3}' | grep chaos-platform); do
  aws s3 rm s3://$bucket --recursive
done

# 2. Deregister all Lambda function event source mappings
# (handled by terraform destroy)

# 3. Delete ECR images (optional — storage cost is minimal)
for repo in target-app chaos-engine load-tester dashboard; do
  aws ecr batch-delete-image \
    --repository-name $repo \
    --image-ids "$(aws ecr list-images --repository-name $repo --query 'imageIds' --output json)"
done

# 4. Destroy all Terraform resources
cd terraform/environments/dev
terraform destroy

# 5. Confirm nothing is left running
aws eks list-clusters
aws rds describe-db-instances
aws elasticache describe-cache-clusters
aws kafka list-clusters
```

After `terraform destroy` completes, the only remaining charges should be:
- S3 storage for the Terraform state file (pennies per month)
- CloudWatch Logs retention (pennies per month)

These can be cleaned up manually if needed:
```bash
# Delete Terraform state bucket (WARNING: cannot recover state after this)
aws s3 rb s3://chaos-platform-dev-terraform-state --force

# Delete DynamoDB lock table
aws dynamodb delete-table --table-name chaos-platform-terraform-lock
```
