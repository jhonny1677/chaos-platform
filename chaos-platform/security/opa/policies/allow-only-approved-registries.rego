# allow-only-approved-registries.rego
#
# Security rationale: Images from unapproved registries may contain malware,
# cryptominers, or backdoors. Supply chain attacks increasingly target the
# image layer. Restricting to our ECR registry (where every image is scanned
# by Trivy before push) and docker.io/library (official Docker images with
# known provenance) dramatically reduces supply chain risk.
#
# :latest tag is banned because it is not reproducible — the same deployment
# can pull different code at different times, making rollbacks unreliable and
# security audits meaningless.

package allow_only_approved_registries

import future.keywords.in

# These are the only approved image sources
approved_prefixes := {
  # Our ECR — all images here were scanned by the CI pipeline
  "REPLACE_WITH_AWS_ACCOUNT_ID.dkr.ecr.REPLACE_WITH_REGION.amazonaws.com/chaos-platform/",
  # Official Docker Hub images (busybox, postgres, nginx, etc.)
  "docker.io/library/",
  # Unqualified official images resolve to docker.io/library
  "busybox",
  "postgres",
  "nginx",
  "redis",
  "python",
  "node",
  # Grafana public images used for observability
  "grafana/",
  "prom/",
  "otel/",
  "hashicorp/vault",
}

default allow := false
allow {
  not deny[_]
}

# Check if an image comes from an approved registry
image_approved(image) {
  some prefix in approved_prefixes
  startswith(image, prefix)
}

# Deny images from unapproved registries
deny[msg] {
  input.kind == "Pod"
  some container in input.spec.containers
  not image_approved(container.image)
  msg := sprintf(
    "Container '%v' uses image '%v' from an unapproved registry. Allowed prefixes: %v",
    [container.name, container.image, approved_prefixes]
  )
}

# Deny :latest tag — not reproducible
deny[msg] {
  input.kind == "Pod"
  some container in input.spec.containers
  endswith(container.image, ":latest")
  msg := sprintf(
    "Container '%v' uses the ':latest' tag on image '%v'. Pin to a specific digest or semver tag.",
    [container.name, container.image]
  )
}

# Images with no tag default to :latest — also deny
deny[msg] {
  input.kind == "Pod"
  some container in input.spec.containers
  not contains(container.image, ":")
  msg := sprintf(
    "Container '%v' image '%v' has no tag. Untagged images resolve to :latest which is not reproducible.",
    [container.name, container.image]
  )
}
