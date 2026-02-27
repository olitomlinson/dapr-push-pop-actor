"""
Base user class for all load test scenarios.

Provides common functionality:
- Custom timing instrumentation with perf_counter
- Queue depth tracking
- Custom metrics for push/pop operations
- Response handling and error reporting
"""

import time
import random
import string
from typing import Dict, Any, Optional
from locust import HttpUser, task, between, events


class BasePushPopUser(HttpUser):
    """
    Base class for push-pop-actor load tests.

    All scenario-specific users should inherit from this class to get
    consistent timing, metrics, and helper methods.
    """

    # Default wait time between tasks (can be overridden in subclasses)
    wait_time = between(1, 3)

    # Abstract host - will be set by Locust CLI or environment
    abstract = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Track queue depth estimates (approximate)
        self.queue_depth_estimate = {}

        # Default queue ID for simple scenarios
        self.queue_id = self._generate_queue_id()

    def _generate_queue_id(self, prefix: str = "load-test") -> str:
        """Generate a unique queue ID for this user."""
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"{prefix}-{random_suffix}"

    def _generate_test_item(self, size: str = "small") -> Dict[str, Any]:
        """
        Generate a test item with varying sizes.

        Args:
            size: "small", "medium", or "large"

        Returns:
            Dictionary representing a queue item
        """
        base_item = {
            "timestamp": time.time(),
            "test_run": "load_test",
            "user_id": self.queue_id,
        }

        if size == "small":
            # ~100 bytes
            base_item["data"] = "x" * 50
        elif size == "medium":
            # ~1KB
            base_item["data"] = "x" * 900
            base_item["extra_fields"] = {f"field_{i}": f"value_{i}" for i in range(10)}
        elif size == "large":
            # ~10KB
            base_item["data"] = "x" * 9000
            base_item["extra_fields"] = {f"field_{i}": f"value_{i}" for i in range(50)}

        return base_item

    def push_item(
        self,
        queue_id: Optional[str] = None,
        item: Optional[Dict[str, Any]] = None,
        priority: int = 0,
        name: Optional[str] = None
    ) -> bool:
        """
        Push an item to a queue with custom timing.

        Args:
            queue_id: Queue ID (defaults to self.queue_id)
            item: Item to push (generates default if None)
            priority: Priority level (0 = highest)
            name: Custom name for metrics (defaults to "push")

        Returns:
            True if successful, False otherwise
        """
        queue_id = queue_id or self.queue_id
        item = item or self._generate_test_item()
        name = name or f"push_queue_{queue_id}"

        payload = {
            "item": item,
            "priority": priority
        }

        # High-resolution timing
        start_time = time.perf_counter()

        try:
            with self.client.post(
                f"/queue/{queue_id}/push",
                json=payload,
                catch_response=True,
                name=name
            ) as response:
                duration_ms = (time.perf_counter() - start_time) * 1000

                if response.status_code == 200:
                    # Track queue depth estimate
                    self.queue_depth_estimate[queue_id] = \
                        self.queue_depth_estimate.get(queue_id, 0) + 1

                    response.success()
                    return True
                else:
                    response.failure(f"Push failed: {response.status_code} - {response.text}")
                    return False

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            # Fire custom event for exception tracking
            self.environment.events.request.fire(
                request_type="POST",
                name=name,
                response_time=duration_ms,
                response_length=0,
                exception=e
            )
            return False

    def pop_items(
        self,
        queue_id: Optional[str] = None,
        depth: int = 1,
        name: Optional[str] = None
    ) -> list:
        """
        Pop items from a queue with custom timing.

        Args:
            queue_id: Queue ID (defaults to self.queue_id)
            depth: Number of items to pop
            name: Custom name for metrics (defaults to "pop")

        Returns:
            List of popped items (empty list on failure)
        """
        queue_id = queue_id or self.queue_id
        name = name or f"pop_queue_{queue_id}_depth_{depth}"

        # High-resolution timing
        start_time = time.perf_counter()

        try:
            with self.client.post(
                f"/queue/{queue_id}/pop",
                params={"depth": depth},
                catch_response=True,
                name=name
            ) as response:
                duration_ms = (time.perf_counter() - start_time) * 1000

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    count = data.get("count", 0)

                    # Update queue depth estimate
                    self.queue_depth_estimate[queue_id] = \
                        max(0, self.queue_depth_estimate.get(queue_id, 0) - count)

                    response.success()
                    return items
                else:
                    response.failure(f"Pop failed: {response.status_code} - {response.text}")
                    return []

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            # Fire custom event for exception tracking
            self.environment.events.request.fire(
                request_type="POST",
                name=name,
                response_time=duration_ms,
                response_length=0,
                exception=e
            )
            return []

    def get_queue_depth_estimate(self, queue_id: Optional[str] = None) -> int:
        """
        Get the estimated queue depth for a queue.

        Note: This is an estimate based on push/pop operations during the test.
        It may not reflect the actual queue depth if other processes are
        modifying the queue.

        Args:
            queue_id: Queue ID (defaults to self.queue_id)

        Returns:
            Estimated queue depth
        """
        queue_id = queue_id or self.queue_id
        return self.queue_depth_estimate.get(queue_id, 0)


# Event handlers for custom metrics reporting
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Log test start."""
    print(f"\n=== Load test starting ===")
    print(f"Host: {environment.host}")
    print(f"Users: {environment.runner.target_user_count if environment.runner else 'N/A'}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log test completion."""
    print(f"\n=== Load test completed ===")
    if environment.runner and hasattr(environment.runner, 'stats'):
        stats = environment.runner.stats
        print(f"Total requests: {stats.total.num_requests}")
        print(f"Total failures: {stats.total.num_failures}")
        print(f"Average response time: {stats.total.avg_response_time:.2f}ms")
        print(f"p95 response time: {stats.total.get_response_time_percentile(0.95):.2f}ms")
