# Bulk Pop Feature Roadmap

## Context

Modify existing Pop methods to return arrays, enabling retrieval of multiple messages in a single atomic operation. This addresses the current limitation where messages must be popped one at a time.

**Why**: Reduces round-trip overhead for high-throughput consumers, improves performance when processing batches of messages.

**Approach**: Extend existing `Pop()` and `PopWithAck()` methods to accept optional `count` parameter and return arrays instead of single items. This is a **breaking change** but simplifies the API (no new methods needed).

**Current State**: `Pop()` and `PopWithAck()` return single items. Push already supports batch operations as a reference pattern.

## Implementation Phases

Each phase is designed to fit within a single context window and can be completed independently.

---

### Phase 1: Core Actor - Modify Pop to Return Arrays

**Scope**: Change `Pop()` method to accept `count` parameter and return array of items.

**Files**:
- [dotnet/src/DaprMQ.Interfaces/Models.cs](dotnet/src/DaprMQ.Interfaces/Models.cs) - Modify `PopRequest` and `PopResponse`
- [dotnet/src/DaprMQ/QueueActor.cs](dotnet/src/DaprMQ/QueueActor.cs) - Modify `Pop()` implementation

**Breaking Changes**:
- `PopRequest`: Add optional `Count` property (default 1, max 100)
- `PopResponse`: Change from single item fields to `List<PopItem>` array
  - New: `List<PopItem> Items { get; init; }`
  - Remove: `ItemJson`, `Priority` (now inside PopItem)
  - Keep: `Locked`, `IsEmpty`, `Message`, `LockExpiresAt` (for error cases)
- New record: `PopItem { ItemJson, Priority }`

**Implementation Details**:
- Loop up to `Count` times calling `PopWithPriorityAsync()` internally
- Stop early if queue empty or locked (legacy mode)
- Return all successfully popped items in `Items` array
- Single `SaveStateAsync()` at end for atomic commit
- Empty queue: return `IsEmpty=true` with empty `Items` list
- Locked queue: return `Locked=true` with partial `Items` (what was popped before lock detected)

**Patterns to Follow**:
- Batch pattern from `Push()` (lines 249-291 in QueueActor.cs)
- Pop logic from `PopWithPriorityAsync()` (lines 340-500)

**Testing** (TDD - Write Tests First):
- Add to [dotnet/tests/DaprMQ.Tests/QueueActorTests.cs](dotnet/tests/DaprMQ.Tests/QueueActorTests.cs):
  - `Pop_WithCount_ReturnsMultipleItems()` - Pop 5 items, verify all returned
  - `Pop_WithCountGreaterThanAvailable_ReturnsPartialResults()` - Request 10, only 3 exist
  - `Pop_WithCountZero_ReturnsEmptyArray()` - Edge case validation
  - `Pop_WithCountExceedingMax_ValidationError()` - Count > 100 validation
  - `Pop_CrossPriority_ReturnsInPriorityOrder()` - Items across priorities 0, 1, 2
- Run after implementation: `dotnet test tests/DaprMQ.Tests/DaprMQ.Tests.csproj`

**Complexity**: ~100 lines code + ~100 lines tests, 3 files

---

### Phase 2: Core Actor - Modify PopWithAck to Return Arrays

**Scope**: Change `PopWithAck()` method to accept `count` parameter and return array of locked items.

**Files**:
- [dotnet/src/DaprMQ.Interfaces/Models.cs](dotnet/src/DaprMQ.Interfaces/Models.cs) - Modify `PopWithAckRequest` and `PopWithAckResponse`
- [dotnet/src/DaprMQ/QueueActor.cs](dotnet/src/DaprMQ/QueueActor.cs) - Modify `PopWithAck()` implementation

**Breaking Changes**:
- `PopWithAckRequest`: Add optional `Count` property (default 1, max 100)
- `PopWithAckResponse`: Change from single item fields to `List<PopWithAckItem>` array
  - New: `List<PopWithAckItem> Items { get; init; }`
  - Remove: `ItemJson`, `Priority`, `LockId`, `LockExpiresAt` (now inside PopWithAckItem)
  - Keep: `Locked`, `IsEmpty`, `Message` (for error cases)
- New record: `PopWithAckItem { ItemJson, Priority, LockId, LockExpiresAt }`

**Implementation Details**:
- Loop up to `Count` times:
  - Call `PopWithPriorityAsync(skipLockCheck: true)` if competing consumers enabled
  - Generate unique lock ID per item via `GenerateLockId()`
  - Create `LockState` record with item data, TTL
  - Store at `{lockId}-lock` state key
  - Add to `_lock_registry` list
  - Register Dapr reminder for auto-expiry
- Single `SaveStateAsync()` commits all items + all locks atomically
- Legacy mode: if `AllowCompetingConsumers=false` and locks exist, return `Locked=true`
- Return partial results on queue exhaustion in `Items` array

**Patterns to Follow**:
- Lock creation from `PopWithAck()` (lines 603-748)
- Existing `LockState` structure and reminder system

**Testing** (TDD - Write Tests First):
- Add to [dotnet/tests/DaprMQ.Tests/QueueActorTests.cs](dotnet/tests/DaprMQ.Tests/QueueActorTests.cs):
  - `PopWithAck_WithCount_CreatesMultipleLocks()` - Verify each item has unique lock ID
  - `PopWithAck_WithCount_RegistersMultipleReminders()` - Verify reminder per lock
  - `PopWithAck_WithCountPartial_ReturnsAvailableItems()` - Request 10, only 5 available
  - `PopWithAck_LegacyMode_BlocksWithExistingLocks()` - Legacy mode behavior unchanged
  - `PopWithAck_CompetingConsumerMode_AllowsMultipleLocks()` - Parallel locks work
- Run after implementation: `dotnet test tests/DaprMQ.Tests/DaprMQ.Tests.csproj`

**Complexity**: ~150 lines code + ~120 lines tests, 3 files

---

### Phase 3: HTTP REST API

**Scope**: Modify existing `/pop` endpoint to support count parameter and array responses.

**Files**:
- [dotnet/src/DaprMQ.ApiServer/Models/ApiModels.cs](dotnet/src/DaprMQ.ApiServer/Models/ApiModels.cs) - Modify `ApiPopResponse` to return arrays
- [dotnet/src/DaprMQ.ApiServer/Controllers/QueueController.cs](dotnet/src/DaprMQ.ApiServer/Controllers/QueueController.cs) - Modify `POST /queue/{queueId}/pop` endpoint

**Breaking Changes**:
- `ApiPopResponse`: Change from single item to array
  - New: `List<object> Items` (array of JSON objects)
  - New: `List<int> Priorities` (parallel array, optional)
  - Remove: `Item` (single object)
  - Remove: `Priority` (single int)
- Response for PopWithAck mode:
  - New: `List<string> LockIds` (parallel array)
  - New: `List<double> LockExpiresAt` (parallel array)
  - Remove: `lock_id`, `lock_expires_at` headers

**Implementation Details**:
- Add query param: `count` (default 1, max 100)
- Existing headers unchanged:
  - `require_ack` (bool, default false)
  - `ttl_seconds` (int, default 30)
  - `allow_competing_consumers` (bool, default false)
- Parse actor's `PopResponse.Items` array and map to API response
- HTTP status codes unchanged:
  - 200 OK: Items returned (array, can be empty)
  - 204 No Content: Queue empty (IsEmpty=true, Items empty)
  - 400 Bad Request: Invalid count parameter
  - 423 Locked: Queue locked (legacy mode, may include partial items)
  - 500 Internal Server Error: Actor exceptions

**Patterns to Follow**:
- Existing `Pop` endpoint structure (lines 95-178 in QueueController.cs)
- Array mapping similar to Push response

**Testing** (TDD - Write Tests First):
- Add to [dotnet/tests/DaprMQ.Tests/QueueControllerTests.cs](dotnet/tests/DaprMQ.Tests/QueueControllerTests.cs):
  - `Pop_WithCount_Returns200WithItemsArray()` - Mock actor response with multiple items
  - `Pop_WithInvalidCount_Returns400()` - Count < 1 or > 100
  - `Pop_WithCountReturnsEmpty_Returns204()` - Empty items array → 204 No Content
  - `Pop_WithCountReturnsLocked_Returns423()` - Locked response → 423 Locked
  - `PopWithAck_WithCount_ReturnsArrayWithLockIds()` - Verify lock IDs in parallel arrays
- Run after implementation: `dotnet test tests/DaprMQ.Tests/QueueControllerTests.csproj`

**Complexity**: ~80 lines code + ~100 lines tests, 3 files

---

### Phase 4: gRPC API

**Scope**: Modify existing Pop/PopWithAck gRPC methods to support count parameter and return arrays.

**Files**:
- [dotnet/src/DaprMQ.ApiServer/Protos/daprmq.proto](dotnet/src/DaprMQ.ApiServer/Protos/daprmq.proto) - Modify proto definitions
- [dotnet/src/DaprMQ.ApiServer/Services/DaprMQGrpcService.cs](dotnet/src/DaprMQ.ApiServer/Services/DaprMQGrpcService.cs) - Modify service implementations

**Breaking Changes**:
- Modify `PopRequest`:
  ```protobuf
  message PopRequest {
    string queue_id = 1;
    int32 count = 2;  // NEW: optional, default 1
  }
  ```
- Modify `PopSuccess`:
  ```protobuf
  message PopSuccess {
    repeated string item_json = 1;  // CHANGED: single → repeated
    repeated int32 priority = 2;    // CHANGED: single → repeated (parallel array)
  }
  ```
- Modify `PopWithAckRequest`:
  ```protobuf
  message PopWithAckRequest {
    string queue_id = 1;
    int32 ttl_seconds = 2;
    bool allow_competing_consumers = 3;
    int32 count = 4;  // NEW: optional, default 1
  }
  ```
- Modify `PopWithAckSuccess`:
  ```protobuf
  message PopWithAckSuccess {
    repeated string item_json = 1;        // CHANGED: single → repeated
    repeated int32 priority = 2;          // CHANGED: single → repeated
    repeated string lock_id = 3;          // CHANGED: single → repeated
    repeated double lock_expires_at = 4;  // CHANGED: single → repeated
  }
  ```
- No changes to `PopResponse`/`PopWithAckResponse` oneof structure

**Implementation Details**:
- Service methods map actor's `Items` array to repeated protobuf fields
- Handle empty arrays (success with zero items vs IsEmpty flag)
- gRPC status codes unchanged:
  - OK(0): Items returned (array)
  - INVALID_ARGUMENT(3): Invalid count
  - UNAVAILABLE(14): Queue locked
  - INTERNAL(13): Actor errors

**Patterns to Follow**:
- Existing `Pop` gRPC implementation (lines 93-140 in DaprMQGrpcService.cs)
- Array mapping in repeated fields

**Testing** (TDD - Write Tests First):
- Add to [dotnet/tests/DaprMQ.Tests/DaprMQGrpcServiceTests.cs](dotnet/tests/DaprMQ.Tests/DaprMQGrpcServiceTests.cs):
  - `Pop_WithCount_ReturnsRepeatedFields()` - Mock actor, verify repeated item_json/priority
  - `Pop_WithInvalidCount_ThrowsInvalidArgument()` - RpcException with INVALID_ARGUMENT
  - `Pop_WithCountReturnsEmpty_ReturnsEmptySuccess()` - Empty array in success variant
  - `PopWithAck_WithCount_ReturnsRepeatedLockFields()` - Verify repeated lock_id/expires_at
- Run after implementation: `dotnet test tests/DaprMQ.Tests/DaprMQGrpcServiceTests.csproj`

**Complexity**: ~100 lines code + ~80 lines tests, 3 files

---

### Phase 5: Dashboard Integration

**Scope**: Update dashboard to support count parameter and handle array responses from existing Pop API.

**Files**:
- [dashboard/src/services/queueApi.ts](dashboard/src/services/queueApi.ts) - Modify `pop()` and `popWithAck()` to accept count param
- [dashboard/src/types/queue.ts](dashboard/src/types/queue.ts) - Update TypeScript interfaces for array responses
- [dashboard/src/hooks/useQueueOperations.ts](dashboard/src/hooks/useQueueOperations.ts) - Handle array responses
- [dashboard/src/components/PopSection.tsx](dashboard/src/components/PopSection.tsx) - Add count selector UI

**Breaking Changes**:
- `PopResponse` interface: Change `item` (single) → `items` (array)
- `PopWithAckResponse` interface: Change single fields → arrays (items, lockIds, lockExpiresAt)

**Implementation Details**:
- Modify existing API methods to accept optional `count` parameter:
  - `pop(queueId: string, count?: number): Promise<PopResponse>`
  - `popWithAck(queueId: string, count: number, ttlSeconds: number, allowCompeting: boolean): Promise<PopWithAckResponse>`
- Add state: `popCount` (number, default 1)
- UI controls in PopSection:
  - Number input or dropdown for count: 1, 5, 10, 25, 50, 100
  - Existing "Pop" and "Pop with Ack" buttons use the count value
- Handle array responses:
  - Loop through `items` array and add to messages list
  - For PopWithAck: associate each lockId with corresponding item
- Display multiple items in `MessagesList` (already supports arrays)
- Lock countdown timers work automatically (existing logic handles multiple locks)
- Error handling via existing `ErrorModal` (unchanged)

**Patterns to Follow**:
- Existing `pop()` and `popWithAck()` in queueApi.ts
- Array iteration pattern in useQueueOperations.ts

**Testing** (Manual UI Testing):
- Start API server: `cd dotnet/src/DaprMQ.ApiServer && dapr run ...`
- Start dashboard: `cd dashboard && npm run dev`
- Manual verification:
  - Select count (1, 5, 10, etc.) from dropdown
  - Click "Pop" - verify multiple items appear in list
  - Click "Pop with Ack" - verify multiple items with lock countdown timers
  - Verify empty queue shows appropriate message
  - Verify error modal displays API errors correctly

**Complexity**: ~150 lines, 4 files

---

### Phase 6: Documentation

**Scope**: Update documentation to reflect array-based Pop API (breaking change).

**Files**:
- [CLAUDE.md](CLAUDE.md) - Update Core API section with array responses and count parameter
- [docs/QUICKSTART.md](docs/QUICKSTART.md) - Update examples to show array handling
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md) - Update endpoint documentation
- [README.md](README.md) - Update feature #12 from "Bulk Pop" plan to "Bulk Pop (implemented)"

**Implementation Details**:
- Update CLAUDE.md Core API section:
  - Modify `Pop()` and `PopWithAck()` signatures to show count parameter
  - Update request/response models to show arrays
  - Add examples: single pop (count=1) and bulk pop (count>1)
  - Note breaking changes in response structure
- Update QUICKSTART.md:
  - Update HTTP curl examples to pass `?count=N` query param
  - Update gRPC grpcurl examples with count field
  - Update C# code examples to handle array responses
  - Show iteration pattern for processing multiple items
- Update API_REFERENCE.md:
  - Update endpoint: `POST /queue/{queueId}/pop` (not new endpoint)
  - Document new `count` query parameter
  - Update response schemas to show arrays
  - Note: Breaking change banner
- Update README.md:
  - Change feature #12 status indicator if present
  - Update any Pop-related examples

**Complexity**: ~120 lines, 4 files

---

## Phase Sequencing

**Recommended Order**:
1. Phase 1 (Actor - Pop arrays)
2. Phase 2 (Actor - PopWithAck arrays)
3. Phase 3 (HTTP API)
4. Phase 4 (gRPC API) - Can be parallel with Phase 3
5. Phase 5 (Dashboard) - Depends on Phase 3
6. Phase 6 (Documentation) - Last, after all features complete

**Alternative (Vertical Slices)**:
- Slice 1: Phase 1 → Phase 3 → Phase 5 (Pop arrays end-to-end)
- Slice 2: Phase 2 → extend Phase 3/5 (PopWithAck arrays)
- Slice 3: Phase 4 (gRPC layer)
- Slice 4: Phase 6 (Documentation)

---

## Verification (Per Phase)

**Phase 1**:
- Write tests first (TDD)
- Implement Pop array logic
- Run unit tests: `cd dotnet && dotnet test tests/DaprMQ.Tests/DaprMQ.Tests.csproj --filter "FullyQualifiedName~Pop"`
- All tests must pass before proceeding

**Phase 2**:
- Write tests first (TDD)
- Implement PopWithAck array logic
- Run unit tests: `cd dotnet && dotnet test tests/DaprMQ.Tests/DaprMQ.Tests.csproj --filter "FullyQualifiedName~PopWithAck"`
- All tests must pass before proceeding

**Phase 3**:
- Write controller tests first (TDD)
- Implement HTTP endpoint modifications
- Run unit tests: `cd dotnet && dotnet test tests/DaprMQ.Tests/QueueControllerTests.csproj`
- All tests must pass
- Manual verification with curl:
  ```bash
  # Start API server
  cd dotnet/src/DaprMQ.ApiServer
  dapr run --app-id daprmq-api --app-port 5000 --resources-path ../../../dapr/components -- dotnet run

  # Single pop
  curl -X POST "http://localhost:8002/queue/test/pop?count=1"

  # Bulk pop
  curl -X POST "http://localhost:8002/queue/test/pop?count=5"

  # Bulk with acknowledgement
  curl -X POST "http://localhost:8002/queue/test/pop?count=10" \
    -H "require_ack: true" \
    -H "ttl_seconds: 60" \
    -H "allow_competing_consumers: true"
  ```

**Phase 4**:
- Write gRPC service tests first (TDD)
- Implement proto + service modifications
- Run unit tests: `cd dotnet && dotnet test tests/DaprMQ.Tests/DaprMQGrpcServiceTests.csproj`
- All tests must pass
- Manual verification with grpcurl:
  ```bash
  # Single pop
  grpcurl -plaintext -d '{"queue_id":"test","count":1}' \
    localhost:5001 daprmq.DaprMQ/Pop

  # Bulk pop
  grpcurl -plaintext -d '{"queue_id":"test","count":5}' \
    localhost:5001 daprmq.DaprMQ/Pop
  ```

**Phase 5**:
- Run dashboard: `cd dashboard && npm run dev`
- Manual UI testing: select count, click Pop, verify multiple items appear

**Phase 6**:
- Documentation review only

---

## Integration Tests (After All Phases)

After completing all phases, run full integration tests with Docker + Dapr + PostgreSQL:

```bash
./build-and-test.sh
```

Add integration test cases to [dotnet/tests/DaprMQ.IntegrationTests](dotnet/tests/DaprMQ.IntegrationTests):
- HTTP bulk pop end-to-end (real Dapr actors + state store)
- gRPC bulk pop end-to-end
- Bulk PopWithAck with acknowledgement flow
- Cross-priority bulk pop behavior
- Competing consumers with multiple parallel locks

## Deferred Items

- **Backwards compatibility**: Not a concern (breaking changes acceptable per requirements)
- **Performance benchmarking**: Future work (profile segment loading performance with large counts)
- **Max count limits tuning**: Start with 100, adjust based on production usage patterns

---

## Key Decisions

1. **API Approach**: Modify existing `Pop()` and `PopWithAck()` methods to return arrays (no new methods)
2. **Breaking Change**: Response structure changes from single item to arrays - this is acceptable per requirements
3. **Count Parameter**: Optional `count` parameter (default 1, max 100) enables bulk behavior
4. **Partial Success**: Return all successfully popped items even if fewer than requested count
5. **Cross-Priority**: Pop items across priorities respecting existing priority ordering (0 first)
6. **Lock Management**: Each item gets unique lock ID, independent acknowledgement via existing `Acknowledge()` method
7. **Atomicity**: All items + locks committed in single SaveStateAsync() call
8. **Error Handling**: Empty queue returns empty items array (not error), locked queue stops early with partial items
9. **Count Limits**: 1-100 items per request (validate at both API and actor layers)
10. **Backwards Compatibility**: Not preserved - clients must update to handle array responses
