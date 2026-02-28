# Architecture Overview

Understanding how PushPopActor works under the hood.

## Core Concepts

### Dapr Actors

PushPopActor is built on Dapr's Virtual Actor pattern:

- **Virtual Actors**: Actors are automatically activated on first use, deactivated when idle
- **Single-Threaded**: Each actor instance processes one operation at a time (no race conditions)
- **Location Transparent**: Actors can be on any node in the cluster
- **Persistent State**: Actor state survives restarts and migrations

### Actor Identity

Each actor instance is uniquely identified by:
- **Actor Type**: `"PushPopActor"`
- **Actor ID**: User-defined string (e.g., `"user-123-tasks"`, `"email-queue"`)

Example: Two queues with different IDs are completely independent:
```python
queue_1 = ActorProxy.create("PushPopActor", ActorId("queue-1"), ...)
queue_2 = ActorProxy.create("PushPopActor", ActorId("queue-2"), ...)
```

## State Management

### State Store

Actor state is persisted in a Dapr state store component:

```
┌─────────────────┐
│  PushPopActor   │
│  (actor-123)    │
└────────┬────────┘
         │
         │ save_state()
         ▼
┌─────────────────┐
│  State Manager  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  State Store    │
│  (PostgreSQL)   │
└─────────────────┘
```

### State Schema

Each actor stores multiple keys in the state store based on priority levels:

**Priority Queue Keys**: `queue_0`, `queue_1`, `queue_2`, ..., `queue_N`
**Value**: JSON array of dictionaries (FIFO-ordered items at that priority)

**Metadata Key**: `metadata`
**Value**: JSON object mapping priority levels to item counts

Example state for actor "my-queue":

```json
// queue_0 (highest priority)
[
  {"task": "urgent_email", "user_id": 123},
  {"task": "critical_alert", "severity": "high"}
]

// queue_1
[
  {"task": "process_upload", "file_id": 456},
  {"task": "generate_report", "type": "monthly"}
]

// metadata (metadata)
{
  "0": 2,
  "1": 2
}
```

### State Operations

**Push Operation:**
1. Extract item and priority from request (default priority: 0)
2. Load queue for that priority level (e.g., `queue_1`) from state store
3. Append new item to end of array
4. Update `metadata` metadata map
5. Save both the queue and metadata back to state store

**Pop Operation:**
1. Load `metadata` metadata to determine which priorities have items
2. Sort priority keys numerically (0, 1, 2, ...)
3. For each priority in order, load its queue (e.g., `queue_0`) and pop single item from front
4. Update the queue key and metadata map
5. Save state and return item to caller

## Actor Lifecycle

### Activation

When an actor is first accessed:

```python
async def _on_activate(self) -> None:
    """Initialize empty queue if it doesn't exist."""
    has_queue, _ = await self._state_manager.try_get_state("queue")
    if not has_queue:
        await self._state_manager.set_state("queue", [])
        await self._state_manager.save_state()
```

### Deactivation

Dapr automatically deactivates idle actors based on `actorIdleTimeout` (default: 1 hour).

When reactivated, state is loaded from state store automatically.

## Concurrency Model

### Single-Threaded Actor

Each actor instance processes one request at a time:

```
Request 1 → Push()  ──▶ [Processing...] ──▶ Response
Request 2 → Pop()   ──▶ [Queued...]     ──▶ [Processing...] ──▶ Response
Request 3 → Push()  ──▶ [Queued...]                ──▶ [Processing...] ──▶ Response
```

This eliminates race conditions - no locks needed!

### Multiple Actor Instances

Different actor IDs run in parallel:

```
Actor "queue-1" → Push()  ─┬─▶ [Processing independently]
Actor "queue-2" → Pop()   ─┼─▶ [Processing independently]
Actor "queue-3" → Push()  ─┴─▶ [Processing independently]
```

## Scalability

### Horizontal Scaling

Actors are distributed across app instances using consistent hashing:

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   App Pod 1  │  │   App Pod 2  │  │   App Pod 3  │
├──────────────┤  ├──────────────┤  ├──────────────┤
│ Actor A, D   │  │ Actor B, E   │  │ Actor C, F   │
└──────────────┘  └──────────────┘  └──────────────┘
       ▲                 ▲                 ▲
       └─────────────────┼─────────────────┘
                         │
                  ┌──────┴──────┐
                  │  Placement  │
                  │   Service   │
                  └─────────────┘
```

### Placement Service

Dapr's placement service:
- Tracks which actors are on which app instances
- Routes requests to correct instance
- Handles actor migration during scaling/failures

## Integration Patterns

### 1. Direct Actor Invocation

```python
from dapr.actor import ActorProxy

proxy = ActorProxy.create(...)
await proxy.Push(item)
```

**Pros:**
- Direct access, no HTTP overhead
- Type-safe with ActorInterface

**Cons:**
- Requires Dapr SDK
- Python-only (or use language-specific SDK)

### 2. REST API

```bash
curl -X POST http://localhost:8000/queue/queue-1/push
```

**Pros:**
- Language-agnostic
- Simple HTTP interface
- Easy to test with curl

**Cons:**
- HTTP overhead
- Requires API server

## Failure Handling

### State Store Failures

If state store is unavailable:
- Push/Pop operations fail and return error
- Actor state manager retries internally
- Caller receives exception after retries exhausted

### Actor Migration

When app instance fails:
1. Placement service detects failure
2. Actor is re-activated on healthy instance
3. State is loaded from state store
4. Operations continue with no data loss

### Exactly-Once Semantics

Dapr actors provide **at-least-once** delivery:
- Operations may be retried on failure
- Implement idempotency in consumers if needed

## Configuration

### Actor Runtime Config

```yaml
actorIdleTimeout: "1h"        # Deactivate after 1 hour of inactivity
actorScanInterval: "30s"      # Check for idle actors every 30s
drainOngoingCallTimeout: "30s"  # Wait 30s for calls during shutdown
drainRebalancedActors: true   # Move actors gracefully during rebalance
```

### State Store Config

```yaml
type: state.postgresql
metadata:
- name: actorStateStore
  value: "true"              # Required for actor state
- name: connectionString
  value: "host=..."          # Database connection
```

### Placement Service

- Runs as separate service (not per-instance)
- Maintains consistent hash ring
- Handles actor distribution and rebalancing

## Comparison to Alternatives

### vs. Redis Queue

**PushPopActor:**
- ✅ Automatic distribution across nodes
- ✅ No Redis dependency (use any Dapr state store)
- ✅ Type-safe interface
- ❌ More overhead (actor framework)

**Redis Queue:**
- ✅ Lower overhead
- ✅ Battle-tested
- ❌ Manual distribution/sharding
- ❌ Requires Redis

### vs. Message Queue (RabbitMQ, Kafka)

**PushPopActor:**
- ✅ Simpler setup
- ✅ Embedded in app (no separate broker)
- ❌ Not designed for high throughput
- ❌ Limited routing/filtering

**Message Queue:**
- ✅ High throughput
- ✅ Advanced routing
- ❌ Complex setup
- ❌ Separate infrastructure

### vs. Cloud Queues (SQS, Azure Queue)

**PushPopActor:**
- ✅ Cloud-agnostic
- ✅ Run locally for dev
- ❌ Self-managed state store

**Cloud Queue:**
- ✅ Fully managed
- ✅ Proven scalability
- ❌ Cloud vendor lock-in
- ❌ Costs scale with usage

## Best Practices

1. **Use Descriptive Actor IDs**: `user-{userId}-tasks` not `queue-123`
2. **Limit Queue Size**: Pop regularly to prevent unbounded growth
3. **Monitor State Store**: Watch database size and performance
4. **Batch Pop Operations**: Pop multiple items to reduce roundtrips
5. **Handle Empty Queue**: Pop returns empty array, not error
6. **Idempotent Consumers**: Operations may be retried on failure

## Limitations

- **Not a Message Broker**: No pub/sub, routing, or dead letter queues
- **In-Memory Queue**: All items loaded into memory during pop
- **Priority-Based Ordering**: Items are FIFO within each priority level (0 = highest priority)
- **No Transactions**: Push/Pop are separate operations
- **State Store Dependency**: Requires configured Dapr state store

## Further Reading

- [Dapr Actors Documentation](https://docs.dapr.io/developing-applications/building-blocks/actors/)
- [Virtual Actor Pattern (Orleans)](https://www.microsoft.com/en-us/research/project/orleans-virtual-actors/)
- [Actor Model (Wikipedia)](https://en.wikipedia.org/wiki/Actor_model)
