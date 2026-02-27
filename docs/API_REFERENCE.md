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

Pop N dictionaries from the queue (FIFO - removed from front).

```python
async def Pop(self, depth: int) -> list
```

**Parameters:**
- `depth` (int): Number of items to retrieve from the front of the queue. Must be a positive integer.

**Returns:**
- `list`: Array of dictionaries. Returns empty array `[]` if queue is empty or depth is invalid.

**Behavior:**
- Removes and returns up to `depth` items from the front of the queue
- If queue has fewer items than `depth`, returns all available items
- Returns empty array if queue is empty or `depth <= 0`
- Persists updated queue state to Dapr state store
- Items are returned in FIFO order (oldest first)

**Example:**

```python
# Pop single item
items = await proxy.Pop(1)
print(items)  # [{"task": "send_email"}]

# Pop multiple items
items = await proxy.Pop(5)
print(len(items))  # 5 (or fewer if queue has < 5 items)

# Pop from empty queue
items = await proxy.Pop(10)
print(items)  # []

# Pop all items (large depth)
items = await proxy.Pop(1000)
print(len(items))  # All items in queue
```

**Edge Cases:**

```python
# Zero depth
items = await proxy.Pop(0)
print(items)  # []

# Negative depth
items = await proxy.Pop(-5)
print(items)  # []

# Depth larger than queue size
await proxy.Push({"a": 1})
await proxy.Push({"b": 2})
items = await proxy.Pop(100)
print(len(items))  # 2 (not 100)
```

**Processing Pattern:**

```python
# Consumer loop
while True:
    items = await proxy.Pop(10)  # Process 10 at a time

    if not items:
        await asyncio.sleep(1)  # Wait for more items
        continue

    for item in items:
        await process_item(item)
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

Pop items from the specified queue.

**Path Parameters:**
- `queueId` (string): Unique identifier for the queue

**Query Parameters:**
- `depth` (integer, optional): Number of items to pop. Default: 1. Range: 1-100.

**Request Body:**
None

**Response (200 OK):**
```json
{
  "items": [
    {"task_id": 123, "action": "send_email"},
    {"task_id": 124, "action": "process_upload"}
  ],
  "count": 2
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
# Pop single item (default)
curl -X POST "http://localhost:8000/queue/my-queue/pop"

# Pop multiple items
curl -X POST "http://localhost:8000/queue/my-queue/pop?depth=10"

# Pop from empty queue (returns empty array)
curl -X POST "http://localhost:8000/queue/empty-queue/pop"
# Response: {"items": [], "count": 0}
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

# 422 Unprocessable Entity - Validation error
curl -X POST "http://localhost:8000/queue/my-queue/pop?depth=-1"

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
- **Network Calls**: 1 state store write per push
- **Recommendation**: Batch pushes when possible to reduce roundtrips

### Pop Performance

- **Time Complexity**: O(n) where n = depth
- **Network Calls**: 1 state store read + 1 write per pop
- **Memory**: All popped items loaded into memory
- **Recommendation**: Use appropriate depth (10-100 items) to balance throughput vs latency

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
- **Max Queue Size**: No hard limit, but large queues impact performance
- **Max Depth**: API server limits to 100 items per pop (configurable)
- **Concurrency**: One operation per actor at a time (per actor ID)

---

## Version Compatibility

- **Dapr**: 1.17.0+
- **Python**: 3.11+
- **push-pop-actor**: 0.1.0

---

## See Also

- [QUICKSTART.md](QUICKSTART.md) - Getting started guide
- [ARCHITECTURE.md](ARCHITECTURE.md) - How it works under the hood
- [README.md](../README.md) - Project overview
- [Examples](../examples/) - Code examples
