# ADR-001: Python for Backend Services

**Status:** Accepted  
**Date:** 2026-01-01  
**Deciders:** Platform Team

---

## Context

The chaos engine and load tester are both IO-bound services. The chaos engine spends most of its time waiting for:
- Kubernetes API responses (pod status polling, pod deletion confirmation)
- Prometheus query responses (metric collection)
- Kafka publish acknowledgements

The load tester spends most of its time waiting for:
- HTTP responses from the target application
- Redis writes (stat aggregation)

We needed a language that handles concurrent IO efficiently, has a strong Kubernetes client library, and is fast to iterate in during development.

The three serious candidates were Python, Go, and Java.

---

## Decision

We chose **Python 3.11** for all backend services (chaos engine, load tester, target app).

---

## Consequences

**Good:**
- `asyncio` + `httpx` provides excellent concurrent IO performance without the complexity of goroutines. The load tester can maintain 10,000 concurrent connections from a single process.
- The `kubernetes` client library is maintained by the Kubernetes project itself and covers the full API.
- `FastAPI` provides automatic OpenAPI documentation — the chaos engine API is self-documenting with zero extra code.
- Development velocity is high. Complex features like the circuit breaker were implemented in ~50 lines.
- `pytest` with `asyncio` support makes testing async code straightforward.
- Familiarity: Python is the most commonly known language across the engineering team.

**Bad / Trade-offs:**
- Python is not ideal for CPU-bound work. If we ever need to do heavy computation (e.g., running chaos algorithm in a tight loop), Go or Rust would be faster.
- Cold start time for the Lambda functions is longer than Go (~300ms vs ~50ms). For Lambda functions triggered by EventBridge (not latency-sensitive), this is acceptable.
- GIL prevents true multi-threading. We work around this entirely with `asyncio` (single-threaded event loop, no shared state).
- Type hints are optional and not enforced at runtime — requires discipline to maintain.

---

## Alternatives Considered

**Go:**  
- Excellent performance, true parallelism, small binary size  
- Rejected because: steeper learning curve, the Kubernetes client API is more complex, less familiar to the team  
- Would reconsider for a production chaos engine that needs to handle 100+ concurrent experiments  

**Java (Spring Boot):**  
- Mature ecosystem, excellent for large teams  
- Rejected because: too heavy for Lambda (JAR files >50MB, cold start 2–3 seconds), overkill for services of this size, verbose code for what are fundamentally simple IO-bound tasks  
