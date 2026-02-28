# Feature: Segmented Queue Architecture

## Overview

The Segmented Queue Architecture is a performance optimization that splits large priority queues into fixed-size segments (default: 100 items per segment). This prevents memory, network, and compute bottlenecks when queues grow large by ensuring operations only load/serialize small chunks of data at a time.

**Key Characteristics:**
- **Fixed-Size Segments**: Each segment stores max 100 items (configurable)
- **Transparent to API**: No API changes - works seamlessly with existing Push/Pop methods
- **Head/Tail Pointers**: Metadata tracks which segment to pop from (head) and push to (tail)
- **Automatic Allocation**: New segments created automatically when tail segment fills
- **Automatic Cleanup**: Empty head segments deleted immediately after draining
- **Independent per Priority**: Each priority level has its own segment numbering

## Use Cases

- **Large Queues**: Queues with hundreds or thousands of items
- **High-Throughput Systems**: Systems pushing/popping frequently with large backlogs
- **Memory-Constrained Environments**: Limit memory footprint per operation
- **Network Optimization**: Reduce serialization overhead to state store
- **Scalability**: Enable queues to grow to millions of items without performance degradation

## Architecture

### State Key Structure

**Before (Non-Segmented)**:
```
queue_0: [item1, item2, ..., item1000]  // All 1000 items in one key
```

**After (Segmented)**:
```
queue_0_seg_0: [items 0-99]      // First 100 items
queue_0_seg_1: [items 100-199]   // Next 100 items
queue_0_seg_2: [items 200-299]   // etc.
...
queue_0_seg_9: [items 900-999]   // Last 100 items
```

### Metadata Structure

```json
{
  "config": {
    "segment_size": 100
  },
  "queues": {
    "queue_0": {
      "metadata": {
        "count": 250,
        "head_segment": 0,
        "tail_segment": 2
      }
    }
  }
}
```

**Metadata Fields**:
- `config.segment_size`: Max items per segment (default: 100)
- `head_segment`: Segment to pop from (oldest items, front of queue)
- `tail_segment`: Segment to push to (newest items, back of queue)
- `count`: Total items across all segments for this priority

### Segment Lifecycle

#### Push Flow
```
1. Get tail_segment from metadata (e.g., segment 2)
2. Load tail segment: queue_0_seg_2
3. If len(segment) < 100: append item to segment
4. If len(segment) == 100:
   - Allocate new segment (tail_segment = 3)
   - Create empty segment: queue_0_seg_3
   - Append item to new segment
5. Save segment and updated metadata
```

#### Pop Flow
```
1. Get head_segment from metadata (e.g., segment 0)
2. Load head segment: queue_0_seg_0
3. Pop item from front of segment
4. If segment becomes empty:
   - If head_segment < tail_segment:
     - Delete empty segment (set to [])
     - Increment head_segment to next (1)
   - If head_segment == tail_segment:
     - Queue is now empty, delete metadata
5. Save updated segment (if not empty) and metadata
```

#### Segment Cleanup
- Empty head segments are deleted immediately (not saved back)
- Tail segment remains even when empty (it's the current push target)
- When last segment empties, queue metadata is removed

### State Schema Example

**Actor with 250 items in priority 0**:

```json
// State Store Keys:
{
  "queue_0_seg_0": [
    {"id": 1, "task": "process"},
    {"id": 2, "task": "send"},
    ... // 98 more items (100 total)
  ],
  "queue_0_seg_1": [
    {"id": 101, "task": "analyze"},
    ... // 99 more items (100 total)
  ],
  "queue_0_seg_2": [
    {"id": 201, "task": "archive"},
    ... // 49 more items (50 total)
  ],
  "metadata": {
    "config": {"segment_size": 100},
    "queues": {
      "queue_0": {
        "metadata": {
          "count": 250,
          "head_segment": 0,
          "tail_segment": 2
        }
      }
    }
  }
}
```

## API Changes

**No API changes** - segmentation is fully transparent:

```python
# Push works exactly the same
await actor.Push({"item": {"data": "value"}, "priority": 0})

# Pop works exactly the same
items = await actor.Pop()
```

The only visible change is in the state store - segments are created/deleted automatically.

## Examples

### Example 1: Basic Usage (Transparent)

```python
from push_pop_actor import PushPopActor

# Push 150 items - creates 2 segments automatically
for i in range(150):
    await actor.Push({"item": {"id": i}, "priority": 0})

# Pop items - drains from segment 0, then segment 1
for _ in range(150):
    result = await actor.Pop()
    # Segments cleaned up automatically as they empty
```

### Example 2: Large Queue

```python
# Push 1000 items - creates 10 segments
for i in range(1000):
    await actor.Push({"item": {"task_id": i}, "priority": 0})

# Each operation only loads 100 items max
# Memory: ~10-50KB per operation vs 1-5MB for full queue
# Network: ~10-50KB serialized vs 1-5MB per save
```

### Example 3: Multiple Priorities with Segments

```python
# Each priority has independent segment numbering
for i in range(150):
    await actor.Push({"item": {"id": i}, "priority": 0})  # queue_0_seg_0, queue_0_seg_1
    await actor.Push({"item": {"id": i}, "priority": 1})  # queue_1_seg_0, queue_1_seg_1

# Pop drains priority 0 completely (both segments), then priority 1
```

### Example 4: Inspecting State via Dapr API

```bash
# View segment directly via Dapr actor state API
curl http://localhost:3500/v1.0/actors/PushPopActor/my-queue/state/queue_0_seg_0

# View metadata
curl http://localhost:3500/v1.0/actors/PushPopActor/my-queue/state/metadata
```

## Edge Cases

### 1. Segment Transition
**Scenario**: Pop drains all items from head segment
**Result**: Head segment deleted, head_segment pointer incremented, pop continues from next segment

### 2. Single Segment
**Scenario**: Queue has < 100 items
**Result**: Only one segment exists (head_segment == tail_segment), works normally

### 3. Returned Items Overflow
**Scenario**: PopWithAck expires and returns items to head segment, causing it to exceed 100 items temporarily
**Result**: Allowed - segment can temporarily exceed limit when items are returned (avoids complex splitting logic)

### 4. Empty Queue
**Scenario**: Pop called on empty queue
**Result**: No segments exist, metadata has no queue entry, returns empty list

### 5. Segment Cleanup During Pop
**Scenario**: Pop removes last item from head segment, but more segments exist
**Result**: Head segment not saved (deleted), head pointer incremented, metadata updated

## Performance Characteristics

### Memory Usage

**Before Segmentation**:
- Push: Load entire queue (N items) into memory
- Pop: Load entire queue (N items) into memory

**After Segmentation**:
- Push: Load max 100 items into memory
- Pop: Load max 100 items into memory

**Example**: Queue with 10,000 items
- Before: 1-5MB per operation
- After: 10-50KB per operation (100x reduction)

### Network Overhead

**Before Segmentation**:
- Save operation: Serialize entire queue (N items)

**After Segmentation**:
- Save operation: Serialize max 100 items

**Example**: Queue with 10,000 items
- Before: 1-5MB per save
- After: 10-50KB per save (100x reduction)

### Time Complexity

**Push**:
- Before: O(1) append + O(N) serialize
- After: O(1) append + O(1) serialize (fixed segment size)

**Pop**:
- Before: O(N) slice + O(N) serialize
- After: O(1) slice + O(1) serialize (fixed segment size)

### State Operations

**Push** (normal case):
- 2 state reads (metadata + tail segment)
- 2 state writes (segment + metadata)

**Pop** (normal case):
- 2 state reads (metadata + head segment)
- 2 state writes (segment + metadata)

**Pop** (segment transition):
- 2 state reads
- 1 state write (metadata only, empty segment not saved)

## Migration and Compatibility

### Breaking Changes

**IMPORTANT**: This is a **breaking change**. Segmented queues are incompatible with pre-v4.0 state format.

**Old Format** (v3.x):
```json
{
  "queue_0": [item1, item2, ...],
  "metadata": {"queues": {"queue_0": {"metadata": {"count": N}}}}
}
```

**New Format** (v4.0+):
```json
{
  "queue_0_seg_0": [items...],
  "metadata": {
    "config": {"segment_size": 100},
    "queues": {
      "queue_0": {
        "metadata": {
          "count": N,
          "head_segment": 0,
          "tail_segment": M
        }
      }
    }
  }
}
```

### Migration Steps

**Option 1: Fresh Start** (Recommended)
1. Drain all items from old actors (Pop until empty)
2. Deploy v4.0+ with segmented queues
3. Re-push items if needed

**Option 2: Manual State Migration** (Advanced)
1. Export state from old format using Dapr API
2. Transform to new format (split into segments)
3. Import to new state keys
4. Deploy v4.0+

**Option 3: Lazy Migration** (Future Enhancement - Not Implemented)
- Check for old `queue_N` keys on first access
- Migrate to segments on-the-fly
- Requires additional migration code

### Rollback

To rollback to v3.x:
1. Drain all segmented queues
2. Clear actor state
3. Deploy v3.x
4. Re-push items

## Implementation Details

### Segment Size Configuration

- Default: 100 items per segment
- Stored in: `metadata["config"]["segment_size"]`
- Applied: On actor activation
- Change impact: Only affects newly created segments

**Why 100?**
- Balances memory overhead (100 dicts ~10-50KB typically)
- Fast serialization (<10ms network + serialize time)
- Reasonable granularity for cleanup operations
- Low state operation overhead (2 reads, 2 writes per Push/Pop)

### Helper Methods

```python
_get_segment_key(priority, segment)  # Build segment key
_get_segment_size(metadata)          # Get configured size
_get_head_segment(metadata, priority)  # Get head pointer
_get_tail_segment(metadata, priority)  # Get tail pointer
_set_segment_pointers(metadata, priority, head, tail)  # Update pointers
```

### Validation

**Segment Size**: Must be positive integer (default: 100)
**Segment Numbers**: Auto-incrementing, starting from 0
**Head/Tail**: head_segment <= tail_segment always

### Logging

```
INFO: Pushed item to priority 0 segment 2 for actor my-queue. Segment size: 87, Total count: 287
INFO: Popped 1 item from priority 0 segment 0 for actor my-queue. Remaining count: 286
INFO: Popped 1 item from priority 0 segment 0 (now empty, moved to segment 1). Remaining count: 200
INFO: Popped last item from priority 0 for actor my-queue. Queue now empty.
```

## Testing

### Unit Tests

Comprehensive test coverage including:
- Segment allocation when full (100+ items)
- Cross-segment pop transitions
- Empty segment cleanup
- Large queues (350+ items, 4 segments)
- Priority + segment combinations
- PopWithAck with segmented returns
- Segment size configuration

**Run tests**:
```bash
pytest tests/test_actor.py -v
pytest tests/test_actor.py -k "segment" -v  # Segment-specific tests
```

### Integration Tests

**Manual testing**:
```bash
# Start stack
docker-compose up

# Push 200 items
for i in {1..200}; do
  curl -X POST http://localhost:8000/queue/test/push \
    -H "Content-Type: application/json" \
    -d "{\"item\": {\"id\": $i}}"
done

# Verify segments via Dapr API
curl http://localhost:3500/v1.0/actors/PushPopActor/test/state/queue_0_seg_0
curl http://localhost:3500/v1.0/actors/PushPopActor/test/state/queue_0_seg_1

# Pop all items
for i in {1..200}; do
  curl -X POST http://localhost:8000/queue/test/pop
done
```

## Best Practices

1. **Monitor Segment Count**: Track how many segments exist per priority
2. **Avoid Sparse Priorities**: Don't use priorities 0, 100, 1000 (creates many segment keys)
3. **Pop Regularly**: Prevent unbounded segment growth
4. **Use Default Segment Size**: 100 is optimized for most use cases
5. **Plan Migration**: Test migration strategy before upgrading

## Performance Benefits

| Metric | Before (Single Queue) | After (Segmented) | Improvement |
|--------|----------------------|-------------------|-------------|
| Memory per Push | N items | 100 items | 100x for N=10k |
| Memory per Pop | N items | 100 items | 100x for N=10k |
| Network per Save | N items serialized | 100 items serialized | 100x for N=10k |
| Pop Time Complexity | O(N) slice | O(1) slice | Linear to constant |
| Max Queue Size | Limited by memory | Unlimited | Scalable |

## References

- [PushPopActor API Reference](../docs/API_REFERENCE.md)
- [Architecture Documentation](../docs/ARCHITECTURE.md)
- [N-Queue Priority System](./n-queue-priority-system.md)
- [Message Acknowledgement](./message-acknowledgement.md)
- [Dapr Actors Documentation](https://docs.dapr.io/developing-applications/building-blocks/actors/)

## Version

- **Introduced**: v4.0.0
- **Last Updated**: 2026-02-28
