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
Task<PushResponse> Push(PushRequest request);              // Add to end (FIFO)
Task<PopResponse> Pop();                                   // Remove single item from front
Task<PopWithAckResponse> PopWithAck(PopWithAckRequest);    // Pop with acknowledgement (creates lock)
Task<AcknowledgeResponse> Acknowledge(AcknowledgeRequest); // Acknowledge and remove locked items
Task<ExtendLockResponse> ExtendLock(ExtendLockRequest);    // Extend existing lock TTL
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

## Testing & Development Workflow

**CRITICAL: Follow Test-First Development (TDD) Approach**

1. **Write tests BEFORE implementation code** - Always write failing tests first
2. **Run fast feedback tests after EVERY code change** - No exceptions
3. **Use integration tests for final verification** - Before committing

### Fast Feedback Loop (< 5 seconds)

Run unit tests after every code change - NO Docker required:

```bash
cd dotnet
dotnet test tests/PushPopActor.Tests/PushPopActor.Tests.csproj
```

### Full Verification (requires Docker)

Run integration tests before committing:

```bash
./build-and-test.sh
```

### Test Organization

- **Actor unit tests** (28 tests in `PushPopActorTests.cs`): Business logic in `PushPopActor.cs`
- **Controller unit tests** (14 tests in `QueueControllerTests.cs`): HTTP status codes, request validation
- **Integration tests** (15 tests in `PushPopActor.IntegrationTests`): Full stack end-to-end with Dapr + PostgreSQL

### When to Run Tests

- **After every code change**: Run fast unit tests (`dotnet test`)
- **Before committing**: Run full integration tests (`./build-and-test.sh`)
- **After refactoring**: Run both unit and integration tests
- **When fixing bugs**: Write failing test FIRST, then fix code

### Outside-In TDD Workflow (Recommended for New Features)

When adding new features to the API, follow this **outside-in** approach to ensure you build exactly what users need:

**1. Integration Tests First** (Define external API contract)
   - Write failing integration tests that describe the user-facing HTTP API
   - This defines the "what" - what should the feature do from a user's perspective?
   - Tests compile but fail because endpoints don't exist yet
   - Example: `ExtendLock_ValidLock_ExtendsExpiry` - full HTTP flow with real assertions

**2. API Models** (Make integration tests compile)
   - Add request/response models to `ApiServer/Models/ApiModels.cs`
   - Just enough to make integration tests compile and route correctly

**3. Controller Tests** (Define HTTP layer behavior)
   - Write failing controller unit tests using mocked actor responses
   - Test HTTP status code mappings: 200 OK, 400 Bad Request, 404 Not Found, 410 Gone, etc.
   - Verify error handling and response transformations
   - Example: `ExtendLock_LockExpired_Returns410`

**4. Actor Interface Models** (Make controller tests compile)
   - Add actor request/response models to `Interfaces/Models.cs`
   - Update `IPushPopActor.cs` interface
   - Add method name constant to `ActorMethodNames.cs`

**5. Implement Controller Logic** (Make controller tests pass)
   - Implement the controller endpoint
   - Map actor responses to HTTP status codes
   - Handle error cases appropriately

**6. Actor Tests** (Define business logic)
   - Write failing actor unit tests with mocked `IActorStateManager`
   - Test all business logic paths: success, validation errors, edge cases
   - Example: `ExtendLock_MultipleExtensions_Accumulates`

**7. Implement Actor Logic** (Make actor tests pass)
   - Implement the actor method in `PushPopActor.cs`
   - Focus on correctness - tests guide the implementation
   - All tests should now pass ✅

**Why Outside-In?**
- ✅ Ensures you build what users actually need (not over-engineering)
- ✅ Integration tests fail early if layers don't connect properly
- ✅ Each layer is tested independently (fast feedback)
- ✅ Prevents implementing features that don't match API design
- ✅ Clear progression: external contract → HTTP layer → business logic

**Fast Feedback Loop:**
```bash
# After each implementation step, run relevant tests
dotnet test --filter "FullyQualifiedName~ExtendLock"  # Run specific feature tests
dotnet test                                            # Run all unit tests (fast)
./build-and-test.sh                                   # Run integration tests (slow)
```

### Traditional TDD Workflow (For Internal Changes)

For changes that don't affect the external API (refactoring, bug fixes, internal optimizations):

1. Write failing test that describes desired behavior
2. Run test to confirm it fails (red) ❌
3. Write minimal code to make test pass (green) ✅
4. Refactor while keeping tests green
5. Run fast tests after each change
6. Commit only when all tests pass

### Controller Testing Architecture

The API server uses `IActorInvoker` abstraction for testability:

```csharp
// Interface enables mocking in unit tests
public interface IActorInvoker
{
    Task<TResponse> InvokeMethodAsync<TResponse>(...);
    Task<TResponse> InvokeMethodAsync<TRequest, TResponse>(...);
}

// Implementation wraps Dapr's ActorProxy
public class DaprActorInvoker : IActorInvoker { ... }
```

This pattern enables controller unit tests to mock actor responses and verify HTTP status code mappings without requiring Dapr runtime.

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
- `POST /queue/{queueId}/pop` - Pop single item (with optional `require_ack` header for locking)
- `POST /queue/{queueId}/acknowledge` - Acknowledge and remove locked item
- `POST /queue/{queueId}/extend-lock` - Extend existing lock TTL
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
