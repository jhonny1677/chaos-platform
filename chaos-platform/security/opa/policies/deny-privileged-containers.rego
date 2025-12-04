# deny-privileged-containers.rego
#
# Security rationale: Privileged containers bypass nearly all Linux namespace
# and capability restrictions — they can see and modify the host filesystem,
# load kernel modules, and communicate with any process on the node. This is
# equivalent to root on the bare metal host and completely negates container
# isolation. No legitimate application in this platform needs it.
#
# hostPID/hostNetwork give containers visibility into all host processes and
# network traffic respectively. During chaos experiments this could allow a
# compromised container to interfere with other cluster workloads.
#
# hostPath volumes mount directories from the host node into the container,
# allowing escape via symlink attacks and access to node credentials.

package deny_privileged

import future.keywords.in

default allow := false
allow {
  not deny[_]
}

# Deny privileged containers
deny[msg] {
  input.kind == "Pod"
  some container in input.spec.containers
  container.securityContext.privileged == true
  msg := sprintf(
    "Container '%v' is privileged. Privileged containers bypass all security boundaries.",
    [container.name]
  )
}

# Deny allowPrivilegeEscalation
deny[msg] {
  input.kind == "Pod"
  some container in input.spec.containers
  container.securityContext.allowPrivilegeEscalation == true
  msg := sprintf(
    "Container '%v' allows privilege escalation (allowPrivilegeEscalation: true).",
    [container.name]
  )
}

# Deny hostPID
deny[msg] {
  input.kind == "Pod"
  input.spec.hostPID == true
  msg := "Pod uses hostPID: true — containers can see all processes on the host."
}

# Deny hostNetwork
deny[msg] {
  input.kind == "Pod"
  input.spec.hostNetwork == true
  msg := "Pod uses hostNetwork: true — containers share the node's network namespace."
}

# Deny hostPath volumes
deny[msg] {
  input.kind == "Pod"
  some volume in input.spec.volumes
  volume.hostPath
  msg := sprintf(
    "Pod uses a hostPath volume '%v'. Use PVCs or emptyDir instead to prevent host filesystem access.",
    [volume.name]
  )
}

# Also check init containers
deny[msg] {
  input.kind == "Pod"
  some container in input.spec.initContainers
  container.securityContext.privileged == true
  msg := sprintf("Init container '%v' is privileged.", [container.name])
}
