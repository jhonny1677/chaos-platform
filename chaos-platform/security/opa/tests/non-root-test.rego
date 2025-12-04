# non-root-test.rego — OPA unit tests for require-non-root policy.
#
# Run: opa test security/opa/policies/ security/opa/tests/ -v

package tests.require_non_root

import data.require_non_root.deny

# ── Fixtures ──────────────────────────────────────────────────────────────────
compliant_pod := {
  "kind": "Pod",
  "metadata": {"name": "good-pod", "namespace": "chaos-engine"},
  "spec": {
    "securityContext": {
      "runAsNonRoot": true,
      "runAsUser":    1001,
      "fsGroup":      2000
    },
    "containers": [{
      "name":  "app",
      "image": "myapp:1.0.0",
      "securityContext": {
        "runAsNonRoot":           true,
        "readOnlyRootFilesystem": true,
        "allowPrivilegeEscalation": false
      }
    }]
  }
}

root_container := {
  "kind": "Pod",
  "metadata": {"name": "root-pod", "namespace": "chaos-engine"},
  "spec": {
    "containers": [{
      "name":  "app",
      "image": "myapp:1.0.0",
      "securityContext": {
        "runAsNonRoot": false,
        "runAsUser":    0
      }
    }]
  }
}

missing_non_root := {
  "kind": "Pod",
  "metadata": {"name": "no-nonroot", "namespace": "chaos-engine"},
  "spec": {
    "containers": [{
      "name":  "app",
      "image": "myapp:1.0.0",
      "securityContext": {}   # no runAsNonRoot
    }]
  }
}

writable_rootfs := {
  "kind": "Pod",
  "metadata": {"name": "writable-pod", "namespace": "load-tester"},
  "spec": {
    "containers": [{
      "name":  "app",
      "image": "myapp:1.0.0",
      "securityContext": {
        "runAsNonRoot":           true,
        "readOnlyRootFilesystem": false   # writable — violation
      }
    }]
  }
}

explicit_uid_zero := {
  "kind": "Pod",
  "metadata": {"name": "uid-zero-pod", "namespace": "chaos-engine"},
  "spec": {
    "containers": [{
      "name":  "app",
      "image": "myapp:1.0.0",
      "securityContext": {
        "runAsUser": 0   # root by UID
      }
    }]
  }
}

# ── Tests ─────────────────────────────────────────────────────────────────────
test_compliant_pod_allowed {
  count(deny) == 0 with input as compliant_pod
}

test_deny_root_container {
  some msg in deny with input as root_container
  contains(msg, "root")
}

test_deny_explicit_uid_zero {
  some msg in deny with input as explicit_uid_zero
  contains(msg, "UID 0")
}

test_deny_missing_non_root_flag {
  count(deny) > 0 with input as missing_non_root
}

test_deny_writable_root_filesystem {
  some msg in deny with input as writable_rootfs
  contains(msg, "readOnlyRootFilesystem")
}

test_deny_message_includes_container_name {
  some msg in deny with input as root_container
  contains(msg, "app")
}
