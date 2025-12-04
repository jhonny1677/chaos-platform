# require-labels.rego
#
# Security rationale (also operational): Labels are the primary mechanism for
# associating Kubernetes resources — NetworkPolicy selectors, RBAC, monitoring
# service discovery, and chaos experiment targeting all rely on labels.
#
# Missing labels cause:
#   - NetworkPolicies failing to apply → default-deny rules drop all traffic
#   - Prometheus service discovery missing pods → blind spots in monitoring
#   - Chaos experiments accidentally targeting wrong pods (wrong label selector)
#   - Audit logs lacking service context
#
# Required labels:
#   app                          — identifies the workload (e.g. chaos-engine)
#   version                      — enables canary deployments and rollback tracking
#   app.kubernetes.io/part-of    — links to the platform (chaos-platform)
#
# Required namespace labels:
#   environment                  — dev/staging/prod; gating mechanism for
#                                   deny-public-services and other policies

package require_labels

import future.keywords.in

required_pod_labels := {"app", "version", "app.kubernetes.io/part-of"}
required_namespace_labels := {"environment"}

default allow := false
allow {
  not deny[_]
}

# Deny pods missing required labels
deny[msg] {
  input.kind == "Pod"
  some required_label in required_pod_labels
  not input.metadata.labels[required_label]
  msg := sprintf(
    "Pod '%v' is missing required label '%v'. Required labels: %v",
    [input.metadata.name, required_label, required_pod_labels]
  )
}

# Deny namespaces missing environment label
deny[msg] {
  input.kind == "Namespace"
  some required_label in required_namespace_labels
  not input.metadata.labels[required_label]
  msg := sprintf(
    "Namespace '%v' is missing required label '%v'. Add: kubectl label namespace %v environment=<dev|staging|prod>",
    [input.metadata.name, required_label, input.metadata.name]
  )
}

# Warn on empty label values (not a hard deny, but flag it)
deny[msg] {
  input.kind == "Pod"
  input.metadata.labels.app == ""
  msg := "Pod has an 'app' label but its value is empty. Provide a meaningful service name."
}
