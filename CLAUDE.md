# Claude Context: Push-Pop Actor

## Project Overview

**push-pop-actor** is a C# library providing a simple FIFO queue-based Dapr actor for storing and retrieving JSON-serialized data. It's designed for lightweight message queuing, task scheduling, and ordered processing in Dapr applications.

- **Package Name**: `PushPopActor` (NuGet)
- **C# Namespaces**: `PushPopActor`, `PushPopActor.Interfaces`, `PushPopActor.ApiServer`
- **GitHub**: https://github.com/olitomlinson/dapr-push-pop-actor
- **.NET**: 10.0+
- **Dapr**: 1.17.0+

## Project Structure

```
.
├── dotnet/
│   ├── src/
│   │   ├── PushPopActor/                    # Main actor implementation
│   │   │   ├── PushPopActor.cs              # Core actor class
│   │   │   └── PushPopActor.csproj          # Project file
│   │   ├── PushPopActor.Interfaces/         # Actor interfaces and models
│   │   │   ├── IPushPopActor.cs             # Actor interface definition
│   │   │   ├── Models.cs                    # Request/Response models
│   │   │   └── PushPopActor.Interfaces.csproj
│   │   └── PushPopActor.ApiServer/          # ASP.NET Core API server
│   │       ├── Program.cs                   # API server entry point
│   │       ├── Controllers/QueueController.cs # REST API endpoints
│   │       └── PushPopActor.ApiServer.csproj
│   └── tests/
│       └── PushPopActor.Tests/              # Unit tests
│           ├── PushPopActorTests.cs         # xUnit tests
│           └── PushPopActor.Tests.csproj
├── load_tests/                              # Locust load testing (Python)
├── docs/
│   ├── QUICKSTART.md                        # Getting started guide
│   ├── ARCHITECTURE.md                      # Design details
│   └── API_REFERENCE.md                     # Complete API docs
├── dapr/
│   ├── components/                          # Dapr component configs (state store)
│   └── config/                              # Dapr runtime config
└── docker-compose.yml                       # Full stack (PostgreSQL, Dapr, API)

```

## Core API

### Actor Interface

```csharp
using PushPopActor.Interfaces;

// Main methods:
Task<PushResponse> Push(PushRequest request);           // Add to end (FIFO)
Task<PopResponse> Pop();                                // Remove single item from front
Task<PopWithAckResponse> PopWithAck(PopWithAckRequest); // Pop with acknowledgement
Task<AcknowledgeResponse> Acknowledge(AcknowledgeRequest); // Acknowledge popped items
```

### Usage Modes

1. **Library Mode**: Import and register actor in existing Dapr apps
2. **API Server Mode**: Run example REST API (`dapr-push-pop-server`)
3. **Docker Mode**: Full stack with PostgreSQL + Dapr placement

## Key Files

- **[dotnet/src/PushPopActor/PushPopActor.cs](dotnet/src/PushPopActor/PushPopActor.cs)**: Core `PushPopActor` implementation
- **[dotnet/src/PushPopActor.Interfaces/IPushPopActor.cs](dotnet/src/PushPopActor.Interfaces/IPushPopActor.cs)**: Actor interface definition
- **[dotnet/src/PushPopActor.Interfaces/Models.cs](dotnet/src/PushPopActor.Interfaces/Models.cs)**: Request/Response models
- **[dotnet/src/PushPopActor.ApiServer/Program.cs](dotnet/src/PushPopActor.ApiServer/Program.cs)**: ASP.NET Core API server
- **[dotnet/src/PushPopActor.ApiServer/Controllers/QueueController.cs](dotnet/src/PushPopActor.ApiServer/Controllers/QueueController.cs)**: REST API endpoints
- **[dotnet/tests/PushPopActor.Tests/PushPopActorTests.cs](dotnet/tests/PushPopActor.Tests/PushPopActorTests.cs)**: Comprehensive unit tests

## Technology Stack

- **Dapr SDK**: `Dapr.Actors`, `Dapr.AspNetCore`, `Dapr.Client`
- **Web Framework**: ASP.NET Core 10.0 (for API mode)
- **Testing**: xUnit, Moq
- **Language**: C# 13 with .NET 10.0

## Common Commands

```bash
# Build
cd dotnet
dotnet build                                # Build all projects
dotnet build src/PushPopActor              # Build actor library

# Test
dotnet test                                 # Run all tests
dotnet test --logger "console;verbosity=detailed"  # Verbose output

# Run API Server
cd src/PushPopActor.ApiServer
dapr run --app-id push-pop-api \
  --app-port 5000 \
  --resources-path ../../dapr/components \
  -- dotnet run

# Docker
docker-compose up                          # Full stack
```

## Architecture Notes

### Actor Model
- Each actor ID = separate queue instance
- Single-threaded per actor (no race conditions)
- State persisted to Dapr state store (PostgreSQL, Redis, etc.)
- Automatic activation/deactivation via Dapr

### State Management (v4.0+ Segmented Queues)
- **Segmented storage**: Queues split into 100-item segments for performance
- State keys: `queue_0_seg_0`, `queue_0_seg_1`, etc. (priority + segment number)
- Metadata tracks: `head_segment` (pop from), `tail_segment` (push to), `count`
- Format: `List<string>` per segment (max 100 JSON items each)
- Push appends to tail segment, allocates new segment when full (100 items)
- Pop removes from head segment, deletes empty segments automatically
- State saved after every operation
- **Benefits**: Constant memory/network per operation regardless of queue size

### REST API Endpoints
- `POST /queue/{queueId}/push` - Push item
- `POST /queue/{queueId}/pop` - Pop single item
- `GET /health` - Health check

## Development Conventions

### Code Style
- Language: C# 13 with .NET 10.0
- Nullable reference types: Enabled
- Async/await: All actor methods are async Tasks

### Testing
- Framework: xUnit
- Mocking: Moq for IActorStateManager
- Coverage target: >95%
- Test file naming: `*Tests.cs`

### Namespace Patterns
```csharp
// External imports
using Dapr.Actors;
using Dapr.Actors.Runtime;
using Dapr.Client;

// Internal imports
using PushPopActor.Interfaces;
```

## Important Notes

1. **Package Naming**:
   - NuGet package: `PushPopActor`
   - C# namespaces: `PushPopActor`, `PushPopActor.Interfaces`
   - GitHub repo: `dapr-push-pop-actor`

2. **Actor Registration**: Must register `PushPopActor` before creating proxies

3. **Item Format**: Push accepts JSON strings (ItemJson property)

4. **Priority System**: Default priority is 1. Priority 0 is reserved as a "fast lane" for urgent items that need to interrupt normal processing. Lower priority numbers are processed first (0 before 1 before 2, etc.).

5. **FIFO Guarantee**: Items always returned in insertion order within priority

6. **Concurrency**: One operation per actor instance at a time

7. **Direct Actor API Access**: You can interact directly with actors via Dapr's HTTP API for testing and debugging. This allows you to invoke actor methods and inspect state without going through the application's REST API:
   ```bash
   # Invoke actor method directly
   curl -X POST http://localhost:3500/v1.0/actors/PushPopActor/my-queue/method/Push \
     -H "Content-Type: application/json" \
     -d '{"item": {"test": "data"}}'

   # Get actor state directly (useful for debugging)
   curl http://localhost:3500/v1.0/actors/PushPopActor/my-queue/state/queue
   ```
   - Dapr sidecar typically runs on port 3500 (configurable)
   - Actor type: `PushPopActor`
   - State key: `queue`
   - Full API reference: https://docs.dapr.io/reference/api/actors_api/

8. **Nonremoting Actor Invocations**: The API server uses Dapr's nonremoting mechanism (`InvokeMethodAsync`) for actor calls instead of interface-based remoting. This provides better decoupling and enables cross-language scenarios:
   ```csharp
   // Nonremoting approach (used by API server)
   var proxy = ActorProxy.Create(actorId, "PushPopActor");
   var result = await proxy.InvokeMethodAsync<PushRequest, PushResponse>("Push", request);

   // Remoting approach (still supported for library users)
   var proxy = ActorProxy.Create<IPushPopActor>(actorId, "PushPopActor");
   var result = await proxy.Push(request);
   ```
   - Both approaches work with the same actor implementation
   - Nonremoting is recommended for API servers and cross-language scenarios
   - Remoting is convenient for type-safe C# applications

## Future Considerations

- Max queue size limits (currently unbounded)
- Batch push operations (currently one-at-a-time)
- Queue metrics/monitoring endpoints
- Alternative state store examples (Redis, CosmosDB)

## Quick Reference Links

- Dapr Docs: https://docs.dapr.io/
- Dapr .NET SDK: https://github.com/dapr/dotnet-sdk
- Project Issues: https://github.com/olitomlinson/dapr-push-pop-actor/issues
