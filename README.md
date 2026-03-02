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

curl -X POST "http://localhost:8000/queue/my-queue/pop"
```

### Install as NuGet Package

```bash
dotnet add package PushPopActor
```

```csharp
using Dapr.Actors;
using Dapr.Actors.Client;
using PushPopActor.Interfaces;

// Create a queue
var proxy = ActorProxy.Create<IPushPopActor>(
    new ActorId("my-queue"),
    "PushPopActor"
);

// Push items with priorities
await proxy.Push(new PushRequest
{
    ItemJson = "{\"task\": \"urgent\"}",
    Priority = 0
}); // High

await proxy.Push(new PushRequest
{
    ItemJson = "{\"task\": \"normal\"}",
    Priority = 5
}); // Low

// Pop single item (priority 0 comes first)
var result = await proxy.Pop();  // Returns PopResponse with items list
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
- **Segmented storage** (v4.0+): Queues split into 100-item segments for optimal performance

### Architecture Overview

Each actor instance uses a **segmented queue architecture** (v4.0+) where large queues are split into fixed-size segments (default: 100 items). This prevents memory/network bottlenecks when queues grow large.

State is stored as: `queue_0_seg_0`, `queue_0_seg_1`, `queue_1_seg_0`, etc., plus a `metadata` map with segment pointers. Pop operations drain from priority 0 completely before moving to priority 1, and so on.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for technical details.

## Performance

**Time Complexity:**
- `Push`: O(1) amortized append operation
- `Pop()`: O(k) where k = number of priority levels with items
  - Scans priorities 0 → N to find first item (O(k))
  - Removes 1 item from front of segment (O(1))

**Space Complexity:**
- O(n) where n = total items in queue
- **Segmented storage** (v4.0+): Max 100 items loaded per operation (vs entire queue)

**I/O Operations:**
- Push: 2 state store operations (segment + metadata)
- Pop: 2 state store operations (segment + metadata)

**Memory Efficiency:**
- **Small queues** (<100 items): 1 segment, minimal overhead
- **Large queues** (10k+ items): Load max 100 items per operation (vs 10k in v3.x)
  - Example: 10,000 item queue uses ~10-50KB memory per operation (was 1-5MB)

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for optimization strategies.

## Documentation

- **[Quick Start Guide](docs/QUICKSTART.md)** - Get running in minutes
- **[API Reference](docs/API_REFERENCE.md)** - Complete method documentation
- **[Architecture](docs/ARCHITECTURE.md)** - How it works under the hood
- **[Examples](examples/)** - Code samples and patterns

## Requirements

- .NET 10.0+
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
