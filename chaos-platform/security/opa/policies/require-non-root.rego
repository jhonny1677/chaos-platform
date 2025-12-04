# require-non-root.rego
#
# Security rationale: Running containers as root means that if an attacker
# escapes the container they have root on the host node — game over for the
# entire cluster. Running as non-root and with a read-only root filesystem
# dramatically reduces the blast radius of a container escape.
#
# readOnlyRootFilesystem prevents attackers from writing malicious binaries
# to the container — any persistence attempt requires a writable volume
# mount, which is easier to audit and detect.

package require_non_root

import future.keywords.in

default allow := false
allow {
  not deny[_]
}

# Deny containers without runAsNonRoot: true
deny[msg] {
  input.kind == "Pod"
  some container in input.spec.containers
  not container.securityContext.runAsNonRoot
  msg := sprintf(
    "Container '%v' must set securityContext.runAsNonRoot: true. Running as root is not permitted.",
    [container.name]
  )
}

# Deny containers that explicitly set runAsUser: 0 (root)
deny[msg] {
  input.kind == "Pod"
  some container in input.spec.containers
  container.securityContext.runAsUser == 0
  msg := sprintf(
    "Container '%v' explicitly runs as UID 0 (root). Use a non-zero UID.",
    [container.name]
  )
}

# Deny containers without readOnlyRootFilesystem: true
deny[msg] {
  input.kind == "Pod"
  some container in input.spec.containers
  not container.securityContext.readOnlyRootFilesystem
  msg := sprintf(
    "Container '%v' must set securityContext.readOnlyRootFilesystem: true to prevent filesystem tampering.",
    [container.name]
  )
}

# Also check pod-level security context — if set at pod level but not
# overridden at container level it still applies.
deny[msg] {
  input.kind == "Pod"
  not input.spec.securityContext.runAsNonRoot
  count(input.spec.containers) > 0
  # Only flag if no container-level override exists anywhere
  every container in input.spec.containers {
    not container.securityContext.runAsNonRoot
  }
  msg := "Pod does not set securityContext.runAsNonRoot: true at the pod or container level."
}
