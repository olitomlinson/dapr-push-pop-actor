"""
Unit tests for PushPopActor.

These tests mock the Dapr state manager to avoid requiring a running Dapr runtime.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock

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
    """Test that actor activation initializes empty queue_counts map."""
    await mock_actor._on_activate()

    # Check that queue_counts was initialized
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert has_counts is True
    assert counts == {}


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
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 1


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
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 3


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
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts == {}


@pytest.mark.asyncio
async def test_pop_from_empty_queue(mock_actor):
    """Test popping from an empty queue returns empty list."""
    await mock_actor._on_activate()

    result = await mock_actor.Pop(5)
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
    result = await mock_actor.Pop(1)
    assert len(result) == 1
    assert result[0] == items[0]

    # Verify remaining items in queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert len(queue) == 2
    assert queue == items[1:]

    # Verify counts map was updated
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 2


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

    # Pop three items
    result = await mock_actor.Pop(3)
    assert len(result) == 3
    assert result == items[:3]

    # Verify remaining items in queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert len(queue) == 2
    assert queue == items[3:]

    # Verify counts map was updated
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 2


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

    # Try to pop 10 items (more than available)
    result = await mock_actor.Pop(10)
    assert len(result) == 2
    assert result == items

    # Verify queue_0 was not saved (empty queue cleanup)
    # Note: Our implementation doesn't save empty queues
    # Verify counts map is empty
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts == {}


@pytest.mark.asyncio
async def test_pop_with_zero_depth(mock_actor):
    """Test that popping with depth=0 returns empty list."""
    await mock_actor._on_activate()

    # Push items
    await mock_actor.Push({"item": {"id": 1, "message": "test"}})

    # Pop with depth 0
    result = await mock_actor.Pop(0)
    assert result == []

    # Verify item is still in queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert len(queue) == 1

    # Verify counts map unchanged
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 1


@pytest.mark.asyncio
async def test_pop_with_negative_depth(mock_actor):
    """Test that popping with negative depth returns empty list."""
    await mock_actor._on_activate()

    # Push items
    await mock_actor.Push({"item": {"id": 1, "message": "test"}})

    # Pop with negative depth
    result = await mock_actor.Pop(-5)
    assert result == []

    # Verify item is still in queue_0
    has_queue, queue = await mock_actor._state_manager.try_get_state("queue_0")
    assert len(queue) == 1

    # Verify counts map unchanged
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 1


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
        result = await mock_actor.Pop(1)
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
    result = await mock_actor.Pop(1)
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
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 2


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
    result = await mock_actor.Pop(1)
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
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 1


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
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["5"] == 1


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
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 1


@pytest.mark.asyncio
async def test_push_invalid_priority_negative(mock_actor):
    """Test that negative priority is rejected."""
    await mock_actor._on_activate()

    item = {"id": 1, "message": "test"}
    result = await mock_actor.Push({"item": item, "priority": -1})

    assert result is False

    # Verify no queues created
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts == {}


@pytest.mark.asyncio
async def test_push_invalid_priority_non_int(mock_actor):
    """Test that non-integer priority is rejected."""
    await mock_actor._on_activate()

    item = {"id": 1, "message": "test"}
    result = await mock_actor.Push({"item": item, "priority": "high"})

    assert result is False

    # Verify no queues created
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts == {}


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
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 2
    assert counts["1"] == 1
    assert counts["5"] == 1


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
    result = await mock_actor.Pop(1)
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

    # Pop 4 items - should drain all priority 0, then 1 from priority 1
    result = await mock_actor.Pop(4)
    assert len(result) == 4
    assert result[0]["p"] == 0
    assert result[1]["p"] == 0
    assert result[2]["p"] == 0
    assert result[3]["p"] == 1

    # Verify priority 0 is empty
    has_q0, q0 = await mock_actor._state_manager.try_get_state("queue_0")
    # Queue 0 should not exist or be empty
    assert not has_q0 or len(q0) == 0

    # Verify priority 1 still has 1 item
    has_q1, q1 = await mock_actor._state_manager.try_get_state("queue_1")
    assert len(q1) == 1

    # Verify counts map
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert "0" not in counts  # Priority 0 should be removed
    assert counts["1"] == 1


@pytest.mark.asyncio
async def test_pop_mixed_priorities(mock_actor):
    """Test pop depth spanning multiple priorities."""
    await mock_actor._on_activate()

    # Push to priorities 0, 1, 2
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 1})
    await mock_actor.Push({"item": {"id": 4}, "priority": 1})
    await mock_actor.Push({"item": {"id": 5}, "priority": 2})

    # Pop all 5 items
    result = await mock_actor.Pop(10)
    assert len(result) == 5
    # Should be in order: 0, 0, 1, 1, 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2
    assert result[2]["id"] == 3
    assert result[3]["id"] == 4
    assert result[4]["id"] == 5


@pytest.mark.asyncio
async def test_pop_skips_empty_priorities(mock_actor):
    """Test that Pop skips empty priority levels."""
    await mock_actor._on_activate()

    # Push to priorities 0, 2, 5 (skip 1, 3, 4)
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 2})
    await mock_actor.Push({"item": {"id": 3}, "priority": 5})

    # Pop all - should get in order 0, 2, 5
    result = await mock_actor.Pop(10)
    assert len(result) == 3
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2
    assert result[2]["id"] == 3


@pytest.mark.asyncio
async def test_counts_map_decremented_on_pop(mock_actor):
    """Test that counts map is decremented on pop."""
    await mock_actor._on_activate()

    # Push items
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 1})

    # Pop one item
    await mock_actor.Pop(1)

    # Verify counts map
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 1
    assert counts["1"] == 1


@pytest.mark.asyncio
async def test_counts_map_key_removed_when_zero(mock_actor):
    """Test that count keys are removed when reaching zero."""
    await mock_actor._on_activate()

    # Push and pop
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 1})

    # Pop all priority 0 items
    await mock_actor.Pop(1)

    # Verify priority 0 removed from counts
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert "0" not in counts
    assert counts["1"] == 1


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
    result = await mock_actor.Pop(3)
    assert len(result) == 3
    assert result[0]["id"] == 1
    assert result[1]["id"] == 2
    assert result[2]["id"] == 3


@pytest.mark.asyncio
async def test_pop_more_than_available_multi_priority(mock_actor):
    """Test pop depth exceeding all queues combined."""
    await mock_actor._on_activate()

    # Push 5 items total
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 1})
    await mock_actor.Push({"item": {"id": 4}, "priority": 2})
    await mock_actor.Push({"item": {"id": 5}, "priority": 2})

    # Try to pop 100 items
    result = await mock_actor.Pop(100)
    assert len(result) == 5


@pytest.mark.asyncio
async def test_push_after_pop_multi_priority(mock_actor):
    """Test pushing to different priorities after popping."""
    await mock_actor._on_activate()

    # Push and pop
    await mock_actor.Push({"item": {"id": 1}, "priority": 0})
    await mock_actor.Pop(1)

    # Push to different priorities
    await mock_actor.Push({"item": {"id": 2}, "priority": 0})
    await mock_actor.Push({"item": {"id": 3}, "priority": 5})

    # Verify
    has_counts, counts = await mock_actor._state_manager.try_get_state("queue_counts")
    assert counts["0"] == 1
    assert counts["5"] == 1


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
    result = await mock_actor.Pop(1)
    assert len(result) == 1
    assert result[0] == complex_item
    assert result[0]["nested"]["deeply"]["nested"]["value"] == "test"
