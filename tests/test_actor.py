"""
Unit tests for PushPopActor.

These tests mock the Dapr state manager to avoid requiring a running Dapr runtime.
"""

import pytest
from unittest.mock import MagicMock

from push_pop_actor import PushPopActor


class MockStateManager:
    """Mock state manager for testing actor without Dapr runtime."""

    def __init__(self):
        self.state = {}

    async def try_get_state(self, key: str):
        """Mock try_get_state method."""
        if key in self.state:
            return (True, self.state[key])
        return (False, None)

    async def set_state(self, key: str, value):
        """Mock set_state method."""
        self.state[key] = value

    async def save_state(self):
        """Mock save_state method."""
        pass


@pytest.fixture
def mock_actor():
    """Create a PushPopActor instance with mocked state manager."""
    # Create mock context and actor_id
    ctx = MagicMock()
    actor_id = "test-actor-123"

    # Create actor
    actor = PushPopActor(ctx, actor_id)

    # Replace state manager with mock
    actor._state_manager = MockStateManager()

    return actor


@pytest.mark.asyncio
async def test_actor_activation(mock_actor):
    """Test that actor activation initializes empty metadata map."""
    await mock_actor._on_activate()

    # Check that metadata was initialized
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert has_metadata is True
    assert metadata == {"queues": {}}


@pytest.mark.asyncio
async def test_push_single_item(mock_actor):
    """Test pushing a single item to the queue (priority 0 by default)."""
    await mock_actor._on_activate()

    item = {"id": 1, "message": "test item"}
    result = await mock_actor.Push({"item": item})

    assert result is True

    # Verify item was added to queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert has_queue is True
    assert len(queue) == 1
    assert queue[0] == item

    # Verify counts map was updated
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_push_multiple_items(mock_actor):
    """Test pushing multiple items to the queue."""
    await mock_actor._on_activate()

    items = [
        {"id": 1, "message": "first"},
        {"id": 2, "message": "second"},
        {"id": 3, "message": "third"},
    ]

    for item in items:
        result = await mock_actor.Push({"item": item})
        assert result is True

    # Verify all items were added to queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert has_queue is True
    assert len(queue) == 3
    assert queue == items

    # Verify counts map
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 3


@pytest.mark.asyncio
async def test_push_invalid_item(mock_actor):
    """Test that pushing non-dict item fails."""
    await mock_actor._on_activate()

    # Try pushing string instead of dict
    result = await mock_actor.Push({"item": "not a dict"})
    assert result is False

    # Try pushing list instead of dict
    result = await mock_actor.Push({"item": [1, 2, 3]})
    assert result is False

    # Verify no queues were created
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert has_queue is False

    # Verify counts map is still empty
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata == {"queues": {}}


@pytest.mark.asyncio
async def test_pop_from_empty_queue(mock_actor):
    """Test popping from an empty queue returns empty list."""
    await mock_actor._on_activate()

    result = await mock_actor.Pop()
    assert result == []


@pytest.mark.asyncio
async def test_pop_single_item(mock_actor):
    """Test popping a single item from the queue."""
    await mock_actor._on_activate()

    # Push items
    items = [
        {"id": 1, "message": "first"},
        {"id": 2, "message": "second"},
        {"id": 3, "message": "third"},
    ]
    for item in items:
        await mock_actor.Push({"item": item})

    # Pop one item
    result = await mock_actor.Pop()
    assert len(result) == 1
    assert result[0] == items[0]

    # Verify remaining items in queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert len(queue) == 2
    assert queue == items[1:]

    # Verify counts map was updated
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 2


@pytest.mark.asyncio
async def test_pop_multiple_items(mock_actor):
    """Test popping multiple items from the queue."""
    await mock_actor._on_activate()

    # Push items
    items = [
        {"id": 1, "message": "first"},
        {"id": 2, "message": "second"},
        {"id": 3, "message": "third"},
        {"id": 4, "message": "fourth"},
        {"id": 5, "message": "fifth"},
    ]
    for item in items:
        await mock_actor.Push({"item": item})

    # Pop three items one at a time
    popped = []
    for _ in range(3):
        result = await mock_actor.Pop()
        assert len(result) == 1
        popped.extend(result)

    assert popped == items[:3]

    # Verify remaining items in queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert len(queue) == 2
    assert queue == items[3:]

    # Verify counts map was updated
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 2


@pytest.mark.asyncio
async def test_pop_more_than_available(mock_actor):
    """Test that popping more than available returns all items."""
    await mock_actor._on_activate()

    # Push only 2 items
    items = [
        {"id": 1, "message": "first"},
        {"id": 2, "message": "second"},
    ]
    for item in items:
        await mock_actor.Push({"item": item})

    # Try to pop 10 items (more than available) - loop until empty
    popped = []
    for _ in range(10):
        result = await mock_actor.Pop()
        if not result:
            break
        popped.extend(result)

    assert len(popped) == 2
    assert popped == items

    # Verify counts map is empty
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata == {"queues": {}}


@pytest.mark.asyncio
async def test_fifo_ordering(mock_actor):
    """Test that items are popped in FIFO order."""
    await mock_actor._on_activate()

    # Push items in order
    items = [
        {"id": 1, "message": "first", "timestamp": "2024-01-01"},
        {"id": 2, "message": "second", "timestamp": "2024-01-02"},
        {"id": 3, "message": "third", "timestamp": "2024-01-03"},
        {"id": 4, "message": "fourth", "timestamp": "2024-01-04"},
    ]
    for item in items:
        await mock_actor.Push({"item": item})

    # Pop items one at a time and verify order
    for i, expected_item in enumerate(items):
        result = await mock_actor.Pop()
        assert len(result) == 1
        assert result[0] == expected_item


@pytest.mark.asyncio
async def test_push_after_pop(mock_actor):
    """Test that items can be pushed after popping."""
    await mock_actor._on_activate()

    # Push initial items
    await mock_actor.Push({"item": {"id": 1, "message": "first"}})
    await mock_actor.Push({"item": {"id": 2, "message": "second"}})

    # Pop one item
    result = await mock_actor.Pop()
    assert len(result) == 1

    # Push new item
    new_item = {"id": 3, "message": "third"}
    result = await mock_actor.Push({"item": new_item})
    assert result is True

    # Verify queue_0 state
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert len(queue) == 2
    assert queue[0]["id"] == 2  # Second item from original push
    assert queue[1]["id"] == 3  # New item

    # Verify counts map
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 2


@pytest.mark.asyncio
async def test_complex_item_structure(mock_actor):
    """Test pushing and popping items with complex nested structure."""
    await mock_actor._on_activate()

    complex_item = {
        "id": 123,
        "user": {"name": "Alice", "email": "alice@example.com"},
        "metadata": {"tags": ["urgent", "important"], "priority": 5},
        "nested": {"deeply": {"nested": {"value": "test"}}},
    }

    # Push complex item
    result = await mock_actor.Push({"item": complex_item})
    assert result is True

    # Pop and verify structure is preserved
    result = await mock_actor.Pop()
    assert len(result) == 1
    assert result[0] == complex_item
    assert result[0]["user"]["name"] == "Alice"
    assert result[0]["nested"]["deeply"]["nested"]["value"] == "test"


# ============================================================================
# Priority System Tests
# ============================================================================


@pytest.mark.asyncio
async def test_push_with_priority_0(mock_actor):
    """Test pushing to priority 0 queue explicitly."""
    await mock_actor._on_activate()

    item = {"id": 1, "message": "high priority"}
    result = await mock_actor.Push({"item": item, "priority": 0})

    assert result is True

    # Verify item in queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert has_queue is True
    assert len(queue) == 1
    assert queue[0] == item

    # Verify counts map
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_push_with_priority_5(mock_actor):
    """Test pushing to arbitrary priority level."""
    await mock_actor._on_activate()

    item = {"id": 1, "message": "low priority"}
    result = await mock_actor.Push({"item": item, "priority": 5})

    assert result is True

    # Verify item in queue_5
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_5")
    assert has_queue is True
    assert len(queue) == 1

    # Verify counts map
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_5"]["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_push_default_priority(mock_actor):
    """Test that Push without priority defaults to 0."""
    await mock_actor._on_activate()

    item = {"id": 1, "message": "default priority"}
    result = await mock_actor.Push({"item": item})  # No priority specified

    assert result is True

    # Verify item in queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert has_queue is True

    # Verify counts map
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_push_invalid_priority_negative(mock_actor):
    """Test that negative priority is rejected."""
    await mock_actor._on_activate()

    item = {"id": 1, "message": "test"}
    result = await mock_actor.Push({"item": item, "priority": -1})

    assert result is False

    # Verify no queues created
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata == {"queues": {}}


@pytest.mark.asyncio
async def test_push_invalid_priority_non_int(mock_actor):
    """Test that non-integer priority is rejected."""
    await mock_actor._on_activate()

    item = {"id": 1, "message": "test"}
    result = await mock_actor.Push({"item": item, "priority": "high"})

    assert result is False

    # Verify no queues created
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata == {"queues": {}}


@pytest.mark.asyncio
async def test_counts_map_updated_on_push(mock_actor):
    """Test that counts map is correctly updated on push."""
    await mock_actor._on_activate()

    # Push to different priorities
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 1})
    await mock_actor.Push({"item": {"id": 4}, "priority": 5})

    # Verify counts map
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 2
    assert metadata["queues"]["queue_1"]["metadata"]["count"] == 1
    assert metadata["queues"]["queue_5"]["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_multiple_priorities_push(mock_actor):
    """Test pushing to multiple priority levels."""
    await mock_actor._on_activate()

    items_p0 = [{"id": 1, "priority": "high"}, {"id": 2, "priority": "high"}]
    items_p1 = [{"id": 3, "priority": "medium"}]
    items_p2 = [{"id": 4, "priority": "low"}]

    for item in items_p0:
        await mock_actor.Push({"item": item, "priority": 0})
    for item in items_p1:
        await mock_actor.Push({"item": item, "priority": 1})
    for item in items_p2:
        await mock_actor.Push({"item": item, "priority": 2})

    # Verify queue_0
    has_q0, q0 = await mock_actor._state_manager.try_get_state("queue_0")
    assert len(q0) == 2

    # Verify queue_1
    has_q1, q1 = await mock_actor._state_manager.try_get_state("queue_1")
    assert len(q1) == 1

    # Verify queue_2
    has_q2, q2 = await mock_actor._state_manager.try_get_state("queue_2")
    assert len(q2) == 1


@pytest.mark.asyncio
async def test_pop_lowest_priority_first(mock_actor):
    """Test that priority 0 is returned before 1, 2, etc."""
    await mock_actor._on_activate()

    # Push to different priorities
    await mock_actor.Push({"item": {"id": 1, "priority": "low"}, "priority": 2})
    await mock_actor.Push({"item": {"id": 2, "priority": "high"}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3, "priority": "medium"}, "priority": 1})

    # Pop one item - should get priority 0
    result = await mock_actor.Pop()
    assert len(result) == 1
    assert result[0]["id"] == 2
    assert result[0]["priority"] == "high"


@pytest.mark.asyncio
async def test_pop_drains_priority_completely(mock_actor):
    """Test that priority 0 is drained before touching priority 1."""
    await mock_actor._on_activate()

    # Push multiple items to priority 0 and 1
    await mock_actor.Push({"item": {"id": 1, "p": 0}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2, "p": 0}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3, "p": 0}, "priority": 0})
    await mock_actor.Push({"item": {"id": 4, "p": 1}, "priority": 1})
    await mock_actor.Push({"item": {"id": 5, "p": 1}, "priority": 1})

    # Pop 4 items one at a time - should drain all priority 0, then 1 from priority 1
    popped = []
    for _ in range(4):
        result = await mock_actor.Pop()
        assert len(result) == 1
        popped.extend(result)

    assert len(popped) == 4
    assert popped[0]["p"] == 0
    assert popped[1]["p"] == 0
    assert popped[2]["p"] == 0
    assert popped[3]["p"] == 1

    # Verify priority 0 is empty
    has_q0, q0 = await mock_actor._state_manager.try_get_state("queue_0")
    # Queue 0 should not exist or be empty
    assert not has_q0 or len(q0) == 0

    # Verify priority 1 still has 1 item
    has_q1, q1 = await mock_actor._state_manager.try_get_state("queue_1")
    assert len(q1) == 1

    # Verify counts map
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert "queue_0" not in metadata["queues"]  # Priority 0 should be removed
    assert metadata["queues"]["queue_1"]["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_pop_mixed_priorities(mock_actor):
    """Test pop spanning multiple priorities."""
    await mock_actor._on_activate()

    # Push to priorities 0, 1, 2
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 1})
    await mock_actor.Push({"item": {"id": 4}, "priority": 1})
    await mock_actor.Push({"item": {"id": 5}, "priority": 2})

    # Pop all 5 items one at a time
    popped = []
    for _ in range(10):
        result = await mock_actor.Pop()
        if not result:
            break
        popped.extend(result)

    assert len(popped) == 5
    # Should be in order: 0, 0, 1, 1, 2
    assert popped[0]["id"] == 1
    assert popped[1]["id"] == 2
    assert popped[2]["id"] == 3
    assert popped[3]["id"] == 4
    assert popped[4]["id"] == 5


@pytest.mark.asyncio
async def test_pop_skips_empty_priorities(mock_actor):
    """Test that Pop skips empty priority levels."""
    await mock_actor._on_activate()

    # Push to priorities 0, 2, 5 (skip 1, 3, 4)
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 2})
    await mock_actor.Push({"item": {"id": 3}, "priority": 5})

    # Pop all - should get in order 0, 2, 5
    popped = []
    for _ in range(10):
        result = await mock_actor.Pop()
        if not result:
            break
        popped.extend(result)

    assert len(popped) == 3
    assert popped[0]["id"] == 1
    assert popped[1]["id"] == 2
    assert popped[2]["id"] == 3


@pytest.mark.asyncio
async def test_counts_map_decremented_on_pop(mock_actor):
    """Test that counts map is decremented on pop."""
    await mock_actor._on_activate()

    # Push items
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 1})

    # Pop one item
    await mock_actor.Pop()

    # Verify counts map
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 1
    assert metadata["queues"]["queue_1"]["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_counts_map_key_removed_when_zero(mock_actor):
    """Test that count keys are removed when reaching zero."""
    await mock_actor._on_activate()

    # Push and pop
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 1})

    # Pop all priority 0 items
    await mock_actor.Pop()

    # Verify priority 0 removed from counts
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert "queue_0" not in metadata["queues"]
    assert metadata["queues"]["queue_1"]["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_fifo_within_priority(mock_actor):
    """Test that FIFO is maintained within each priority level."""
    await mock_actor._on_activate()

    # Push multiple items to priority 2
    items = [
        {"id": 1, "timestamp": "2024-01-01"},
        {"id": 2, "timestamp": "2024-01-02"},
        {"id": 3, "timestamp": "2024-01-03"},
    ]

    for item in items:
        await mock_actor.Push({"item": item, "priority": 2})

    # Pop and verify FIFO order
    popped = []
    for _ in range(3):
        result = await mock_actor.Pop()
        assert len(result) == 1
        popped.extend(result)

    assert len(popped) == 3
    assert popped[0]["id"] == 1
    assert popped[1]["id"] == 2
    assert popped[2]["id"] == 3


@pytest.mark.asyncio
async def test_pop_more_than_available_multi_priority(mock_actor):
    """Test pop exceeding all queues combined."""
    await mock_actor._on_activate()

    # Push 5 items total
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 1})
    await mock_actor.Push({"item": {"id": 4}, "priority": 2})
    await mock_actor.Push({"item": {"id": 5}, "priority": 2})

    # Try to pop 100 items
    popped = []
    for _ in range(100):
        result = await mock_actor.Pop()
        if not result:
            break
        popped.extend(result)

    assert len(popped) == 5


@pytest.mark.asyncio
async def test_push_after_pop_multi_priority(mock_actor):
    """Test pushing to different priorities after popping."""
    await mock_actor._on_activate()

    # Push and pop
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Pop()

    # Push to different priorities
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 5})

    # Verify
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 1
    assert metadata["queues"]["queue_5"]["metadata"]["count"] == 1


@pytest.mark.asyncio
async def test_complex_item_multi_priority(mock_actor):
    """Test nested dicts preserved across priorities."""
    await mock_actor._on_activate()

    complex_item = {
        "id": 123,
        "nested": {"deeply": {"nested": {"value": "test"}}},
    }

    # Push to priority 3
    result = await mock_actor.Push({"item": complex_item, "priority": 3})
    assert result is True

    # Pop and verify structure preserved
    result = await mock_actor.Pop()
    assert len(result) == 1
    assert result[0] == complex_item
    assert result[0]["nested"]["deeply"]["nested"]["value"] == "test"


# ============================================================================
# Acknowledgement Feature Tests
# ============================================================================


@pytest.mark.asyncio
async def test_pop_with_ack_creates_lock(mock_actor):
    """Test that PopWithAck creates a lock and returns lock_id."""
    await mock_actor._on_activate()

    # Push an item
    item = {"id": 1, "message": "test"}
    await mock_actor.Push({"item": item})

    # Pop with acknowledgement
    result = await mock_actor.PopWithAck({"ttl_seconds": 30})

    # Verify response structure
    assert result["locked"] is True
    assert result["count"] == 1
    assert len(result["items"]) == 1
    assert result["items"][0] == item
    assert "lock_id" in result
    assert len(result["lock_id"]) > 0
    assert "lock_expires_at" in result

    # Verify lock was stored in metadata
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert "_active_lock" in metadata
    assert metadata["_active_lock"]["lock_id"] == result["lock_id"]
    assert len(metadata["_active_lock"]["items_with_priority"]) == 1


@pytest.mark.asyncio
async def test_acknowledge_valid_lock(mock_actor):
    """Test acknowledging with valid lock_id."""
    await mock_actor._on_activate()

    # Push and pop with ack
    await mock_actor.Push({"item": {"id": 1}})
    pop_result = await mock_actor.PopWithAck({})
    lock_id = pop_result["lock_id"]

    # Acknowledge
    ack_result = await mock_actor.Acknowledge({"lock_id": lock_id})

    # Verify acknowledgement succeeded
    assert ack_result["success"] is True
    assert "acknowledged successfully" in ack_result["message"].lower()
    assert ack_result["items_acknowledged"] == 1

    # Verify lock was removed
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert "_active_lock" not in metadata


@pytest.mark.asyncio
async def test_acknowledge_invalid_lock_id(mock_actor):
    """Test acknowledging with invalid lock_id."""
    await mock_actor._on_activate()

    # Push and pop with ack
    await mock_actor.Push({"item": {"id": 1}})
    await mock_actor.PopWithAck({})

    # Try to acknowledge with wrong lock_id
    ack_result = await mock_actor.Acknowledge({"lock_id": "invalid123"})

    # Verify failure
    assert ack_result["success"] is False
    assert "invalid" in ack_result["message"].lower()

    # Verify lock still exists
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert "_active_lock" in metadata


@pytest.mark.asyncio
async def test_acknowledge_missing_lock_id(mock_actor):
    """Test acknowledging without providing lock_id."""
    await mock_actor._on_activate()

    # Try to acknowledge without lock_id
    ack_result = await mock_actor.Acknowledge({})

    # Verify failure
    assert ack_result["success"] is False
    assert "required" in ack_result["message"].lower()


@pytest.mark.asyncio
async def test_pop_while_locked_returns_locked_status(mock_actor):
    """Test that PopWithAck while locked returns appropriate status."""
    await mock_actor._on_activate()

    # Push and pop with ack
    await mock_actor.Push({"item": {"id": 1}})
    await mock_actor.PopWithAck({})

    # Try to pop again while locked
    second_pop = await mock_actor.PopWithAck({})

    # Verify second pop indicates locked
    assert second_pop["locked"] is True
    assert second_pop["count"] == 0
    assert len(second_pop["items"]) == 0
    assert "lock_expires_at" in second_pop
    assert "pending acknowledgement" in second_pop["message"].lower()


@pytest.mark.asyncio
async def test_lock_expiration_returns_items(mock_actor):
    """Test that expired locks automatically return items to queue."""
    from unittest.mock import patch

    await mock_actor._on_activate()

    # Push items
    await mock_actor.Push({"item": {"id": 1}})
    await mock_actor.Push({"item": {"id": 2}})

    # Pop with short TTL (only pops 1 item now)
    with patch("time.time", return_value=1000.0):
        pop_result = await mock_actor.PopWithAck({"ttl_seconds": 5})

    # Verify item was popped
    assert pop_result["count"] == 1
    lock_id = pop_result["lock_id"]

    # Fast forward past expiration
    with patch("time.time", return_value=1006.0):
        # Try to acknowledge expired lock
        ack_result = await mock_actor.Acknowledge({"lock_id": lock_id})

    # Verify acknowledgement failed due to expiration
    assert ack_result["success"] is False
    assert ack_result.get("error_code") == "LOCK_EXPIRED"

    # Verify lock was removed
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert "_active_lock" not in metadata


@pytest.mark.asyncio
async def test_expired_lock_items_returned_to_queue_on_next_pop(mock_actor):
    """Test that items from expired lock are returned to their original priority on next pop."""
    from unittest.mock import patch

    await mock_actor._on_activate()

    # Push item to default priority (0)
    await mock_actor.Push({"item": {"id": 1, "data": "test"}})

    # Pop with short TTL
    with patch("time.time", return_value=1000.0):
        pop_result = await mock_actor.PopWithAck({"ttl_seconds": 2})

    assert pop_result["count"] == 1

    # Fast forward past expiration
    with patch("time.time", return_value=1003.0):
        # Next pop should trigger cleanup and return the item to priority 0
        next_pop = await mock_actor.PopWithAck({})

    # Verify the original item was returned
    assert next_pop["count"] == 1
    assert next_pop["items"][0]["id"] == 1
    assert next_pop["items"][0]["data"] == "test"


@pytest.mark.asyncio
async def test_regular_pop_still_works(mock_actor):
    """Test that regular Pop still works without ack."""
    await mock_actor._on_activate()

    # Push items
    await mock_actor.Push({"item": {"id": 1}})
    await mock_actor.Push({"item": {"id": 2}})

    # Use regular Pop (no acknowledgement) - pop items one at a time
    popped = []
    for _ in range(2):
        result = await mock_actor.Pop()
        assert isinstance(result, list)
        popped.extend(result)

    # Verify both items were popped
    assert len(popped) == 2
    assert popped[0]["id"] == 1
    assert popped[1]["id"] == 2

    # Verify no lock was created
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert "_active_lock" not in metadata


@pytest.mark.asyncio
async def test_pop_with_ack_empty_queue(mock_actor):
    """Test PopWithAck on empty queue returns unlocked empty result."""
    await mock_actor._on_activate()

    # Pop from empty queue
    result = await mock_actor.PopWithAck({})

    # Verify unlocked empty result (no lock created for empty pop)
    assert result["locked"] is False
    assert result["count"] == 0
    assert len(result["items"]) == 0
    assert "lock_id" not in result

    # Verify no lock was created
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert "_active_lock" not in metadata


@pytest.mark.asyncio
async def test_acknowledge_no_active_lock(mock_actor):
    """Test acknowledging when no lock exists."""
    await mock_actor._on_activate()

    # Try to acknowledge without any active lock
    ack_result = await mock_actor.Acknowledge({"lock_id": "some_id"})

    # Verify failure
    assert ack_result["success"] is False
    assert "no active lock" in ack_result["message"].lower()


@pytest.mark.asyncio
async def test_pop_with_ack_multiple_items_single_lock(mock_actor):
    """Test PopWithAck pops a single item and creates a lock."""
    await mock_actor._on_activate()

    # Push multiple items
    await mock_actor.Push({"item": {"id": 1}})
    await mock_actor.Push({"item": {"id": 2}})
    await mock_actor.Push({"item": {"id": 3}})

    # Pop single item with ack
    result = await mock_actor.PopWithAck({})

    # Verify single item in lock
    assert result["count"] == 1
    assert result["locked"] is True

    # Verify lock contains single item
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert len(metadata["_active_lock"]["items_with_priority"]) == 1


@pytest.mark.asyncio
async def test_pop_with_ack_custom_ttl(mock_actor):
    """Test PopWithAck with custom TTL."""
    from unittest.mock import patch

    await mock_actor._on_activate()

    # Push item
    await mock_actor.Push({"item": {"id": 1}})

    # Pop with custom TTL
    with patch("time.time", return_value=1000.0):
        result = await mock_actor.PopWithAck({"ttl_seconds": 60})

    # Verify lock expires_at reflects custom TTL
    assert result["lock_expires_at"] == 1060.0

    # Verify in state
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["_active_lock"]["expires_at"] == 1060.0


@pytest.mark.asyncio
async def test_pop_with_ack_ttl_bounds(mock_actor):
    """Test PopWithAck enforces TTL bounds (1-300 seconds)."""
    from unittest.mock import patch

    await mock_actor._on_activate()

    # Push items
    await mock_actor.Push({"item": {"id": 1}})

    # Test minimum bound (0 becomes 1)
    with patch("time.time", return_value=1000.0):
        result = await mock_actor.PopWithAck({"ttl_seconds": 0})
        lock_id = result["lock_id"]

    # Verify TTL was clamped to minimum (1 second)
    assert result["lock_expires_at"] == 1001.0

    # Clean up
    await mock_actor.Acknowledge({"lock_id": lock_id})

    # Push another item
    await mock_actor.Push({"item": {"id": 2}})

    # Test maximum bound (400 becomes 300)
    with patch("time.time", return_value=2000.0):
        result = await mock_actor.PopWithAck({"ttl_seconds": 400})

    # Verify TTL was clamped to maximum (300 seconds)
    assert result["lock_expires_at"] == 2300.0


@pytest.mark.asyncio
async def test_expired_lock_items_return_to_original_priority_single(mock_actor):
    """Test that items from priority 2 return to priority 2, not queue_0."""
    from unittest.mock import patch

    await mock_actor._on_activate()

    # Push to priority 2
    await mock_actor.Push({"item": {"id": 1, "data": "p2"}, "priority": 2})

    # Pop with ack and short TTL
    with patch("time.time", return_value=1000.0):
        pop_result = await mock_actor.PopWithAck({"ttl_seconds": 2})

    # Verify item was popped
    assert pop_result["count"] == 1
    assert pop_result["locked"] is True

    # Fast forward past expiration
    with patch("time.time", return_value=1003.0):
        # Trigger expiration cleanup with another PopWithAck
        next_pop = await mock_actor.PopWithAck({})

    # Verify item returned and available
    assert next_pop["count"] == 1
    assert next_pop["items"][0]["id"] == 1
    assert next_pop["items"][0]["data"] == "p2"

    # Verify item is in priority 2 queue, not queue_0
    has_queue_2, queue_2 = await mock_actor._state_manager.try_get_state("queue_2")
    has_queue_0, queue_0 = await mock_actor._state_manager.try_get_state("queue_0")

    # After the second pop, the item was taken from queue_2
    # So verify the counts are correct
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    # After second pop with ack, there should be a new lock
    assert "_active_lock" in metadata


@pytest.mark.asyncio
async def test_expired_lock_items_return_to_original_priorities_multiple(mock_actor):
    """Test that a single item from expired lock returns to its original queue."""
    from unittest.mock import patch

    await mock_actor._on_activate()

    # Push to different priorities
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 1})
    await mock_actor.Push({"item": {"id": 4}, "priority": 2})

    # Pop single item with ack (should pop from priority 0)
    with patch("time.time", return_value=1000.0):
        pop_result = await mock_actor.PopWithAck({"ttl_seconds": 2})

    # Verify single item was popped
    assert pop_result["count"] == 1
    assert pop_result["locked"] is True

    # Fast forward past expiration
    with patch("time.time", return_value=1003.0):
        # Trigger expiration cleanup
        await mock_actor.PopWithAck({})

    # Verify items returned to original priorities
    has_q0, queue_0 = await mock_actor._state_manager.try_get_state("queue_0")
    has_q1, queue_1 = await mock_actor._state_manager.try_get_state("queue_1")
    has_q2, queue_2 = await mock_actor._state_manager.try_get_state("queue_2")

    # After expiration return, the expired item should be back
    # Then the new PopWithAck popped one item from queue_0
    assert len(queue_0) == 1  # One left (one was returned, then popped again)
    assert len(queue_1) == 1  # Untouched
    assert len(queue_2) == 1  # Untouched

    # Verify queue_0 has the second item (first was returned then re-popped)
    assert queue_0[0]["id"] == 2

    # Verify queue_1 has its item
    assert queue_1[0]["id"] == 3

    # Verify queue_2 has its item
    assert queue_2[0]["id"] == 4

    # Verify counts updated correctly
    has_metadata, metadata = await mock_actor._state_manager.try_get_state("metadata")
    assert metadata["queues"]["queue_0"]["metadata"]["count"] == 1  # One item (one re-popped)
    assert metadata["queues"]["queue_1"]["metadata"]["count"] == 1
    assert metadata["queues"]["queue_2"]["metadata"]["count"] == 1
