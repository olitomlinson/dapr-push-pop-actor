"""
PushPopActor - A priority queue-based actor for storing and retrieving dictionaries.

This actor implements an N-queue priority system where:
- Push: adds a dictionary to a specific priority queue (0 = highest priority)
- Pop: removes and returns N dictionaries, draining from lowest priority index first
- Each priority level maintains FIFO ordering independently
"""
import logging
from typing import Any, Dict, List

from dapr.actor import Actor, ActorInterface, actormethod

logger = logging.getLogger(__name__)


class PushPopActorInterface(ActorInterface):
    """Interface for PushPopActor."""

    @actormethod(name="Push")
    async def Push(self, data: dict) -> bool:
        """
        Push a dictionary onto a priority queue.

        Args:
            data: Dictionary containing:
                - item (dict): The item to push onto the queue
                - priority (int, optional): Priority level (0 = highest). Default: 0

        Returns:
            bool: True if successful, False otherwise
        """
        ...

    @actormethod(name="Pop")
    async def Pop(self, depth: int) -> list:
        """
        Pop N dictionaries from the queue.

        Args:
            depth: Number of items to retrieve from the front of the queue

        Returns:
            list: Array of dictionaries (empty array if queue is empty)
        """
        ...


class PushPopActor(Actor, PushPopActorInterface):
    """Actor implementing a simple queue-based storage for dictionaries."""

    def __init__(self, ctx: Any, actor_id: Any) -> None:
        super().__init__(ctx, actor_id)
        self.actor_id = actor_id
        logger.info(f"PushPopActor initialized: {actor_id}")

    async def _on_activate(self) -> None:
        """
        Called when the actor is activated.
        Initializes the queue counts map if it doesn't exist.
        """
        logger.info(f"PushPopActor activating: {self.actor_id}")

        # Check if queue_counts exists, if not initialize it
        has_counts, _ = await self._state_manager.try_get_state("queue_counts")
        if not has_counts:
            await self._state_manager.set_state("queue_counts", {})
            await self._state_manager.save_state()
            logger.info(f"Initialized empty queue_counts map for actor {self.actor_id}")

    async def Push(self, data: Dict[str, Any]) -> bool:
        """
        Push a dictionary onto a priority queue (FIFO within priority level).

        Args:
            data: Dictionary containing:
                - item (dict): The item to push onto the queue
                - priority (int, optional): Priority level (0 = highest). Default: 0

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Extract item and priority from data
            item = data.get("item")
            priority = data.get("priority", 0)

            # Validate input is a dict
            if not isinstance(item, dict):
                logger.error(f"Push failed: item is not a dict, got {type(item)}")
                return False

            # Validate priority is non-negative integer
            if not isinstance(priority, int) or priority < 0:
                logger.error(f"Push failed: priority must be non-negative integer, got {priority}")
                return False

            # Construct queue key for this priority level
            queue_key = f"queue_{priority}"

            # Get queue for this priority level (or create empty)
            has_queue, queue = await self._state_manager.try_get_state(queue_key)
            if not has_queue:
                queue = []

            # Push item to queue (append to end)
            queue.append(item)

            # Update counts map
            has_counts, counts = await self._state_manager.try_get_state("queue_counts")
            if not has_counts:
                counts = {}

            counts[str(priority)] = counts.get(str(priority), 0) + 1

            # Save both queue and counts map
            await self._state_manager.set_state(queue_key, queue)
            await self._state_manager.set_state("queue_counts", counts)
            await self._state_manager.save_state()

            logger.info(f"Pushed item to priority {priority} queue for actor {self.actor_id}. Queue size: {len(queue)}, Total counts: {counts}")
            return True

        except Exception as e:
            logger.error(f"Error in Push for actor {self.actor_id}: {e}", exc_info=True)
            return False

    async def Pop(self, depth: int) -> List[Dict[str, Any]]:
        """
        Pop N dictionaries from priority queues (FIFO within each priority, lowest priority index first).

        Drains from priority 0, then 1, then 2, etc., until depth is satisfied.

        Args:
            depth: Number of items to retrieve

        Returns:
            list: Array of dictionaries (empty array if no items available)
        """
        try:
            # Validate depth is positive
            if depth <= 0:
                logger.warning(f"Pop called with non-positive depth {depth} for actor {self.actor_id}")
                return []

            # Load queue_counts map
            has_counts, counts = await self._state_manager.try_get_state("queue_counts")
            if not has_counts or not counts:
                logger.info(f"Pop called but no queues have items for actor {self.actor_id}")
                return []

            # Sort priority keys numerically (0, 1, 2, ...)
            priority_keys = sorted([int(k) for k in counts.keys()])

            result = []
            remaining_depth = depth

            # Process each priority level in order
            for priority in priority_keys:
                if remaining_depth == 0:
                    break

                count = counts.get(str(priority), 0)
                if count == 0:
                    continue

                # Load queue for this priority
                queue_key = f"queue_{priority}"
                has_queue, queue = await self._state_manager.try_get_state(queue_key)

                if not has_queue or not queue:
                    # Defensive: fix count desync
                    logger.warning(f"Count desync detected for priority {priority}, fixing...")
                    if str(priority) in counts:
                        del counts[str(priority)]
                    continue

                # Calculate how many to pop from this priority
                pop_count = min(remaining_depth, len(queue))

                # Pop items from front
                popped = queue[:pop_count]
                queue = queue[pop_count:]

                # Update state
                # Always update the queue state (even if empty, for consistency)
                await self._state_manager.set_state(queue_key, queue)

                # Update counts map
                new_count = count - pop_count
                if new_count == 0:
                    del counts[str(priority)]
                else:
                    counts[str(priority)] = new_count

                # Add to result
                result.extend(popped)
                remaining_depth -= pop_count

                logger.info(f"Popped {pop_count} items from priority {priority} for actor {self.actor_id}")

            # Save updated counts map
            await self._state_manager.set_state("queue_counts", counts)
            await self._state_manager.save_state()

            logger.info(f"Popped {len(result)} total items for actor {self.actor_id}. Remaining counts: {counts}")
            return result

        except Exception as e:
            logger.error(f"Error in Pop for actor {self.actor_id}: {e}", exc_info=True)
            return []
