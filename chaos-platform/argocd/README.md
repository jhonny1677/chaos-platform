# ArgoCD — Chaos Platform GitOps

All application deployments are managed by ArgoCD using the **App of Apps** pattern.

## Architecture

```
app-of-apps          ← single root Application (bootstrap this manually once)
└── argocd/apps/
    ├── monitoring-stack.yaml   [wave -2] Prometheus + Grafana + Loki
    ├── security-stack.yaml     [wave -1] Vault + Sealed Secrets
    ├── target-app.yaml         [wave  1] Fake e-commerce API
    ├── chaos-engine.yaml       [wave  2] Chaos injection engine
    ├── load-tester.yaml        [wave  3] Load testing service + KEDA
    └── dashboard.yaml          [wave  4] React frontend
```

Sync waves control deployment order. Monitoring must be healthy before applications start, so Prometheus scraping works from the first pod.

## Bootstrap (one time per cluster)

```bash
# 1. Install ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# 2. Wait for ArgoCD to be ready
kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=300s

# 3. Create the AppProject first (required for child apps)
kubectl apply -f chaos-platform/argocd/projects/chaos-platform-project.yaml

# 4. Bootstrap the app-of-apps — this creates all other apps automatically
kubectl apply -f chaos-platform/argocd/app-of-apps.yaml

# 5. Get the initial admin password
argocd admin initial-password -n argocd
```

## Access ArgoCD UI

```bash
# Port-forward (or use the Ingress if configured)
kubectl port-forward svc/argocd-server -n argocd 8080:443 &
# Open https://localhost:8080  (username: admin)
```

## GitOps Workflow

1. Developer pushes code → GitHub Actions builds and pushes image to ECR
2. GitHub Actions updates the `image:` tag in `k8s/deployment.yaml` with `[skip ci]` commit
3. ArgoCD detects the manifest change (polls every 3 minutes by default)
4. ArgoCD auto-syncs → `kubectl apply` runs in-cluster → new pods roll out
5. ArgoCD health checks confirm rollout success

## Manual Sync

```bash
# Sync a specific app immediately
argocd app sync chaos-engine

# Force re-sync with pruning
argocd app sync target-app --prune

# Sync all apps
argocd app sync --all
```

## Secrets Handling

- Raw `Secret` resources are **blocked** by the AppProject `namespaceResourceBlacklist`
- Use **SealedSecrets** (`kubeseal`) for encrypted secrets stored in git
- Or use **Vault** with the Vault agent injector sidecar

## CI Token for GitHub Actions

```bash
# Generate a scoped token for the ci-deployer role
argocd proj role create-token chaos-platform ci-deployer --expires-in 8760h
```

Store the token as `ARGOCD_TOKEN` in GitHub Secrets. CI can then call:
```bash
argocd app sync target-app --auth-token "$ARGOCD_TOKEN" --server argocd.chaos-platform.local
```
