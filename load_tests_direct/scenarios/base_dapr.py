"""
Base user class for direct Dapr actor load test scenarios.

Provides common functionality:
- Dapr Actor SDK integration via ActorProxy
- Custom timing instrumentation with perf_counter
- Queue depth tracking
- Custom metrics for push/pop operations
- Response handling and error reporting
"""

import time
import random
import string
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional
from locust import User, task, between, events
from dapr.actor import ActorId, ActorProxy
from push_pop_actor import PushPopActorInterface


class BaseDaprActorUser(User):
    """
    Base class for push-pop-actor direct actor load tests.

    All scenario-specific users should inherit from this class to get
    consistent timing, metrics, and helper methods.

    Uses Dapr Actor SDK to invoke actors directly via gRPC.
    Uses ThreadPoolExecutor to run async code in separate threads with fresh event loops.
    """

    # Default wait time between tasks (can be overridden in subclasses)
    wait_time = between(1, 3)

    # Abstract user - will not be selectable in Locust UI
    abstract = True

    # Shared thread pool for all users
    _executor = ThreadPoolExecutor(max_workers=50)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Track queue depth estimates (approximate)
        self.queue_depth_estimate = {}

        # Default queue ID for simple scenarios
        self.queue_id = self._generate_queue_id()

        # Cache actor proxies to avoid recreating them
        self._actor_proxies = {}

    def _generate_queue_id(self, prefix: str = "load-test-direct") -> str:
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
            "test_run": "load_test_direct",
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

    def _get_or_create_proxy(self, queue_id: str):
        """Get cached proxy or create a new one for the given queue_id."""
        if queue_id not in self._actor_proxies:
            self._actor_proxies[queue_id] = ActorProxy.create(
                actor_type="PushPopActor",
                actor_id=ActorId(queue_id),
                actor_interface=PushPopActorInterface
            )
        return self._actor_proxies[queue_id]

    def push_item(
        self,
        queue_id: Optional[str] = None,
        item: Optional[Dict[str, Any]] = None,
        priority: int = 0,
        name: Optional[str] = None
    ) -> bool:
        """Synchronous wrapper using ThreadPoolExecutor with fresh event loop."""
        def run_in_thread():
            # Create new loop without setting it as current to avoid conflicts with gevent
            loop = asyncio.new_event_loop()
            coro = None
            try:
                coro = self._push_item_async(queue_id, item, priority, name)
                return loop.run_until_complete(coro)
            except Exception:
                # If exception occurs, close the coroutine to avoid warning
                if coro is not None:
                    coro.close()
                raise
            finally:
                loop.close()

        try:
            return self._executor.submit(run_in_thread).result(timeout=30)
        except Exception:
            return False

    async def _push_item_async(
        self,
        queue_id: Optional[str] = None,
        item: Optional[Dict[str, Any]] = None,
        priority: int = 0,
        name: Optional[str] = None
    ) -> bool:
        """
        Push an item to a queue using Dapr Actor SDK.

        Args:
            queue_id: Queue ID (defaults to self.queue_id)
            item: Item to push (generates default if None)
            priority: Priority level (0 = highest)
            name: Custom name for metrics (defaults to "dapr_push_queue_{id}")

        Returns:
            True if successful, False otherwise
        """
        queue_id = queue_id or self.queue_id
        item = item or self._generate_test_item()
        name = name or f"dapr_push_queue_{queue_id}"

        # High-resolution timing
        start_time = time.perf_counter()

        try:
            # Get or create cached actor proxy
            proxy = self._get_or_create_proxy(queue_id)

            # Call Push method with item and priority
            data = {"item": item, "priority": priority}
            success = await proxy.Push(data)

            duration_ms = (time.perf_counter() - start_time) * 1000

            # Fire custom event for Locust metrics
            self.environment.events.request.fire(
                request_type="ACTOR",
                name=name,
                response_time=duration_ms,
                response_length=len(str(item)),
                exception=None if success else Exception("Push returned False")
            )

            if success:
                # Track queue depth estimate
                self.queue_depth_estimate[queue_id] = \
                    self.queue_depth_estimate.get(queue_id, 0) + 1

            return success

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            # Fire custom event for exception tracking
            self.environment.events.request.fire(
                request_type="ACTOR",
                name=name,
                response_time=duration_ms,
                response_length=0,
                exception=e
            )
            return False

    def pop_items(
        self,
        queue_id: Optional[str] = None,
        name: Optional[str] = None
    ) -> list:
        """Synchronous wrapper using ThreadPoolExecutor with fresh event loop."""
        def run_in_thread():
            # Create new loop without setting it as current to avoid conflicts with gevent
            loop = asyncio.new_event_loop()
            coro = None
            try:
                coro = self._pop_items_async(queue_id, name)
                return loop.run_until_complete(coro)
            except Exception:
                # If exception occurs, close the coroutine to avoid warning
                if coro is not None:
                    coro.close()
                raise
            finally:
                loop.close()

        try:
            return self._executor.submit(run_in_thread).result(timeout=30)
        except Exception:
            return []

    async def _pop_items_async(
        self,
        queue_id: Optional[str] = None,
        name: Optional[str] = None
    ) -> list:
        """
        Pop a single item from a queue using Dapr Actor SDK.

        Args:
            queue_id: Queue ID (defaults to self.queue_id)
            name: Custom name for metrics (defaults to "dapr_pop_queue_{id}")

        Returns:
            List with single item or empty list on failure
        """
        queue_id = queue_id or self.queue_id
        name = name or f"dapr_pop_queue_{queue_id}"

        # High-resolution timing
        start_time = time.perf_counter()

        try:
            # Get or create cached actor proxy
            proxy = self._get_or_create_proxy(queue_id)

            # Call Pop method
            items = await proxy.Pop()

            duration_ms = (time.perf_counter() - start_time) * 1000

            # Fire custom event for Locust metrics
            self.environment.events.request.fire(
                request_type="ACTOR",
                name=name,
                response_time=duration_ms,
                response_length=len(str(items)),
                exception=None
            )

            # Update queue depth estimate
            if items:
                self.queue_depth_estimate[queue_id] = \
                    max(0, self.queue_depth_estimate.get(queue_id, 0) - 1)

            return items

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            # Fire custom event for exception tracking
            self.environment.events.request.fire(
                request_type="ACTOR",
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
    print(f"\n=== Direct actor load test starting ===")
    print(f"Host: {environment.host if hasattr(environment, 'host') else 'N/A'}")
    print(f"Mode: Dapr Actor SDK (gRPC)")
    print(f"Users: {environment.runner.target_user_count if environment.runner else 'N/A'}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Log test completion."""
    print(f"\n=== Direct actor load test completed ===")
    if environment.runner and hasattr(environment.runner, 'stats'):
        stats = environment.runner.stats
        print(f"Total requests: {stats.total.num_requests}")
        print(f"Total failures: {stats.total.num_failures}")
        print(f"Average response time: {stats.total.avg_response_time:.2f}ms")
        print(f"p95 response time: {stats.total.get_response_time_percentile(0.95):.2f}ms")
