# ADR-005: Both Kyverno AND OPA Instead of Just One

**Status:** Accepted  
**Date:** 2026-03-15  
**Deciders:** Platform Team

---

## Context

Kubernetes admission control allows you to intercept every resource creation/update and either approve it, deny it, or mutate it before it's persisted. This is how you enforce policies like "all containers must be non-root" without relying on individual developers to remember.

Two major tools exist for this: **OPA/Gatekeeper** (using Rego policies) and **Kyverno** (using YAML-native policies). The question was: do we use one or both?

---

## Decision

We use **both Kyverno and OPA/Gatekeeper**, each for what it does best:

**OPA/Gatekeeper** for policies that require complex logic:
- Registry allowlist (requires prefix matching and tag validation logic)
- Deny public services (requires checking both type and namespace)
- Non-root validation (requires checking both pod-level and container-level security context with fallback logic)
- All OPA policies have companion unit tests (`.rego` test files)

**Kyverno** for policies that are configuration-like rather than logic-heavy:
- Require resource limits (simple "field must exist" check)
- Disallow latest tag (simple string suffix check)
- Add default labels (mutate policy — simpler in Kyverno YAML than Rego)
- Require read-only root filesystem

---

## Consequences

**Good:**
- OPA Rego is significantly more expressive than Kyverno's YAML patterns. Complex allowlist logic with multiple conditions is readable in Rego and unreadable in Kyverno YAML.
- Kyverno's YAML format is immediately readable by engineers who have never written a policy. `pattern: spec.containers[*].resources.limits.memory: "?*"` is self-explanatory.
- Kyverno supports **Mutate** policies natively — automatically adding labels to pods. OPA/Gatekeeper can mutate but requires additional tooling (OPA Mutations are experimental).
- OPA policies can be unit-tested with `opa test` — this is first-class in OPA and allows TDD for security policies.
- Using both tools provides defense in depth: a misconfiguration in one admission webhook doesn't remove all policy enforcement.

**Bad / Trade-offs:**
- Two separate tools to learn, maintain, and monitor.
- Two sets of Helm charts to update.
- Engineers need to know which tool enforces which policy — added cognitive overhead.
- There is some policy overlap (e.g., both tools check image registries) — this is intentional for defense in depth but does cause duplicate denial messages in some edge cases.
- Two admission webhooks add latency to resource creation (~50ms each in practice, barely noticeable).

---

## Alternatives Considered

**OPA/Gatekeeper only:**  
- Fully expressive, unit-testable, widely used  
- Rejected because: no native mutate support, YAML is verbose for simple "field must exist" checks, steeper learning curve for new engineers  

**Kyverno only:**  
- Excellent UX, native K8s YAML, mutate + validate + generate in one tool  
- Rejected because: complex logic is difficult in the pattern-matching DSL, no unit test framework, regex support limited  

**Built-in Pod Security Admission (PSA):**  
- Free, built into Kubernetes 1.25+, no extra controller needed  
- Not sufficient: only enforces a limited set of security standards (Privileged/Baseline/Restricted), cannot enforce custom policies like "only images from our ECR"  

---

## Lessons Learned

The biggest lesson from running both tools: **start in Audit mode**. Both Kyverno and OPA/Gatekeeper support `Audit` enforcement action — this logs violations without blocking anything. We ran in Audit for two weeks before switching to Enforce, which revealed several legitimate workloads that would have been denied by the initial policy definitions (specifically: Falco's DaemonSet needing `privileged: true`, and the OTel Collector needing `hostNetwork`). Running in Audit first prevented self-inflicted outages.
