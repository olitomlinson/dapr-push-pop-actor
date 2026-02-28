"""
S3: Mixed Push/Pop Workload (Producer-Consumer Pattern)

This is the most important scenario for realistic performance testing.
It simulates steady-state producer-consumer patterns where items are
being pushed and popped concurrently.

Variants:
- S3a: Balanced (50% push, 50% pop)
- S3b: Producer-heavy (80% push, 20% pop)
- S3c: Consumer-heavy (20% push, 80% pop)

Expected behavior:
- Balanced: Queue depth should remain relatively stable
- Producer-heavy: Queue depth should grow
- Consumer-heavy: Queue depth should shrink (may reach empty)
"""

import random
from locust import task, between
from scenarios.base import BasePushPopUser


class MixedWorkloadUser(BasePushPopUser):
    """
    S3a: Balanced mixed workload (50% push, 50% pop).

    This is the default mixed scenario representing a steady-state
    system where production and consumption are balanced.

    Target: 50 RPS total (25 push/s + 25 pop/s)
    """

    wait_time = between(0.5, 1.5)  # Average 1s between requests = ~1 RPS per user

    def on_start(self):
        """Initialize by pushing some items to ensure queue isn't empty."""
        print(f"User {self.queue_id} starting - pre-populating queue")

        # Push 10 items to start with
        for i in range(10):
            self.push_item(priority=0)

    @task(50)
    def push_operation(self):
        """Push a single item with priority 0 (50% weight)."""
        item = self._generate_test_item(size="small")
        self.push_item(item=item, priority=0)

    @task(50)
    def pop_operation(self):
        """Pop a single item (50% weight)."""
        items = self.pop_items()

        # Track empty queue occurrences
        if not items:
            # Queue is empty - this is fine in balanced load
            pass


class ProducerHeavyUser(BasePushPopUser):
    """
    S3b: Producer-heavy workload (80% push, 20% pop).

    Simulates a system where items are produced faster than consumed.
    Queue depth should grow over time.

    Target: 100 RPS total (80 push/s + 20 pop/s)
    """

    wait_time = between(0.3, 0.7)  # Faster rate for higher throughput

    def on_start(self):
        """Initialize with minimal pre-population."""
        print(f"Producer-heavy user {self.queue_id} starting")

        # Push 5 items to start
        for i in range(5):
            self.push_item(priority=0)

    @task(80)
    def push_operation(self):
        """Push items (80% weight)."""
        item = self._generate_test_item(size="small")
        self.push_item(item=item, priority=0)

    @task(20)
    def pop_operation(self):
        """Pop items less frequently (20% weight)."""
        # Pop single item per call
        items = self.pop_items()


class ConsumerHeavyUser(BasePushPopUser):
    """
    S3c: Consumer-heavy workload (20% push, 80% pop).

    Simulates a system where items are consumed faster than produced.
    Queue depth should shrink, potentially reaching empty state.

    Target: 100 RPS total (20 push/s + 80 pop/s)
    """

    wait_time = between(0.3, 0.7)  # Faster rate for higher throughput

    def on_start(self):
        """Initialize with significant pre-population to avoid immediate empty."""
        print(f"Consumer-heavy user {self.queue_id} starting - pre-populating")

        # Push 50 items to start with to handle initial consumption
        for i in range(50):
            self.push_item(priority=0)

    @task(20)
    def push_operation(self):
        """Push items less frequently (20% weight)."""
        item = self._generate_test_item(size="small")
        self.push_item(item=item, priority=0)

    @task(80)
    def pop_operation(self):
        """Pop items frequently (80% weight)."""
        # Pop single items for more granular consumption
        items = self.pop_items()

        # Track empty queue - expected in consumer-heavy scenario
        if not items:
            # Queue is empty - might want to back off
            pass


class MultiPriorityMixedUser(BasePushPopUser):
    """
    S3d: Mixed workload with multiple priorities.

    Tests performance when using the priority queue features.
    Items are pushed with random priorities 0-4, and popped in order.

    Target: 50 RPS total (balanced push/pop)
    """

    wait_time = between(0.5, 1.5)

    def on_start(self):
        """Initialize with mixed priority items."""
        print(f"Multi-priority user {self.queue_id} starting")

        # Push 20 items with various priorities
        for i in range(20):
            priority = random.randint(0, 4)
            self.push_item(priority=priority)

    @task(50)
    def push_with_random_priority(self):
        """Push items with random priority (0-4)."""
        item = self._generate_test_item(size="small")
        priority = random.randint(0, 4)
        self.push_item(item=item, priority=priority)

    @task(50)
    def pop_by_priority(self):
        """Pop items (will get priority 0 first, then 1, etc.)."""
        items = self.pop_items()


class BalancedLargeItemsUser(BasePushPopUser):
    """
    S3e: Balanced workload with larger items.

    Tests performance impact of larger payloads on serialization and
    database storage.

    Target: 50 RPS total (balanced push/pop)
    """

    wait_time = between(0.5, 1.5)

    def on_start(self):
        """Initialize with medium-sized items."""
        print(f"Large items user {self.queue_id} starting")

        for i in range(10):
            item = self._generate_test_item(size="medium")
            self.push_item(item=item, priority=0)

    @task(50)
    def push_medium_item(self):
        """Push medium-sized items (~1KB)."""
        item = self._generate_test_item(size="medium")
        self.push_item(item=item, priority=0)

    @task(40)
    def push_large_item(self):
        """Push large items (~10KB) occasionally."""
        item = self._generate_test_item(size="large")
        self.push_item(item=item, priority=0)

    @task(50)
    def pop_items_batch(self):
        """Pop multiple items (3 individual pops)."""
        for _ in range(3):
            items = self.pop_items()
            if not items:
                break


# Export all variants
__all__ = [
    "MixedWorkloadUser",           # S3a - Most important, default
    "ProducerHeavyUser",           # S3b - Growing queue
    "ConsumerHeavyUser",           # S3c - Draining queue
    "MultiPriorityMixedUser",      # S3d - Priority testing
    "BalancedLargeItemsUser",      # S3e - Payload size testing
]
