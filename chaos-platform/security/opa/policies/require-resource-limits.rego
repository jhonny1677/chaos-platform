# require-resource-limits.rego
#
# Security rationale: Containers without resource limits can consume unbounded
# CPU and memory, causing noisy-neighbour problems that cascade into outages
# across the entire cluster. During chaos experiments this is especially
# dangerous — a misbehaving container can kill the very infrastructure we're
# trying to test.
#
# This policy denies admission of any Pod that omits CPU or memory
# requests/limits. kube-system is exempt because system components like
# coredns are managed by the cluster itself.

package require_resource_limits

import future.keywords.in
import future.keywords.every

# Namespaces excluded from this policy
exempt_namespaces := {"kube-system", "kube-public", "kube-node-lease"}

default allow := false
allow {
  not deny[_]
}

# Deny if any container is missing a CPU limit
deny[msg] {
  input.kind == "Pod"
  not input.metadata.namespace in exempt_namespaces
  some container in input.spec.containers
  not container.resources.limits.cpu
  msg := sprintf("Container '%v' in pod '%v' is missing a CPU limit. All containers must declare resource limits.", [container.name, input.metadata.name])
}

# Deny if any container is missing a memory limit
deny[msg] {
  input.kind == "Pod"
  not input.metadata.namespace in exempt_namespaces
  some container in input.spec.containers
  not container.resources.limits.memory
  msg := sprintf("Container '%v' in pod '%v' is missing a memory limit.", [container.name, input.metadata.name])
}

# Deny if any container is missing CPU requests
deny[msg] {
  input.kind == "Pod"
  not input.metadata.namespace in exempt_namespaces
  some container in input.spec.containers
  not container.resources.requests.cpu
  msg := sprintf("Container '%v' in pod '%v' is missing a CPU request. Requests are required for the scheduler to place pods optimally.", [container.name, input.metadata.name])
}

# Deny if any container is missing memory requests
deny[msg] {
  input.kind == "Pod"
  not input.metadata.namespace in exempt_namespaces
  some container in input.spec.containers
  not container.resources.requests.memory
  msg := sprintf("Container '%v' in pod '%v' is missing a memory request.", [container.name, input.metadata.name])
}

# Apply the same rules to init containers
deny[msg] {
  input.kind == "Pod"
  not input.metadata.namespace in exempt_namespaces
  some container in input.spec.initContainers
  not container.resources.limits.cpu
  msg := sprintf("Init container '%v' in pod '%v' is missing a CPU limit.", [container.name, input.metadata.name])
}

deny[msg] {
  input.kind == "Pod"
  not input.metadata.namespace in exempt_namespaces
  some container in input.spec.initContainers
  not container.resources.limits.memory
  msg := sprintf("Init container '%v' in pod '%v' is missing a memory limit.", [container.name, input.metadata.name])
}
