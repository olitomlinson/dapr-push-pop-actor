# Claude Context: DaprMQ

## Project Overview

**daprmq** is a C# library providing a simple FIFO queue-based Dapr actor for storing and retrieving JSON-serialized data. It's designed for lightweight message queuing, task scheduling, and ordered processing in Dapr applications.

- **Package Name**: `DaprMQ` (NuGet)
- **C# Namespaces**: `DaprMQ`, `DaprMQ.Interfaces`, `DaprMQ.ApiServer`
- **GitHub**: https://github.com/olitomlinson/dapr-mq
- **.NET**: 10.0+
- **Dapr**: 1.17.0+

## Project Structure

- `dotnet/src/DaprMQ/` - Actor implementation (QueueActor.cs, QueueActor.csproj)
- `dotnet/src/DaprMQ.Interfaces/` - Interfaces and models (IQueueActor.cs, Models.cs)
- `dotnet/src/DaprMQ.ApiServer/` - REST/gRPC API (Program.cs, Controllers/, Services/, Protos/)
- `dotnet/tests/DaprMQ.Tests/` - Unit tests (QueueActorTests.cs, QueueControllerTests.cs, DaprMQGrpcServiceTests.cs)
- `docs/` - QUICKSTART.md, ARCHITECTURE.md, API_REFERENCE.md
- `dapr/components/` - Dapr component configs (state store)
- `dapr/config/` - Dapr runtime config

## Core API

### Actor Interface

```csharp
using DaprMQ.Interfaces;

// Main methods:
Task<PushResponse> Push(PushRequest request);              // Add to end (FIFO)
Task<PopResponse> Pop();                                   // Remove single item from front
Task<PopWithAckResponse> PopWithAck(PopWithAckRequest);    // Pop with acknowledgement (creates lock)
Task<AcknowledgeResponse> Acknowledge(AcknowledgeRequest); // Acknowledge and remove locked items
Task<ExtendLockResponse> ExtendLock(ExtendLockRequest);    // Extend existing lock TTL
```

### Usage Modes

1. **Library Mode**: Import and register actor in existing Dapr apps
2. **API Server Mode**: Run example REST API (`daprmq-server`)
3. **Docker Mode**: Full stack with PostgreSQL + Dapr placement

## Key Files

- **[dotnet/src/DaprMQ/QueueActor.cs](dotnet/src/DaprMQ/QueueActor.cs)**: Core `DaprMQ` implementation
- **[dotnet/src/DaprMQ.Interfaces/IQueueActor.cs](dotnet/src/DaprMQ.Interfaces/IQueueActor.cs)**: Actor interface definition
- **[dotnet/src/DaprMQ.Interfaces/Models.cs](dotnet/src/DaprMQ.Interfaces/Models.cs)**: Request/Response models
- **[dotnet/src/DaprMQ.ApiServer/Program.cs](dotnet/src/DaprMQ.ApiServer/Program.cs)**: ASP.NET Core API server (HTTP + gRPC)
- **[dotnet/src/DaprMQ.ApiServer/Controllers/QueueController.cs](dotnet/src/DaprMQ.ApiServer/Controllers/QueueController.cs)**: REST API endpoints
- **[dotnet/src/DaprMQ.ApiServer/Services/DaprMQGrpcService.cs](dotnet/src/DaprMQ.ApiServer/Services/DaprMQGrpcService.cs)**: gRPC service implementation
- **[dotnet/src/DaprMQ.ApiServer/Protos/daprmq.proto](dotnet/src/DaprMQ.ApiServer/Protos/daprmq.proto)**: gRPC service definition
- **[dotnet/tests/DaprMQ.Tests/QueueActorTests.cs](dotnet/tests/DaprMQ.Tests/QueueActorTests.cs)**: Actor unit tests

## Technology Stack

**Runtime:** C# 13, .NET 10.0 | **Framework:** ASP.NET Core (HTTP + gRPC) | **Dapr:** Dapr.Actors, Dapr.AspNetCore, Dapr.Client | **gRPC:** Grpc.AspNetCore 2.70.0, Protocol Buffers | **Testing:** xUnit, Moq

## Common Commands

```bash
# Build
dotnet build                                          # All projects
dotnet build src/DaprMQ                              # Actor library only

# Test
dotnet test                                           # Run all tests
./build-and-test.sh                                  # Full integration (Docker)

# Run API Server
cd src/DaprMQ.ApiServer
dapr run --app-id daprmq-api --app-port 5000 \
  --resources-path ../../dapr/components -- dotnet run

# Docker
docker-compose up                                     # Full stack
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
dotnet test tests/DaprMQ.Tests/DaprMQ.Tests.csproj
```

### Full Verification (requires Docker)

Run integration tests before committing:

```bash
./build-and-test.sh
```

### Test Organization

- **Actor unit tests** (28 tests in `QueueActorTests.cs`): Business logic in `QueueActor.cs`
- **HTTP controller unit tests** (14 tests in `QueueControllerTests.cs`): HTTP status codes, request validation
- **gRPC service unit tests** (8 tests in `DaprMQGrpcServiceTests.cs`): gRPC status code mappings, error handling
- **Integration tests** (28 tests in `DaprMQ.IntegrationTests`): Full stack end-to-end with Dapr + PostgreSQL (HTTP + gRPC)

### When to Run Tests

- **After every code change**: Run fast unit tests (`dotnet test`)
- **Before committing**: Run full integration tests (`./build-and-test.sh`)
- **After refactoring**: Run both unit and integration tests
- **When fixing bugs**: Write failing test FIRST, then fix code

### Outside-In TDD Workflow (Recommended for New Features)

Follow this workflow to ensure API-first design:

1. **Integration Tests** - Write failing tests for HTTP API contract (what users see)
2. **API Models** - Add ApiModels.cs request/response types (make integration tests compile)
3. **Controller Tests** - Write unit tests with mocked actor, verify HTTP status codes
4. **Actor Models** - Add Interfaces/Models.cs types, update IQueueActor interface
5. **Controller Logic** - Implement controller endpoint (make controller tests pass)
6. **Actor Tests** - Write unit tests with mocked IActorStateManager (business logic)
7. **Actor Logic** - Implement QueueActor method (make all tests pass)

**Why:** Ensures layers connect properly, prevents over-engineering, maintains clear API → business logic progression.

**Fast Feedback:**
```bash
dotnet test --filter "FullyQualifiedName~ExtendLock"  # Feature-specific
dotnet test                                            # All unit tests
./build-and-test.sh                                   # Full integration
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

### gRPC API

The API server exposes equivalent gRPC endpoints alongside HTTP REST APIs on the same port (5000). Both protocols share the same actor invocation logic via `IActorInvoker` abstraction.

**Proto File**: [dotnet/src/DaprMQ.ApiServer/Protos/daprmq.proto](dotnet/src/DaprMQ.ApiServer/Protos/daprmq.proto)

**Service Definition**:
```protobuf
service DaprMQ {
  rpc Push(PushRequest) returns (PushResponse);
  rpc Pop(PopRequest) returns (PopResponse);
  rpc PopWithAck(PopWithAckRequest) returns (PopWithAckResponse);
  rpc Acknowledge(AcknowledgeRequest) returns (AcknowledgeResponse);
  rpc ExtendLock(ExtendLockRequest) returns (ExtendLockResponse);
}
```

**Key Features**:
- **HTTP/2 Binary Protocol**: Lower latency than JSON over HTTP/1.1
- **Type Safety**: Protocol Buffers provide strongly-typed contracts
- **Cross-Language**: Proto files enable client generation in any language

**Port Configuration:**

| Environment | HTTP | gRPC |
|-------------|------|------|
| Local Dev   | 5000 | 5001 |
| Docker Host 1-3 | 8000-8003 | 8100-8103 |
| Docker Gateway | 8002 | 8102 |

**Note:** Separate ports required - Kestrel cannot negotiate HTTP/2 without TLS on same port.

**Status Mappings:** 200→OK(0), 204→OK(empty), 400→INVALID_ARGUMENT(3), 404→NOT_FOUND(5), 410→FAILED_PRECONDITION(9), 423→UNAVAILABLE(14), 500→INTERNAL(13)

**Testing with grpcurl** (use port 5001 for local dev, 810x for docker):
```bash
# Push item
grpcurl -plaintext -d '{"queue_id":"test","item_json":"{\"msg\":\"hello\"}","priority":1}' \
  localhost:5001 daprmq.DaprMQ/Push

# Pop with acknowledgement
grpcurl -plaintext -d '{"queue_id":"test","ttl_seconds":30}' \
  localhost:5001 daprmq.DaprMQ/PopWithAck
```

**C# Client Example**:
```csharp
using Grpc.Net.Client;
using DaprMQ.ApiServer.Grpc;

var channel = GrpcChannel.ForAddress("http://localhost:5001");
var client = new DaprMQ.DaprMQClient(channel);

var response = await client.PopWithAckAsync(new PopWithAckRequest
    { QueueId = "my-queue", TtlSeconds = 30 });

if (response.ResultCase == PopWithAckResponse.ResultOneofCase.Success) {
    // Process item, then acknowledge
    await client.AcknowledgeAsync(new AcknowledgeRequest
        { QueueId = "my-queue", LockId = response.Success.LockId });
}
```

**gRPC Reflection (Service Discovery)**:

Server Reflection enabled - discover services at runtime without `.proto` file.

```bash
# Discover available services (see port table above)
grpcurl -plaintext localhost:5001 list
grpcurl -plaintext localhost:5001 describe daprmq.DaprMQ
grpcurl -plaintext localhost:5001 describe daprmq.DaprMQ.Push
```

**Proto File Access**:

While reflection is available, clients can also access the proto definition directly:
- **Source**: [dotnet/src/DaprMQ.ApiServer/Protos/daprmq.proto](dotnet/src/DaprMQ.ApiServer/Protos/daprmq.proto)
- **Package: daprmq`
- **C# Namespace**: `DaprMQ.ApiServer.Grpc`

For client generation in other languages:
```bash
# Generate Python client
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. daprmq.proto

# Generate Go client
protoc --go_out=. --go-grpc_out=. daprmq.proto

# Generate Java client
protoc --java_out=. --grpc-java_out=. daprmq.proto
```

**HTTP/2 Configuration**:

The server uses **separate ports** for HTTP/1.1 (REST) and HTTP/2 (gRPC) to avoid TLS negotiation requirements:

```csharp
// In Program.cs
builder.WebHost.UseKestrel(options =>
{
    // HTTP/1.1 endpoint for REST APIs
    options.ListenAnyIP(httpPort, listenOptions =>
    {
        listenOptions.Protocols = HttpProtocols.Http1;
    });

    // HTTP/2 endpoint for gRPC (no TLS required when HTTP/2 only)
    options.ListenAnyIP(grpcPort, listenOptions =>
    {
        listenOptions.Protocols = HttpProtocols.Http2;
    });
});
```

This dual-port configuration is **required** because Kestrel cannot negotiate HTTP/2 without TLS when supporting both protocols on the same port (see port table above).

**ARM64 (Apple Silicon) Support**:

To support native ARM64 Docker builds without emulation, the project uses **grpc-tools 2.68.1** instead of the newer 2.70.x versions:

- ✅ Native ARM64 Docker builds (no x86_64 emulation needed)
- ✅ Better performance on Apple Silicon
- ✅ Avoids grpc-tools 2.70.0 protoc crash (exit code 139 on linux_arm64)

The proto files are automatically generated during build from [daprmq.proto](dotnet/src/DaprMQ.ApiServer/Protos/daprmq.proto).

## Development Conventions

- **Language:** C# 13 (.NET 10.0), nullable reference types enabled, async Tasks
- **Testing:** xUnit + Moq, >95% coverage target, `*Tests.cs` naming
- **Imports:** External first (Dapr.*), then internal (DaprMQ.*)

## Important Notes

1. **Package Naming**:
   - NuGet package: `DaprMQ`
   - C# namespaces: `DaprMQ`, `DaprMQ.Interfaces`
   - GitHub repo: `dapr-mq`

2. **Actor Registration**: Must register `DaprMQ` before creating proxies

3. **Item Format**: Push accepts JSON strings (ItemJson property)

4. **Priority System**: Default priority is 1. Priority 0 is reserved as a "fast lane" for urgent items that need to interrupt normal processing. Lower priority numbers are processed first (0 before 1 before 2, etc.).

5. **FIFO Guarantee**: Items always returned in insertion order within priority

6. **Concurrency**: One operation per actor instance at a time

7. **Direct Actor API Access**: Interact with actors via Dapr's HTTP API (port 3500) for testing/debugging:
   ```bash
   # Invoke actor method
   curl -X POST http://localhost:3500/v1.0/actors/DaprMQ/my-queue/method/Push \
     -H "Content-Type: application/json" -d '{"item": {"test": "data"}}'
   ```
   Actor type: `DaprMQ`, State key: `queue`. See https://docs.dapr.io/reference/api/actors_api/

8. **Nonremoting Actor Invocations**: API server uses `InvokeMethodAsync` for better decoupling and cross-language support:
   ```csharp
   // Nonremoting (API server)
   var proxy = ActorProxy.Create(actorId, "QueueActor");
   var result = await proxy.InvokeMethodAsync<PushRequest, PushResponse>("Push", request);

   // Remoting (library users)
   var proxy = ActorProxy.Create<IQueueActor>(actorId, "QueueActor");
   var result = await proxy.Push(request);
   ```

## Future Considerations

- Max queue size limits (currently unbounded)
- Batch push operations (currently one-at-a-time)
- Queue metrics/monitoring endpoints
- Alternative state store examples (Redis, CosmosDB)

## Quick Reference Links

- Dapr Docs: https://docs.dapr.io/
- Dapr .NET SDK: https://github.com/dapr/dotnet-sdk
- Project Issues: https://github.com/olitomlinson/dapr-mq/issues
