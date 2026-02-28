# Feature: Message Acknowledgement

## Overview

The Message Acknowledgement feature adds at-least-once delivery semantics to the PushPopActor by implementing a lock-based acknowledgement system. When enabled, popped messages are held in a locked state until explicitly acknowledged or until the TTL expires, preventing message loss if consumers fail during processing.

**Key Characteristics:**
- **Optional Acknowledgement**: Backward compatible - original Pop method unchanged
- **Lock-Based Protection**: Prevents concurrent pops while waiting for acknowledgement
- **Automatic Expiration**: Messages automatically return to queue after TTL (default: 30s)
- **Single Lock Per Queue**: Only one lock active at a time per actor instance
- **Priority-Aware Return**: Expired items return to their **original priority queues** for reprocessing

## Use Cases

- **Reliable Message Processing**: Ensure messages aren't lost if consumer crashes
- **Transaction-Like Semantics**: Commit or rollback message consumption
- **Worker Failure Recovery**: Auto-retry messages when workers fail without acknowledgement
- **Critical Task Processing**: Guarantee important tasks are completed before removal
- **Idempotent Retry Logic**: Re-deliver messages that weren't successfully processed

## Architecture

### Lock State Management

The lock is stored in the existing `metadata` state key using a reserved `_active_lock` key:

**State Schema:**
```json
{
  "0": 3,
  "1": 5,
  "_active_lock": {
    "lock_id": "abc123def456",
    "items_with_priority": [
      {"item": {"id": 1}, "priority": 0},
      {"item": {"id": 2}, "priority": 1}
    ],
    "expires_at": 1709139245.123,
    "created_at": 1709139215.123
  }
}
```

**Note:** The lock stores `items_with_priority` (not flat `items`) to preserve priority information. This ensures expired items return to their original priority queues.

**Lock ID Format:**
- Generated using `secrets.token_urlsafe(8)`
- 11 characters (URL-safe base64)
- Example: `abc123def456`

**TTL Enforcement:**
- Checked on every `PopWithAck` call
- Expired locks trigger automatic item return to **original priority queues**
- TTL range: 1-300 seconds (default: 30)

## API Changes

### New Method: PopWithAck

**Signature:**
```python
async def PopWithAck(self, data: dict) -> dict
```

**Parameters:**
- `data` (dict): Dictionary containing:
    - `ttl_seconds` (int, optional): Lock TTL in seconds (default: 30, range: 1-300)

**Returns:**
```python
{
    "items": List[dict],           # Popped items
    "count": int,                  # Number of items
    "locked": bool,                # True if lock created
    "lock_id": str,                # Lock ID (if locked=True)
    "lock_expires_at": float,      # Expiration timestamp (if locked=True)
    "message": str                 # Optional status message
}
```

**Behavior:**
1. Checks for existing active lock
2. If lock exists and not expired: returns 423 status info
3. If lock expired: returns items to **their original priority queues**, removes lock, continues
4. Pops items while tracking priority metadata (doesn't use internal Pop method)
5. If no items: returns unlocked empty result
6. Creates lock with generated ID, TTL, and priority-aware item storage
7. Stores lock in `metadata["_active_lock"]` with `items_with_priority` format
8. Returns locked result with lock_id (priority metadata hidden from client)

**Example:**
```python
# Pop with acknowledgement
result = await actor.PopWithAck({"ttl_seconds": 60})

# Result (success):
{
    "items": [{"id": 1}, {"id": 2}],
    "count": 2,
    "locked": True,
    "lock_id": "abc123def456",
    "lock_expires_at": 1709139275.0
}

# Result (locked by another operation):
{
    "items": [],
    "count": 0,
    "locked": True,
    "lock_expires_at": 1709139245.0,
    "message": "Queue is locked pending acknowledgement"
}
```

### New Method: Acknowledge

**Signature:**
```python
async def Acknowledge(self, data: dict) -> dict
```

**Parameters:**
- `data` (dict): Dictionary containing:
  - `lock_id` (str): The lock ID to acknowledge

**Returns:**
```python
{
    "success": bool,               # True if acknowledged
    "message": str,                # Status message
    "items_acknowledged": int,     # Number of items (if success=True)
    "error_code": str              # Optional error code
}
```

**Behavior:**
1. Validates lock_id is provided
2. Loads active lock from state
3. If no lock exists: returns "not found" error
4. If lock expired: removes lock, returns "LOCK_EXPIRED" error
5. If lock_id doesn't match: returns "invalid" error
6. If valid: removes lock, returns success

**Example:**
```python
# Acknowledge with valid lock
result = await actor.Acknowledge({"lock_id": "abc123def456"})

# Result (success):
{
    "success": True,
    "message": "Items acknowledged successfully",
    "items_acknowledged": 2
}

# Result (expired):
{
    "success": False,
    "message": "Lock has expired",
    "error_code": "LOCK_EXPIRED"
}
```

### Existing Method: Pop (Unchanged)

The original `Pop` method remains unchanged for backwards compatibility:

```python
async def Pop(self) -> List[Dict[str, Any]]
```

No acknowledgement required, items removed immediately.

## REST API Endpoints

### Updated Endpoint: POST /queue/{queue_id}/pop

**Query Parameters:**
- `require_ack` (bool, optional): Require acknowledgement (default: False)
- `ttl_seconds` (int, optional): Lock TTL in seconds (default: 30, range: 1-300)

**Response (require_ack=false):**
```json
{
  "items": [{"id": 1}],
  "count": 1
}
```

**Response (require_ack=true, success):**
```json
{
  "items": [{"id": 1}],
  "count": 1,
  "locked": true,
  "lock_id": "abc123def456",
  "lock_expires_at": 1709139275.0
}
```

**Response (require_ack=true, locked - HTTP 423):**
```json
{
  "message": "Queue is locked pending acknowledgement",
  "lock_expires_at": 1709139245.0
}
```

### New Endpoint: POST /queue/{queue_id}/acknowledge

**Request Body:**
```json
{
  "lock_id": "abc123def456"
}
```

**Response (success - HTTP 200):**
```json
{
  "success": true,
  "message": "Items acknowledged successfully",
  "items_acknowledged": 2
}
```

**Response (expired - HTTP 410):**
```json
{
  "success": false,
  "message": "Lock has expired",
  "error_code": "LOCK_EXPIRED"
}
```

**Response (not found - HTTP 404):**
```json
{
  "success": false,
  "message": "No active lock found"
}
```

**Response (invalid - HTTP 400):**
```json
{
  "success": false,
  "message": "Invalid lock_id"
}
```

## HTTP Status Codes

| Scenario | Status Code | Rationale |
|----------|-------------|-----------|
| Pop without ack (success) | 200 OK | Standard success |
| Pop with ack (success) | 200 OK | Standard success |
| Pop with ack (queue locked) | 423 Locked | Resource temporarily locked |
| Acknowledge (success) | 200 OK | Standard success |
| Acknowledge (expired lock) | 410 Gone | Resource existed but expired |
| Acknowledge (lock not found) | 404 Not Found | Lock doesn't exist |
| Acknowledge (invalid lock_id) | 400 Bad Request | Client error |
| Acknowledge (missing lock_id) | 400 Bad Request | Client error |

## Examples

### Example 1: Basic Acknowledgement Flow

```bash
# Push an item
curl -X POST "http://localhost:8000/queue/my-queue/push" \
  -H "Content-Type: application/json" \
  -d '{"item": {"task_id": 123, "action": "send_email"}}'

# Pop with acknowledgement
curl -X POST "http://localhost:8000/queue/my-queue/pop?require_ack=true"
# Response: {"items": [...], "lock_id": "abc123def456", ...}

# Process the item...

# Acknowledge completion
curl -X POST "http://localhost:8000/queue/my-queue/acknowledge" \
  -H "Content-Type: application/json" \
  -d '{"lock_id": "abc123def456"}'
# Response: {"success": true, "items_acknowledged": 1}
```

### Example 2: Lock Prevents Concurrent Pops

```bash
# First pop with ack
curl -X POST "http://localhost:8000/queue/test/pop?require_ack=true"
# Response: {"locked": true, "lock_id": "xyz789", ...}

# Second pop attempt (while locked)
curl -X POST "http://localhost:8000/queue/test/pop"
# Response (HTTP 423): {"message": "Queue is locked...", "lock_expires_at": ...}
```

### Example 3: Automatic Expiration

```bash
# Pop with short TTL
curl -X POST "http://localhost:8000/queue/test/pop?require_ack=true&ttl_seconds=5"
# Response: {"lock_id": "short123", "lock_expires_at": 1709139220.0}

# Wait 6 seconds...

# Try to acknowledge (too late)
curl -X POST "http://localhost:8000/queue/test/acknowledge" \
  -d '{"lock_id": "short123"}'
# Response (HTTP 410): {"success": false, "error_code": "LOCK_EXPIRED"}

# Next pop returns the item again
curl -X POST "http://localhost:8000/queue/test/pop?require_ack=true"
# Response: {"items": [...]}  # Original item returned
```

### Example 4: Backwards Compatibility

```bash
# Regular pop (no acknowledgement)
curl -X POST "http://localhost:8000/queue/test/pop"
# Response: {"items": [...], "count": 5}
# Items immediately removed, no lock created
```

## Edge Cases

### 1. Pop While Locked
**Scenario:** PopWithAck called while another lock is active
**Result:** Returns 423 with lock expiration time, no items popped

### 2. Acknowledge Expired Lock
**Scenario:** Acknowledge called after TTL expires
**Result:** Returns 410 Gone, items already returned to their original priority queues

### 3. Acknowledge Invalid Lock ID
**Scenario:** Acknowledge called with wrong lock_id
**Result:** Returns 400 Bad Request, lock remains active

### 4. Empty Queue with Acknowledgement
**Scenario:** PopWithAck on empty queue
**Result:** Returns unlocked empty result (no lock created)

### 5. Lock Expiration During Processing
**Scenario:** TTL expires while consumer is processing
**Result:** Items automatically returned to their **original priority queues**, next pop retrieves them in priority order

### 6. Actor Deactivation with Active Lock
**Scenario:** Actor deactivates while lock is active
**Result:** Lock persists in state, checked on reactivation

### 7. Multiple Items in Single Lock
**Scenario:** PopWithAck with single item
**Result:** All items stored in single lock, acknowledged together

## Performance Characteristics

### State Operations

**PopWithAck:**
- Same as regular Pop, plus 1 additional write for lock
- ~2-5ms additional latency

**Acknowledge:**
- 1 read + 1 write to metadata
- ~3-5ms total latency

**Expired Lock Cleanup:**
- Triggered on next PopWithAck
- Returns items to queue_0 front
- ~5-10ms additional latency (one-time cost)

### Lock Storage Overhead

- Lock stored in existing `metadata` key (no new state key)
- Lock size: ~200-500 bytes depending on item count
- Minimal impact on state store

## Testing

### Unit Tests

15 comprehensive tests covering:
- Lock creation and validation
- Acknowledgement success/failure
- Lock expiration and item return
- Concurrent pop prevention (423 status)
- Backwards compatibility
- TTL bounds enforcement
- Edge cases (empty queue, invalid locks, etc.)

**Run tests:**
```bash
pytest tests/test_actor.py::test_pop_with_ack_creates_lock -v
pytest tests/test_actor.py -k "acknowledgement" -v
```

### Integration Tests

**Full flow test:**
```bash
# Start stack
docker-compose up

# Test acknowledgement flow
bash examples/test_acknowledgement_flow.sh
```

## Migration and Compatibility

### Breaking Changes

**None.** This feature is fully backwards compatible:
- Original `Pop` method unchanged
- New methods are opt-in via `require_ack` query parameter
- Existing code continues to work without modification

### State Schema Changes

- Adds `_active_lock` key to `metadata` (when lock is active)
- No migration required for existing actors
- Lock automatically removed on acknowledgement or expiration

## Implementation Details

### Lock ID Generation

```python
import secrets
lock_id = secrets.token_urlsafe(8)  # 11 characters, cryptographically secure
```

### TTL Validation

```python
ttl = min(max(data.get("ttl_seconds", 30), 1), 300)  # Clamp to 1-300 seconds
```

### Expired Item Return

Items from expired locks are returned to the **front** of their original priority queues:

```python
# Group items by priority
items_by_priority = {}  # {priority: [items]}

# Return each group to its original queue
for priority, items in items_by_priority.items():
    queue = items + existing_queue  # Prepend to front
```

This ensures:
- Items maintain their original priority level
- Immediate reprocessing within their priority tier
- Priority system integrity is preserved

## Best Practices

1. **Set Appropriate TTL**: Base TTL on expected processing time + buffer
2. **Implement Idempotency**: Handle duplicate deliveries gracefully
3. **Monitor Lock Expirations**: Track how often locks expire without ack
4. **Use for Critical Tasks**: Reserve acknowledgements for important work
5. **Clean Up on Failure**: Acknowledge or let expire, don't leave locks dangling

## References

- [PushPopActor API Reference](../docs/API_REFERENCE.md)
- [Architecture Documentation](../docs/ARCHITECTURE.md)
- [N-Queue Priority System](./n-queue-priority-system.md)
- [Dapr Actors Documentation](https://docs.dapr.io/developing-applications/building-blocks/actors/)

## Version

- **Introduced**: v3.0.0
- **Last Updated**: 2026-02-28
