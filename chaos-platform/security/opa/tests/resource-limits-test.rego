# resource-limits-test.rego — OPA unit tests for require-resource-limits policy.
#
# Run: opa test security/opa/policies/ security/opa/tests/ -v

package tests.require_resource_limits

import data.require_resource_limits.deny

# ── Fixtures ──────────────────────────────────────────────────────────────────
pod_with_limits := {
  "kind": "Pod",
  "metadata": {
    "name":      "good-pod",
    "namespace": "chaos-engine"
  },
  "spec": {
    "containers": [{
      "name":  "app",
      "image": "myapp:1.0.0",
      "resources": {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits":   {"cpu": "500m", "memory": "512Mi"}
      }
    }]
  }
}

pod_missing_cpu_limit := {
  "kind": "Pod",
  "metadata": {
    "name":      "bad-pod",
    "namespace": "chaos-engine"
  },
  "spec": {
    "containers": [{
      "name":  "app",
      "image": "myapp:1.0.0",
      "resources": {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits":   {"memory": "512Mi"}   # missing cpu limit
      }
    }]
  }
}

pod_missing_memory_limit := {
  "kind": "Pod",
  "metadata": {
    "name":      "bad-pod-2",
    "namespace": "load-tester"
  },
  "spec": {
    "containers": [{
      "name":  "app",
      "image": "myapp:1.0.0",
      "resources": {
        "requests": {"cpu": "100m", "memory": "128Mi"},
        "limits":   {"cpu": "500m"}   # missing memory limit
      }
    }]
  }
}

pod_no_resources := {
  "kind": "Pod",
  "metadata": {
    "name":      "bare-pod",
    "namespace": "chaos-engine"
  },
  "spec": {
    "containers": [{
      "name":  "app",
      "image": "myapp:1.0.0"
      # no resources block at all
    }]
  }
}

kube_system_pod := {
  "kind": "Pod",
  "metadata": {
    "name":      "system-pod",
    "namespace": "kube-system"
  },
  "spec": {
    "containers": [{
      "name":  "dns",
      "image": "coredns:1.11.0"
      # no resources — exempt
    }]
  }
}

# ── Tests ─────────────────────────────────────────────────────────────────────
test_allow_pod_with_all_limits {
  count(deny) == 0 with input as pod_with_limits
}

test_deny_missing_cpu_limit {
  some msg in deny with input as pod_missing_cpu_limit
  contains(msg, "CPU limit")
}

test_deny_missing_memory_limit {
  some msg in deny with input as pod_missing_memory_limit
  contains(msg, "memory limit")
}

test_deny_pod_with_no_resources {
  count(deny) > 0 with input as pod_no_resources
}

test_allow_kube_system_pod_without_limits {
  count(deny) == 0 with input as kube_system_pod
}

test_deny_message_contains_container_name {
  some msg in deny with input as pod_missing_cpu_limit
  contains(msg, "app")   # message should include the container name
}
