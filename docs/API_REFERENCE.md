# API Reference

Complete reference for PushPopActor methods and REST API endpoints.

## Actor Interface

### IPushPopActor

Actor interface definition for creating typed proxies.

```csharp
using PushPopActor.Interfaces;
```

## Actor Methods

### Push

Push a JSON item onto the queue (FIFO - added to end).

```csharp
Task<PushResponse> Push(PushRequest request)
```

**Parameters:**
- `request` (PushRequest): Contains:
  - `ItemJson` (string): JSON string to push onto the queue
  - `Priority` (int): Priority level (default: 0, must be >= 0)

**Returns:**
- `PushResponse`: Contains:
  - `Success` (bool): `true` if push was successful, `false` if failed

**Behavior:**
- Appends item to the end of the queue (FIFO)
- Persists queue state to Dapr state store
- Returns immediately after state is saved
- Thread-safe (actor processes one request at a time)

**Example:**

```csharp
using Dapr.Actors;
using Dapr.Actors.Client;
using PushPopActor.Interfaces;
using System.Text.Json;

var proxy = ActorProxy.Create<IPushPopActor>(
    new ActorId("my-queue"),
    "PushPopActor"
);

// Simple item
var response = await proxy.Push(new PushRequest
{
    ItemJson = "{\"task\": \"send_email\"}",
    Priority = 0
});
Console.WriteLine(response.Success);  // True

// Complex nested item
var item = new
{
    task_id = 123,
    action = "process_upload",
    metadata = new
    {
        user_id = 456,
        file = "document.pdf",
        tags = new[] { "urgent", "important" }
    }
};
response = await proxy.Push(new PushRequest
{
    ItemJson = JsonSerializer.Serialize(item),
    Priority = 0
});
Console.WriteLine(response.Success);  // True

// Invalid item (empty)
response = await proxy.Push(new PushRequest
{
    ItemJson = "",
    Priority = 0
});
Console.WriteLine(response.Success);  // False
```

**Error Handling:**

```csharp
try
{
    var response = await proxy.Push(new PushRequest
    {
        ItemJson = itemJson,
        Priority = 0
    });
    if (!response.Success)
    {
        Console.WriteLine("Push failed - check item is valid JSON");
    }
}
catch (Exception ex)
{
    Console.WriteLine($"Actor invocation error: {ex.Message}");
}
```

---

### Pop

Pop a single item from the queue (FIFO - removed from front).

```csharp
Task<PopResponse> Pop()
```

**Parameters:**
- None

**Returns:**
- `PopResponse`: Contains:
  - `ItemsJson` (List<string>): List with single JSON string, or empty list if queue is empty

**Behavior:**
- Removes and returns a single item from the front of the queue
- Returns empty array if queue is empty
- Persists updated queue state to Dapr state store
- Items are returned in FIFO order (oldest first)

**Example:**

```csharp
// Pop single item
var result = await proxy.Pop();
if (result.ItemsJson.Any())
{
    Console.WriteLine(result.ItemsJson[0]);  // {"task": "send_email"}
}
else
{
    Console.WriteLine("Queue is empty");
}

// Pop from empty queue
result = await proxy.Pop();
Console.WriteLine(result.ItemsJson.Count);  // 0
```

**Processing Pattern:**

```csharp
// Consumer loop - pop one item at a time
while (true)
{
    var result = await proxy.Pop();

    if (!result.ItemsJson.Any())
    {
        await Task.Delay(1000);  // Wait for more items
        continue;
    }

    await ProcessItemAsync(result.ItemsJson[0]);
}

// Consumer loop - pop multiple items
var allItems = new List<string>();
for (int i = 0; i < 10; i++)  // Pop up to 10 items
{
    var result = await proxy.Pop();
    if (!result.ItemsJson.Any())
        break;
    allItems.AddRange(result.ItemsJson);
}

foreach (var item in allItems)
{
    await ProcessItemAsync(item);
}
```

### PopWithAck

Pop a single item from the queue with acknowledgement requirement (FIFO with lock).

```csharp
Task<PopWithAckResponse> PopWithAck(PopWithAckRequest request)
```

**Parameters:**
- `request` (PopWithAckRequest): Contains:
  - `TtlSeconds` (int, optional): Lock TTL in seconds (default: 30, range: 1-300)

**Returns:**
- `PopWithAckResponse`: Contains:
  - `ItemsJson` (List<string>): List of popped JSON strings
  - `Count` (int): Number of items returned
  - `Locked` (bool): `true` if lock was created, `false` if queue empty or already locked
  - `LockId` (string, optional): Lock ID to use for acknowledgement (present if `Locked=true`)
  - `LockExpiresAt` (double, optional): Unix timestamp when lock expires (present if `Locked=true`)
  - `Message` (string, optional): Status message

**Behavior:**
- Checks for existing active lock before popping
- If lock exists and not expired: returns 423 status (locked)
- If lock expired: returns items to their original priority queues, removes lock, continues
- Pops items from priority queues in order (0, 1, 2, ...) while tracking priority metadata
- Creates lock with generated ID and stores items with priority information
- Returns items to client (priority metadata hidden from caller)
- Lock prevents concurrent pops until acknowledged or expired
- Expired locks automatically return items to original priority queues

**Example:**

```csharp
// Pop with acknowledgement
var result = await proxy.PopWithAck(new PopWithAckRequest { TtlSeconds = 60 });

if (result.Locked && result.Count > 0)
{
    // Got items with lock
    var items = result.ItemsJson;
    var lockId = result.LockId;

    try
    {
        // Process items
        foreach (var item in items)
        {
            await ProcessItemAsync(item);
        }

        // Acknowledge successful processing
        var ackResult = await proxy.Acknowledge(new AcknowledgeRequest { LockId = lockId });
        Console.WriteLine(ackResult.Success);  // True
    }
    catch (Exception ex)
    {
        // Don't acknowledge - lock will expire and items return to queue
        Console.WriteLine($"Processing failed: {ex.Message}");
    }
}
else if (result.Locked && result.Count == 0)
{
    // Queue is locked by another operation
    Console.WriteLine($"Queue locked until {result.LockExpiresAt}");
}
else
{
    // Queue is empty
    Console.WriteLine("No items available");
}
```

**Edge Cases:**

```csharp
// Pop while another lock is active
var result1 = await proxy.PopWithAck(new PopWithAckRequest());  // Success
var result2 = await proxy.PopWithAck(new PopWithAckRequest());  // Locked
Console.WriteLine(result2.Locked);  // True
Console.WriteLine(result2.Count);   // 0
Console.WriteLine(result2.Message); // "Queue is locked by another operation"

// Custom TTL
var result = await proxy.PopWithAck(new PopWithAckRequest { TtlSeconds = 120 });  // 2 minute lock

// TTL bounds are enforced (1-300 seconds)
result = await proxy.PopWithAck(new PopWithAckRequest { TtlSeconds = 500 });  // Clamped to 300
```

### Acknowledge

Acknowledge popped items using lock ID.

```csharp
Task<AcknowledgeResponse> Acknowledge(AcknowledgeRequest request)
```

**Parameters:**
- `request` (AcknowledgeRequest): Contains:
  - `LockId` (string): The lock ID returned by `PopWithAck`

**Returns:**
- `AcknowledgeResponse`: Contains:
  - `Success` (bool): `true` if acknowledged, `false` if failed
  - `Message` (string): Status message
  - `ItemsAcknowledged` (int, optional): Number of items acknowledged (present if `Success=true`)
  - `ErrorCode` (string, optional): Error code (e.g., "LOCK_EXPIRED")

**Behavior:**
- Validates lock ID against active lock
- If valid: removes lock and returns success
- If lock expired: removes expired lock and returns "LOCK_EXPIRED" error
- If lock not found: returns "not found" error
- If lock ID doesn't match: returns "invalid" error
- Items are already removed from queue during `PopWithAck`

**Example:**

```csharp
// Successful acknowledgement
var result = await proxy.PopWithAck(new PopWithAckRequest());
var lockId = result.LockId;

// Process items...

var ackResult = await proxy.Acknowledge(new AcknowledgeRequest { LockId = lockId });
Console.WriteLine(JsonSerializer.Serialize(ackResult));
// {
//     "Success": true,
//     "Message": "Successfully acknowledged 5 item(s)",
//     "ItemsAcknowledged": 5
// }

// Expired lock
await Task.Delay(35000);  // Wait past 30 second default TTL
ackResult = await proxy.Acknowledge(new AcknowledgeRequest { LockId = lockId });
Console.WriteLine(JsonSerializer.Serialize(ackResult));
// {
//     "Success": false,
//     "Message": "Lock has expired",
//     "ErrorCode": "LOCK_EXPIRED"
// }

// Invalid lock ID
ackResult = await proxy.Acknowledge(new AcknowledgeRequest { LockId = "wrong_id" });
Console.WriteLine(JsonSerializer.Serialize(ackResult));
// {
//     "Success": false,
//     "Message": "Invalid lock_id"
// }
```

**Processing Pattern with Acknowledgement:**

```csharp
// Consumer loop with acknowledgement
while (true)
{
    var result = await proxy.PopWithAck(new PopWithAckRequest { TtlSeconds = 60 });

    if (!result.Locked || result.Count == 0)
    {
        await Task.Delay(1000);
        continue;
    }

    var lockId = result.LockId;
    var items = result.ItemsJson;

    try
    {
        // Process all items
        foreach (var item in items)
        {
            await ProcessItemAsync(item);
        }

        // Acknowledge successful processing
        await proxy.Acknowledge(new AcknowledgeRequest { LockId = lockId });
    }
    catch (Exception ex)
    {
        _logger.LogError(ex, "Processing failed");
        // Don't acknowledge - items will return to queue after TTL
    }
}
```

---

## REST API Endpoints

When using the example API server, these HTTP endpoints are available.

### Base URL

Default: `http://localhost:8000`

### POST /queue/{queueId}/push

Push an item to the specified queue.

**Path Parameters:**
- `queueId` (string): Unique identifier for the queue

**Request Body:**
```json
{
  "item": {
    "key1": "value1",
    "key2": "value2"
  }
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Item pushed to queue {queueId}"
}
```

**Response (400 Bad Request):**
```json
{
  "detail": "Failed to push item"
}
```

**Response (500 Internal Server Error):**
```json
{
  "detail": "Internal error: ..."
}
```

**Example:**

```bash
curl -X POST http://localhost:8000/queue/my-queue/push \
  -H "Content-Type: application/json" \
  -d '{
    "item": {
      "task_id": 123,
      "action": "send_email",
      "recipient": "user@example.com"
    }
  }'
```

---

### POST /queue/{queueId}/pop

Pop a single item from the specified queue, with optional acknowledgement.

**Path Parameters:**
- `queueId` (string): Unique identifier for the queue

**Query Parameters:**
- `require_ack` (boolean, optional): Require acknowledgement for popped items. Default: false.
- `ttl_seconds` (integer, optional): Lock TTL in seconds if `require_ack=true`. Default: 30. Range: 1-300.

**Request Body:**
None

**Response (200 OK - without acknowledgement):**
```json
{
  "item": {"task_id": 123, "action": "send_email"}
}
```

**Response (200 OK - with acknowledgement):**
```json
{
  "items": [
    {"task_id": 123, "action": "send_email"}
  ],
  "count": 1,
  "locked": true,
  "lock_id": "abc123def456",
  "lock_expires_at": 1709139275.0
}
```

**Response (423 Locked - queue already locked):**
```json
{
  "message": "Queue is locked pending acknowledgement",
  "lock_expires_at": 1709139245.0
}
```

**Response (500 Internal Server Error):**
```json
{
  "detail": "Internal error: ..."
}
```

**Examples:**

```bash
# Pop single item (no acknowledgement)
curl -X POST "http://localhost:8000/queue/my-queue/pop"
# Response: {"item": {"task_id": 123, "action": "send_email"}}

# Pop with acknowledgement
curl -X POST "http://localhost:8000/queue/my-queue/pop?require_ack=true"
# Response: {"items": [...], "lock_id": "abc123", "locked": true, ...}

# Pop with custom TTL (2 minutes)
curl -X POST "http://localhost:8000/queue/my-queue/pop?require_ack=true&ttl_seconds=120"

# Pop from empty queue (returns null)
curl -X POST "http://localhost:8000/queue/empty-queue/pop"
# Response: {"item": null}
```

---

### POST /queue/{queueId}/acknowledge

Acknowledge popped items using lock ID.

**Path Parameters:**
- `queueId` (string): Unique identifier for the queue

**Request Body:**
```json
{
  "lock_id": "abc123def456"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "Items acknowledged successfully",
  "items_acknowledged": 5
}
```

**Response (400 Bad Request - missing or invalid lock_id):**
```json
{
  "success": false,
  "message": "lock_id is required"
}
```

**Response (404 Not Found - lock not found):**
```json
{
  "success": false,
  "message": "No active lock found"
}
```

**Response (410 Gone - lock expired):**
```json
{
  "success": false,
  "message": "Lock has expired",
  "error_code": "LOCK_EXPIRED"
}
```

**Response (500 Internal Server Error):**
```json
{
  "detail": "Internal error: ..."
}
```

**Examples:**

```bash
# Successful acknowledgement
curl -X POST "http://localhost:8000/queue/my-queue/acknowledge" \
  -H "Content-Type: application/json" \
  -d '{"lock_id": "abc123def456"}'

# Invalid lock ID
curl -X POST "http://localhost:8000/queue/my-queue/acknowledge" \
  -H "Content-Type: application/json" \
  -d '{"lock_id": "wrong_id"}'
# Response (400): {"success": false, "message": "Invalid lock_id"}

# Expired lock
curl -X POST "http://localhost:8000/queue/my-queue/acknowledge" \
  -H "Content-Type: application/json" \
  -d '{"lock_id": "expired123"}'
# Response (410): {"success": false, "error_code": "LOCK_EXPIRED"}
```

**Complete Workflow:**

```bash
# 1. Pop with acknowledgement
RESPONSE=$(curl -s -X POST "http://localhost:8000/queue/my-queue/pop?require_ack=true")
LOCK_ID=$(echo $RESPONSE | jq -r '.lock_id')
ITEMS=$(echo $RESPONSE | jq -r '.items')

# 2. Process items (your application logic here)
echo "Processing $ITEMS..."

# 3. Acknowledge successful processing
curl -X POST "http://localhost:8000/queue/my-queue/acknowledge" \
  -H "Content-Type: application/json" \
  -d "{\"lock_id\": \"$LOCK_ID\"}"
```

---

### GET /health

Health check endpoint.

**Request Body:**
None

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "dapr-push-pop-actor-api"
}
```

**Example:**

```bash
curl http://localhost:8000/health
```

---

## Data Types

### Item (JSON String)

Items pushed to the queue must be valid JSON strings.

**Valid Items:**

```csharp
// Simple flat object
var item1 = "{\"id\": 1, \"name\": \"Alice\"}";

// Or use JsonSerializer
var item2 = JsonSerializer.Serialize(new { id = 1, name = "Alice" });

// Nested structures
var item3 = JsonSerializer.Serialize(new
{
    user = new { id = 123, email = "alice@example.com" },
    metadata = new { tags = new[] { "urgent" }, priority = 5 }
});

// Arrays
var item4 = JsonSerializer.Serialize(new { items = new[] { 1, 2, 3 }, total = 3 });

// Mixed types
var item5 = JsonSerializer.Serialize(new
{
    str = "value",
    number = 123,
    floating = 45.67,
    boolean = true,
    nullValue = (string?)null,
    array = new[] { 1, 2, 3 },
    nested = new { key = "value" }
});
```

**Invalid Items:**

```csharp
// Empty or null
var invalid1 = "";
var invalid2 = null;

// Non-JSON string
var invalid3 = "not valid json";
```

**Best Practice:**

Use JsonSerializer for complex objects:

```csharp
using System.Text.Json;

var item = new
{
    created_at = DateTime.UtcNow,
    data = "payload"
};

await proxy.Push(new PushRequest
{
    ItemJson = JsonSerializer.Serialize(item),
    Priority = 0
});
```

---

## Error Handling

### Actor Method Errors

```csharp
using Dapr.Actors;
using Dapr.Actors.Client;
using PushPopActor.Interfaces;

try
{
    var proxy = ActorProxy.Create<IPushPopActor>(
        new ActorId("my-queue"),
        "PushPopActor"
    );

    var pushResponse = await proxy.Push(new PushRequest
    {
        ItemJson = "{\"data\": \"value\"}",
        Priority = 0
    });
    if (!pushResponse.Success)
    {
        // Handle push failure (e.g., invalid item)
    }

    var popResponse = await proxy.Pop();
    // ItemsJson is always a list (empty if no items)
}
catch (Exception ex)
{
    // Handle actor invocation errors
    // - Dapr sidecar not running
    // - Network issues
    // - Actor not registered
    Console.WriteLine($"Error: {ex.Message}");
}
```

### REST API Errors

```bash
# 400 Bad Request - Invalid request body
curl -X POST http://localhost:8000/queue/my-queue/push \
  -H "Content-Type: application/json" \
  -d '{"invalid": "missing item key"}'

# 500 Internal Server Error - Actor invocation failed
# (e.g., Dapr sidecar down, state store unavailable)
```

---

## Rate Limits

The example API server has no built-in rate limiting. For production:

1. **Add rate limiting middleware:**
   ```csharp
   using AspNetCoreRateLimit;

   // In Program.cs
   builder.Services.AddMemoryCache();
   builder.Services.Configure<IpRateLimitOptions>(options =>
   {
       options.GeneralRules = new List<RateLimitRule>
       {
           new RateLimitRule
           {
               Endpoint = "POST:/queue/*/push",
               Limit = 100,
               Period = "1m"
           }
       };
   });
   ```

2. **Use API Gateway:** Deploy behind nginx, AWS API Gateway, etc.

3. **Actor-level throttling:** Implement custom throttling in actor logic

---

## Performance Considerations

### Push Performance

- **Time Complexity**: O(1) amortized
- **Network Calls**: 2 state store operations (segment + metadata)
- **Memory** (v4.0+): Max 100 items loaded per push (segmented storage)
- **Recommendation**: Batch pushes when possible to reduce roundtrips

### Pop Performance

- **Time Complexity**: O(k) where k = number of priority levels with items
- **Network Calls**: 2 state store operations (segment + metadata)
- **Memory** (v4.0+): Max 100 items loaded per pop (vs entire queue in v3.x)
- **Scalability**: Constant-time operations regardless of queue size (thanks to segmentation)
- **Recommendation**: Call Pop in loops for bulk processing, or use PopWithAck for reliable batch processing

### Segmented Storage Benefits (v4.0+)

PushPopActor v4.0+ uses segmented storage, splitting large queues into 100-item chunks:

- **Memory**: 10,000 item queue uses ~10-50KB per operation (was 1-5MB in v3.x)
- **Network**: Serialize max 100 items per save (vs entire queue)
- **Performance**: O(1) operations regardless of queue size

See [features/segmented-queue.md](../features/segmented-queue.md) for technical details.

### State Store Impact

```csharp
// ❌ Inefficient - Many roundtrips
for (int i = 0; i < 100; i++)
{
    await proxy.Push(new PushRequest
    {
        ItemJson = JsonSerializer.Serialize(new { id = i }),
        Priority = 0
    });
}

// ✅ Better - Single actor, single queue, processed serially
var items = Enumerable.Range(0, 100).Select(i => new { id = i });
foreach (var item in items)
{
    await proxy.Push(new PushRequest
    {
        ItemJson = JsonSerializer.Serialize(item),
        Priority = 0
    });
}

// ✅ Best - Use multiple actors for parallelism
var actors = Enumerable.Range(0, 10)
    .Select(i => ActorProxy.Create<IPushPopActor>(new ActorId($"queue-{i}"), "PushPopActor"))
    .ToList();
for (int i = 0; i < items.Count(); i++)
{
    await actors[i % 10].Push(new PushRequest
    {
        ItemJson = JsonSerializer.Serialize(items.ElementAt(i)),
        Priority = 0
    });
}
```

---

## Limitations

- **Max Item Size**: Limited by state store (PostgreSQL: ~1GB, but practically keep < 1MB)
- **Max Queue Size**: No hard limit - segmented storage (v4.0+) supports queues of any size
- **Max Segment Size**: 100 items per segment (configurable in metadata)
- **Max Depth**: API server limits to 100 items per pop (configurable)
- **Concurrency**: One operation per actor at a time (per actor ID)
- **Breaking Change**: v4.0+ uses segmented storage, incompatible with v3.x state format

---

## See Also

- [QUICKSTART.md](QUICKSTART.md) - Getting started guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - How it works under the hood
- [README.md](../README.md) - Project overview
- [Examples](../examples/) - Code examples
