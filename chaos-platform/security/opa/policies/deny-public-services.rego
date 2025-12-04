# deny-public-services.rego
#
# Security rationale: LoadBalancer and NodePort Services expose pods directly
# to external networks. In EKS, a LoadBalancer Service immediately provisions
# an Internet-facing ALB/NLB — the wrong service type can accidentally make
# an internal API publicly accessible.
#
# All external traffic should flow through the Ingress controller (nginx),
# which provides TLS termination, auth headers, and rate limiting. Direct
# LoadBalancer services bypass these controls.
#
# NodePort is banned everywhere because it opens a port on every node in the
# cluster (30000-32767 range), bypassing Security Group rules designed for
# specific services.
#
# Exception: ingress-nginx must use LoadBalancer to receive external traffic.
# This is the single controlled entry point for all external access.

package deny_public_services

import future.keywords.in

# These namespaces are allowed to have LoadBalancer services
loadbalancer_allowed_namespaces := {"ingress-nginx", "kube-system"}

default allow := false
allow {
  not deny[_]
}

# Deny LoadBalancer services outside allowed namespaces
deny[msg] {
  input.kind == "Service"
  input.spec.type == "LoadBalancer"
  not input.metadata.namespace in loadbalancer_allowed_namespaces
  msg := sprintf(
    "Service '%v' in namespace '%v' uses type LoadBalancer. This exposes the service externally. Use an Ingress resource instead, or move to the ingress-nginx namespace.",
    [input.metadata.name, input.metadata.namespace]
  )
}

# Deny NodePort services in ALL namespaces (no exceptions)
deny[msg] {
  input.kind == "Service"
  input.spec.type == "NodePort"
  msg := sprintf(
    "Service '%v' in namespace '%v' uses type NodePort. NodePort opens ports on every node and bypasses Security Group rules. Use ClusterIP + Ingress instead.",
    [input.metadata.name, input.metadata.namespace]
  )
}

# Deny Services with explicitly set nodePort fields even if type isn't NodePort
# (misconfiguration that can accidentally expose ports)
deny[msg] {
  input.kind == "Service"
  some port in input.spec.ports
  port.nodePort
  input.spec.type != "NodePort"
  msg := sprintf(
    "Service '%v' specifies nodePort on a non-NodePort service. Remove the nodePort field.",
    [input.metadata.name]
  )
}
