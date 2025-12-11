# ADR-002: Kafka (MSK) for Message Streaming Instead of SQS

**Status:** Accepted  
**Date:** 2026-01-15  
**Deciders:** Platform Team

---

## Context

The chaos platform needs to propagate events between components:
- Chaos engine → dashboard (live experiment progress)
- Chaos engine → report generator (experiment completed)
- Load tester → dashboard (live stats)
- Alertmanager → Slack notifier (alert fired)

We needed a message transport that supports:
1. **Ordered delivery** — chaos events must arrive in sequence (pod-killed must come before experiment-completed)
2. **Replay** — engineers want to replay the event stream from a past experiment for debugging
3. **Multiple consumers** — the dashboard and the report generator both need to receive the same experiment events
4. **Persistent storage** — events should survive consumer restarts

---

## Decision

We chose **Apache Kafka (AWS MSK)** as the primary event streaming system.

The `chaos-events` topic stores all chaos experiment events. Kafka's consumer group model means both the dashboard (group `dashboard-consumers`) and the Slack notifier (group `slack-consumers`) receive every event independently.

---

## Consequences

**Good:**
- Events are retained for 7 days by default — engineers can replay the event log to understand exactly what happened during a past experiment.
- Ordered delivery within a partition. We partition by `experimentId` so all events for a single experiment arrive in order.
- Consumer groups allow independent processing — if the dashboard is down, Slack notifications still arrive, and the dashboard catches up when it restarts.
- Schema evolution: Kafka topics use Avro/JSON — we can add new event fields without breaking existing consumers.
- MSK is managed — no Kafka cluster administration required.

**Bad / Trade-offs:**
- More complex operational overhead than SQS: brokers, partitions, consumer groups, offsets.
- MSK has a minimum cost even at low throughput (~$0.10/hr for a development cluster).
- Connection setup is more complex (SASL/SCRAM-SHA-512, VPC, security groups).
- For the Slack notification use case alone, SQS would be simpler.

---

## Alternatives Considered

**Amazon SQS:**  
- Simple, cheap, serverless, great for at-least-once delivery  
- Rejected because: no replay capability (messages deleted after consumption), no ordering (FIFO queues have throughput limits), no multiple-consumer fan-out without SNS fan-out pattern  

**Amazon EventBridge:**  
- Excellent for routing structured events to many targets  
- Rejected because: no persistent event log/replay, limited to AWS targets (not suitable for streaming to dashboard WebSocket)  

**Redis Pub/Sub:**  
- Already in the stack (used for load test live stats)  
- Rejected because: fire-and-forget (no persistence), no consumer groups, messages lost if subscriber is offline  
