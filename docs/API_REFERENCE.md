# API Reference

Complete reference for PushPopActor methods and REST API endpoints.

## Actor Interface

### PushPopActorInterface

Actor interface definition for creating typed proxies.

```python
from push_pop_actor import PushPopActorInterface
```

## Actor Methods

### Push

Push a dictionary onto the queue (FIFO - added to end).

```python
async def Push(self, item: dict) -> bool
```

**Parameters:**
- `item` (dict): Dictionary to push onto the queue. Must be a valid Python dictionary that can be JSON-serialized.

**Returns:**
- `bool`: `True` if push was successful, `False` if push failed (e.g., invalid input type)

**Behavior:**
- Appends item to the end of the queue (FIFO)
- Persists queue state to Dapr state store
- Returns immediately after state is saved
- Thread-safe (actor processes one request at a time)

**Example:**

```python
from dapr.actor import ActorId, ActorProxy
from push_pop_actor import PushPopActorInterface

proxy = ActorProxy.create(
    actor_type="PushPopActor",
    actor_id=ActorId("my-queue"),
    actor_interface=PushPopActorInterface
)

# Simple item
success = await proxy.Push({"task": "send_email"})
print(success)  # True

# Complex nested item
success = await proxy.Push({
    "task_id": 123,
    "action": "process_upload",
    "metadata": {
        "user_id": 456,
        "file": "document.pdf",
        "tags": ["urgent", "important"]
    }
})
print(success)  # True

# Invalid item (not a dict)
success = await proxy.Push("not a dict")
print(success)  # False
```

**Error Handling:**

```python
try:
    success = await proxy.Push(item)
    if not success:
        print("Push failed - check item is a valid dict")
except Exception as e:
    print(f"Actor invocation error: {e}")
```

---

### Pop

Pop a single dictionary from the queue (FIFO - removed from front).

```python
async def Pop(self) -> list
```

**Parameters:**
- None

**Returns:**
- `list`: Array with single dictionary, or empty array `[]` if queue is empty.

**Behavior:**
- Removes and returns a single item from the front of the queue
- Returns empty array if queue is empty
- Persists updated queue state to Dapr state store
- Items are returned in FIFO order (oldest first)

**Example:**

```python
# Pop single item
items = await proxy.Pop()
if items:
    print(items[0])  # {"task": "send_email"}
else:
    print("Queue is empty")

# Pop from empty queue
items = await proxy.Pop()
print(items)  # []
```

**Processing Pattern:**

```python
# Consumer loop - pop one item at a time
while True:
    items = await proxy.Pop()

    if not items:
        await asyncio.sleep(1)  # Wait for more items
        continue

    await process_item(items[0])

# Consumer loop - pop multiple items
all_items = []
for _ in range(10):  # Pop up to 10 items
    items = await proxy.Pop()
    if not items:
        break
    all_items.extend(items)

for item in all_items:
    await process_item(item)
```

### PopWithAck

Pop a single dictionary from the queue with acknowledgement requirement (FIFO with lock).

```python
async def PopWithAck(self, data: dict) -> dict
```

**Parameters:**
- `data` (dict): Dictionary containing:
  - `ttl_seconds` (int, optional): Lock TTL in seconds (default: 30, range: 1-300)

**Returns:**
- `dict`: Dictionary with the following keys:
  - `items` (list): Array of popped dictionaries
  - `count` (int): Number of items returned
  - `locked` (bool): `True` if lock was created, `False` if queue empty or already locked
  - `lock_id` (str, optional): Lock ID to use for acknowledgement (present if `locked=True`)
  - `lock_expires_at` (float, optional): Unix timestamp when lock expires (present if `locked=True`)
  - `message` (str, optional): Status message (e.g., "Queue is locked pending acknowledgement")

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

```python
# Pop with acknowledgement
result = await proxy.PopWithAck({"ttl_seconds": 60})

if result["locked"] and result["count"] > 0:
    # Got items with lock
    items = result["items"]
    lock_id = result["lock_id"]

    try:
        # Process items
        for item in items:
            await process_item(item)

        # Acknowledge successful processing
        ack_result = await proxy.Acknowledge({"lock_id": lock_id})
        print(ack_result["success"])  # True
    except Exception as e:
        # Don't acknowledge - lock will expire and items return to queue
        logger.error(f"Processing failed: {e}")
elif result["locked"] and result["count"] == 0:
    # Queue is locked by another operation
    print(f"Queue locked until {result['lock_expires_at']}")
else:
    # Queue is empty
    print("No items available")
```

**Edge Cases:**

```python
# Pop while another lock is active
result1 = await proxy.PopWithAck({})  # Success
result2 = await proxy.PopWithAck({})  # Locked
print(result2["locked"])  # True
print(result2["count"])   # 0
print(result2["message"]) # "Queue is locked pending acknowledgement"

# Custom TTL
result = await proxy.PopWithAck({"ttl_seconds": 120})  # 2 minute lock

# TTL bounds are enforced (1-300 seconds)
result = await proxy.PopWithAck({"ttl_seconds": 500})  # Clamped to 300
```

### Acknowledge

Acknowledge popped items using lock ID.

```python
async def Acknowledge(self, data: dict) -> dict
```

**Parameters:**
- `data` (dict): Dictionary containing:
  - `lock_id` (str): The lock ID returned by `PopWithAck`

**Returns:**
- `dict`: Dictionary with the following keys:
  - `success` (bool): `True` if acknowledged, `False` if failed
  - `message` (str): Status message
  - `items_acknowledged` (int, optional): Number of items acknowledged (present if `success=True`)
  - `error_code` (str, optional): Error code (e.g., "LOCK_EXPIRED")

**Behavior:**
- Validates lock ID against active lock
- If valid: removes lock and returns success
- If lock expired: removes expired lock and returns "LOCK_EXPIRED" error
- If lock not found: returns "not found" error
- If lock ID doesn't match: returns "invalid" error
- Items are already removed from queue during `PopWithAck`

**Example:**

```python
# Successful acknowledgement
result = await proxy.PopWithAck({})
lock_id = result["lock_id"]

# Process items...

ack_result = await proxy.Acknowledge({"lock_id": lock_id})
print(ack_result)
# {
#     "success": True,
#     "message": "Items acknowledged successfully",
#     "items_acknowledged": 5
# }

# Expired lock
await asyncio.sleep(35)  # Wait past 30 second default TTL
ack_result = await proxy.Acknowledge({"lock_id": lock_id})
print(ack_result)
# {
#     "success": False,
#     "message": "Lock has expired",
#     "error_code": "LOCK_EXPIRED"
# }

# Invalid lock ID
ack_result = await proxy.Acknowledge({"lock_id": "wrong_id"})
print(ack_result)
# {
#     "success": False,
#     "message": "Invalid lock_id"
# }
```

**Processing Pattern with Acknowledgement:**

```python
# Consumer loop with acknowledgement
while True:
    result = await proxy.PopWithAck({"ttl_seconds": 60})

    if not result["locked"] or result["count"] == 0:
        await asyncio.sleep(1)
        continue

    lock_id = result["lock_id"]
    items = result["items"]

    try:
        # Process all items
        for item in items:
            await process_item(item)

        # Acknowledge successful processing
        await proxy.Acknowledge({"lock_id": lock_id})
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        # Don't acknowledge - items will return to queue after TTL
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

### Item (Dictionary)

Items pushed to the queue must be JSON-serializable Python dictionaries.

**Valid Items:**

```python
# Simple flat dict
{"id": 1, "name": "Alice"}

# Nested structures
{
    "user": {"id": 123, "email": "alice@example.com"},
    "metadata": {"tags": ["urgent"], "priority": 5}
}

# Arrays
{"items": [1, 2, 3], "total": 3}

# Mixed types
{
    "string": "value",
    "number": 123,
    "float": 45.67,
    "boolean": True,
    "null": None,
    "array": [1, 2, 3],
    "nested": {"key": "value"}
}
```

**Invalid Items:**

```python
# Not a dict
"string"
123
[1, 2, 3]
None

# Non-JSON-serializable
{"datetime": datetime.now()}  # datetime objects can't be JSON serialized
{"function": lambda x: x}     # functions can't be serialized
{"bytes": b"binary data"}     # bytes can't be JSON serialized directly
```

**Best Practice:**

Convert non-serializable types before pushing:

```python
from datetime import datetime

# Convert datetime to ISO string
item = {
    "created_at": datetime.now().isoformat(),
    "data": "payload"
}
await proxy.Push(item)
```

---

## Error Handling

### Actor Method Errors

```python
from dapr.actor import ActorProxy, ActorId
from push_pop_actor import PushPopActorInterface

try:
    proxy = ActorProxy.create(
        actor_type="PushPopActor",
        actor_id=ActorId("my-queue"),
        actor_interface=PushPopActorInterface
    )

    success = await proxy.Push({"data": "value"})
    if not success:
        # Handle push failure (e.g., invalid item type)
        pass

    items = await proxy.Pop(10)
    # items is always a list (empty if no items)

except Exception as e:
    # Handle actor invocation errors
    # - Dapr sidecar not running
    # - Network issues
    # - Actor not registered
    print(f"Error: {e}")
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
   ```python
   from slowapi import Limiter
   limiter = Limiter(key_func=get_remote_address)

   @app.post("/queue/{queue_id}/push")
   @limiter.limit("100/minute")
   async def push_item(...):
       ...
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

```python
# ❌ Inefficient - Many roundtrips
for i in range(100):
    await proxy.Push({"id": i})

# ✅ Better - Single actor, single queue, processed serially
items = [{"id": i} for i in range(100)]
for item in items:
    await proxy.Push(item)

# ✅ Best - Use multiple actors for parallelism
actors = [ActorProxy.create(..., ActorId(f"queue-{i}"), ...) for i in range(10)]
for i, item in enumerate(items):
    await actors[i % 10].Push(item)
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

## Version Compatibility

- **Dapr**: 1.17.0+
- **Python**: 3.11+
- **push-pop-actor**:
  - v3.x: Non-segmented queues
  - v4.0+: **Segmented queues** (breaking change)

### Version 4.0 Breaking Changes

V4.0 introduces segmented queue architecture for improved performance:

- **State Format**: Changed from `queue_N` to `queue_N_seg_M` keys
- **Migration**: Requires draining v3.x queues before upgrading (see [features/segmented-queue.md](../features/segmented-queue.md))
- **Benefits**: Constant memory/network per operation, scales to millions of items
- **API**: No API changes - fully transparent to users

---

## See Also

- [QUICKSTART.md](QUICKSTART.md) - Getting started guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - How it works under the hood
- [README.md](../README.md) - Project overview
- [Examples](../examples/) - Code examples
