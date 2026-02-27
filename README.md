# Dapr Push-Pop Actor

A simple, priority-based FIFO queue implementation using Dapr actors. Store and retrieve dictionaries with built-in priority ordering and persistent state.

## Why Use This?

This library provides a ready-to-use queue abstraction that:

- **Just Works**: Two methods (`Push`, `Pop`) - that's it
- **Priority Support**: Route urgent tasks ahead of normal ones (0 = highest priority)
- **Persistent**: Backed by any Dapr state store (PostgreSQL, Redis, Cosmos DB, etc.)
- **Scalable**: Leverage Dapr's actor placement for distributed queues
- **Flexible**: Use as a library, REST API, or Docker container

Perfect for task scheduling, message buffering, event sourcing, or any scenario where you need ordered, priority-based processing with strict transactional gaurantees.

## Quick Start

**Want to get started quickly?** See [docs/QUICKSTART.md](docs/QUICKSTART.md) for detailed instructions.

### 30-Second Demo

```bash
# Clone and start with Docker
git clone https://github.com/olitomlinson/dapr-push-pop-actor.git
cd dapr-push-pop-actor
docker-compose up

# Test it (in another terminal)
curl -X POST http://localhost:8000/queue/my-queue/push \
  -H "Content-Type: application/json" \
  -d '{"item": {"task": "hello"}, "priority": 0}'

curl -X POST "http://localhost:8000/queue/my-queue/pop?depth=5"
```

### Install as Library

```bash
pip install push-pop-actor
```

```python
from dapr.actor import ActorId, ActorProxy
from push_pop_actor import PushPopActorInterface

# Create a queue
proxy = ActorProxy.create(
    actor_type="PushPopActor",
    actor_id=ActorId("my-queue"),
    actor_interface=PushPopActorInterface
)

# Push items with priorities
await proxy.Push({"item": {"task": "urgent"}, "priority": 0})    # High
await proxy.Push({"item": {"task": "normal"}, "priority": 5})    # Low

# Pop items (priority 0 comes first)
items = await proxy.Pop(10)
```

**See [docs/QUICKSTART.md](docs/QUICKSTART.md) for complete setup instructions and examples.**

## Use Cases

- **Task Queues**: Background job processing with priority levels
- **Message Buffering**: Temporary storage between microservices
- **Event Sourcing**: Store events for ordered replay
- **Workload Distribution**: Route tasks to priority-based worker pools
- **Rate Limiting**: Queue and throttle API requests

## How It Works

Each queue is a Dapr actor instance with:
- **Persistent state** in your configured Dapr state store
- **Priority ordering**: Pop drains priority 0 → 1 → 2 → ... → N
- **FIFO within priority**: Items at the same priority are processed in order
- **Single-threaded**: No race conditions per queue instance
- **Distributed**: Scale across multiple app instances

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details.

## Performance

**Time Complexity:**
- `Push`: O(1) amortized append operation
- `Pop(depth)`: O(k + d) where k = number of priority levels with items, d = depth requested
  - Scans priorities 0 → N to find items (O(k))
  - Removes d items from front of queue (O(d))

**Space Complexity:**
- O(n) where n = total items in queue
- State stored as serialized list in Dapr state store

**I/O Operations:**
- Push: 1 state store write per operation
- Pop: 1 state store read + 1 write per operation

**Typical Performance:**
- Small queues (<1000 items): Sub-millisecond in-memory operations
- Large queues (>10k items): Dominated by state store latency (PostgreSQL: 1-5ms, Redis: <1ms)
- Recommend batching with `Pop(depth=10-100)` to amortize I/O overhead

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for optimization strategies.

## Documentation

- **[Quick Start Guide](docs/QUICKSTART.md)** - Get running in minutes
- **[API Reference](docs/API_REFERENCE.md)** - Complete method documentation
- **[Architecture](docs/ARCHITECTURE.md)** - How it works under the hood
- **[Examples](examples/)** - Code samples and patterns

## Requirements

- Python 3.11+
- Dapr 1.17.0+
- A Dapr-supported state store (PostgreSQL, Redis, Cosmos DB, etc.)

## Contributing

Contributions welcome! Please fork the repository, create a feature branch, add tests, and submit a pull request.

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines (if available), or just open an issue to discuss your ideas.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- **Issues**: [GitHub Issue Tracker](https://github.com/olitomlinson/dapr-push-pop-actor/issues)
- **Discussions**: [Dapr Discord](https://discord.com/invite/ptHhX6jc34)
- **Docs**: [docs.dapr.io](https://docs.dapr.io/)
