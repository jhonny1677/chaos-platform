#!/usr/bin/env bash
# seal-secret.sh — Create a SealedSecret from a plaintext Kubernetes Secret.
#
# Usage:
#   bash security/sealed-secrets/scripts/seal-secret.sh \
#     --name my-secret \
#     --namespace chaos-engine \
#     --from-literal key1=value1 \
#     --from-literal key2=value2 \
#     --output sealed-secret.yaml
#
# Or from an existing secret file:
#   bash security/sealed-secrets/scripts/seal-secret.sh \
#     --file /tmp/plaintext-secret.yaml \
#     --output sealed-secret.yaml
#
# Prerequisites:
#   - kubeseal CLI: brew install kubeseal  OR  snap install kubeseal
#   - kubectl configured for the target cluster
#   - Sealed Secrets controller running: kubectl get pods -n kube-system -l app=sealed-secrets
#
# SAFETY: This script NEVER writes the plaintext secret to disk.
#         It pipes the plaintext directly to kubeseal via stdin.
#         The output file (--output) contains only the encrypted form.

set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { printf "${GREEN}  ✓ %s${NC}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${NC}\n" "$*" >&2; exit 1; }
info() { printf "${BLUE}  ➜ %s${NC}\n" "$*"; }

SECRET_NAME=""
SECRET_NAMESPACE="default"
OUTPUT_FILE=""
SOURCE_FILE=""
LITERALS=()
CLUSTER_WIDE="false"

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --name)        SECRET_NAME="${2:?--name requires a value}"; shift 2;;
    --namespace)   SECRET_NAMESPACE="${2:?--namespace requires a value}"; shift 2;;
    --output)      OUTPUT_FILE="${2:?--output requires a value}"; shift 2;;
    --file)        SOURCE_FILE="${2:?--file requires a value}"; shift 2;;
    --from-literal) LITERALS+=("${2:?--from-literal requires a value}"); shift 2;;
    --cluster-wide) CLUSTER_WIDE="true"; shift;;
    *) err "Unknown argument: $1";;
  esac
done

# ── Validate ──────────────────────────────────────────────────────────────────
command -v kubeseal &>/dev/null || err "kubeseal not found. Install with: brew install kubeseal"
command -v kubectl  &>/dev/null || err "kubectl not found"

if [[ -z "${OUTPUT_FILE}" ]]; then
  err "--output is required (path where the sealed secret YAML will be written)"
fi

if [[ -z "${SOURCE_FILE}" ]] && [[ -z "${SECRET_NAME}" ]]; then
  err "Either --file or --name must be specified"
fi

# ── Check controller is running ───────────────────────────────────────────────
info "Checking Sealed Secrets controller..."
kubectl get pods -n kube-system -l app.kubernetes.io/name=sealed-secrets --no-headers 2>/dev/null | grep -q Running || \
  err "Sealed Secrets controller not found or not running in kube-system. Install with: helm install sealed-secrets sealed-secrets/sealed-secrets -n kube-system"
ok "Sealed Secrets controller is running"

# ── Fetch the public key (optional — kubeseal fetches it automatically) ──────
# Caching the cert avoids API calls per seal operation (useful in CI)
CERT_FILE="${TMPDIR:-/tmp}/sealed-secrets-cert.pem"
if [[ ! -f "${CERT_FILE}" ]] || [[ $(find "${CERT_FILE}" -mmin +60 2>/dev/null) ]]; then
  info "Fetching Sealed Secrets public key..."
  kubeseal --fetch-cert > "${CERT_FILE}"
  ok "Public key cached at ${CERT_FILE}"
fi

# ── Seal the secret ───────────────────────────────────────────────────────────
KUBESEAL_OPTS=("--format=yaml" "--cert=${CERT_FILE}")
if [[ "${CLUSTER_WIDE}" == "true" ]]; then
  KUBESEAL_OPTS+=("--scope=cluster-wide")
  info "Using cluster-wide scope (SealedSecret can be deployed to any namespace)"
fi

if [[ -n "${SOURCE_FILE}" ]]; then
  info "Sealing secret from file: ${SOURCE_FILE}"
  kubeseal "${KUBESEAL_OPTS[@]}" < "${SOURCE_FILE}" > "${OUTPUT_FILE}"
else
  info "Sealing secret '${SECRET_NAME}' in namespace '${SECRET_NAMESPACE}'..."

  # Build --from-literal args
  LITERAL_ARGS=()
  for lit in "${LITERALS[@]}"; do
    LITERAL_ARGS+=(--from-literal "${lit}")
  done

  # Pipe plaintext secret directly to kubeseal — never touches disk
  kubectl create secret generic "${SECRET_NAME}" \
    --namespace "${SECRET_NAMESPACE}" \
    "${LITERAL_ARGS[@]}" \
    --dry-run=client -o yaml \
  | kubeseal "${KUBESEAL_OPTS[@]}" > "${OUTPUT_FILE}"
fi

ok "SealedSecret written to: ${OUTPUT_FILE}"
printf "\n${GREEN}Done!${NC}\n"
printf "  Add to git: git add %s && git commit -m 'secret: seal %s'\n" "${OUTPUT_FILE}" "${SECRET_NAME}"
printf "  Apply:      kubectl apply -f %s\n" "${OUTPUT_FILE}"
printf "  Verify:     bash security/sealed-secrets/scripts/unseal-verify.sh %s\n\n" "${OUTPUT_FILE}"
