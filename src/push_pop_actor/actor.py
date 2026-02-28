"""
PushPopActor - A priority queue-based actor for storing and retrieving dictionaries.

This actor implements an N-queue priority system where:
- Push: adds a dictionary to a specific priority queue (0 = highest priority)
- Pop: removes and returns a single dictionary, draining from lowest priority index first
- Each priority level maintains FIFO ordering independently
"""
import logging
import secrets
import time
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
    async def Pop(self) -> list:
        """
        Pop a single dictionary from the queue (FIFO - removed from front).

        Returns:
            list: Array with single item, or empty array if queue is empty
        """
        ...

    @actormethod(name="PopWithAck")
    async def PopWithAck(self, data: dict) -> dict:
        """
        Pop a single item with acknowledgement requirement.

        Args:
            data: Dictionary containing:
                - ttl_seconds (int, optional): Lock TTL in seconds (default: 30)

        Returns:
            dict: {
                "items": List[dict],      # List with 1 item or empty
                "count": int,              # 0 or 1
                "locked": bool,
                "lock_id": str (if locked=True),
                "lock_expires_at": float (if locked=True),
                "message": str (optional)
            }
        """
        ...

    @actormethod(name="Acknowledge")
    async def Acknowledge(self, data: dict) -> dict:
        """
        Acknowledge popped items using lock ID.

        Args:
            data: Dictionary containing:
                - lock_id (str): The lock ID to acknowledge

        Returns:
            dict: {
                "success": bool,
                "message": str,
                "items_acknowledged": int (if success=True),
                "error_code": str (optional)
            }
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

    async def Pop(self) -> List[Dict[str, Any]]:
        """
        Pop a single dictionary from priority queues (FIFO within each priority, lowest priority index first).

        Drains from priority 0, then 1, then 2, etc.

        Returns:
            list: Array with single item, or empty array if no items available
        """
        try:
            # Load queue_counts map
            has_counts, counts = await self._state_manager.try_get_state("queue_counts")
            if not has_counts or not counts:
                logger.info(f"Pop called but no queues have items for actor {self.actor_id}")
                return []

            # Sort priority keys numerically (0, 1, 2, ...), excluding _active_lock
            priority_keys = sorted([int(k) for k in counts.keys() if k != "_active_lock"])

            # Process each priority level in order
            for priority in priority_keys:
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

                # Pop single item from front
                item = queue[0]
                queue = queue[1:]

                # Update state
                await self._state_manager.set_state(queue_key, queue)

                # Update counts map
                new_count = count - 1
                if new_count == 0:
                    del counts[str(priority)]
                else:
                    counts[str(priority)] = new_count

                # Save updated counts map
                await self._state_manager.set_state("queue_counts", counts)
                await self._state_manager.save_state()

                logger.info(f"Popped 1 item from priority {priority} for actor {self.actor_id}. Remaining counts: {counts}")
                return [item]

            # No items found
            logger.info(f"Pop called but no items available for actor {self.actor_id}")
            return []

        except Exception as e:
            logger.error(f"Error in Pop for actor {self.actor_id}: {e}", exc_info=True)
            return []

    async def _return_items_to_queue(self, items_with_priority: List[dict]) -> None:
        """
        Return expired lock items to their original priority queues.

        Args:
            items_with_priority: List of {"item": dict, "priority": int}
        """
        if not items_with_priority:
            return

        try:
            # Group items by priority
            items_by_priority = {}
            for entry in items_with_priority:
                priority = entry["priority"]
                item = entry["item"]
                if priority not in items_by_priority:
                    items_by_priority[priority] = []
                items_by_priority[priority].append(item)

            # Load current counts
            has_counts, counts = await self._state_manager.try_get_state("queue_counts")
            if not has_counts:
                counts = {}

            # Return items to each priority queue
            for priority, items in items_by_priority.items():
                queue_key = f"queue_{priority}"

                # Load existing queue
                has_queue, queue = await self._state_manager.try_get_state(queue_key)
                if not has_queue:
                    queue = []

                # Prepend items to front (FIFO, they were already popped)
                queue = items + queue

                # Update counts
                current_count = int(counts.get(str(priority), 0))
                counts[str(priority)] = current_count + len(items)

                # Save queue
                await self._state_manager.set_state(queue_key, queue)

                logger.info(f"Returned {len(items)} expired lock items to queue_{priority} for actor {self.actor_id}")

            # Save updated counts
            await self._state_manager.set_state("queue_counts", counts)
            await self._state_manager.save_state()

            logger.info(f"Returned {len(items_with_priority)} total expired lock items to original priorities for actor {self.actor_id}")

        except Exception as e:
            logger.error(f"Error returning items to queue for actor {self.actor_id}: {e}", exc_info=True)

    async def PopWithAck(self, data: Dict[str, Any]) -> dict:
        """
        Pop a single item with acknowledgement requirement.

        When acknowledgements are enabled, popped items are locked until explicitly
        acknowledged or until the TTL expires. While locked, further pops will fail
        with a locked status.

        Args:
            data: Dictionary containing:
                - ttl_seconds (int, optional): Lock TTL in seconds (default: 30, max: 300)

        Returns:
            dict: {
                "items": List[dict],      # List with 1 item or empty
                "count": int,              # 0 or 1
                "locked": bool,
                "lock_id": str (if locked=True),
                "lock_expires_at": float (if locked=True),
                "message": str (optional)
            }
        """
        try:
            # 1. Check for active lock and handle expiration
            has_counts, counts = await self._state_manager.try_get_state("queue_counts")
            if has_counts and "_active_lock" in counts:
                lock = counts["_active_lock"]
                # Check if expired
                if time.time() < lock["expires_at"]:
                    # Lock still valid - return 423 info
                    logger.info(f"PopWithAck blocked: active lock exists for actor {self.actor_id}")
                    return {
                        "items": [],
                        "count": 0,
                        "locked": True,
                        "lock_expires_at": lock["expires_at"],
                        "message": "Queue is locked pending acknowledgement"
                    }
                else:
                    # Expired - return items to queue and remove lock
                    logger.info(f"Lock expired for actor {self.actor_id}, returning items to queue")
                    await self._return_items_to_queue(lock["items_with_priority"])
                    del counts["_active_lock"]
                    await self._state_manager.set_state("queue_counts", counts)
                    await self._state_manager.save_state()

            # 2. Pop single item WITH priority tracking
            items_with_priority = []

            # Reload counts after potential cleanup
            has_counts, counts = await self._state_manager.try_get_state("queue_counts")
            if not has_counts or not counts:
                logger.info(f"PopWithAck called but no queues have items for actor {self.actor_id}")
                return {"items": [], "count": 0, "locked": False}

            # Sort priority keys numerically (0, 1, 2, ...), excluding _active_lock
            priority_keys = sorted([int(k) for k in counts.keys() if k != "_active_lock"])

            # Process each priority level in order
            for priority in priority_keys:
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

                # Pop single item from front
                item = queue[0]
                queue = queue[1:]

                # Add to result WITH priority metadata
                items_with_priority.append({"item": item, "priority": priority})

                # Update state
                await self._state_manager.set_state(queue_key, queue)

                # Update counts map
                new_count = count - 1
                if new_count == 0:
                    del counts[str(priority)]
                else:
                    counts[str(priority)] = new_count

                logger.info(f"PopWithAck: popped 1 item from priority {priority} for actor {self.actor_id}")
                break  # Only pop one item

            # 3. If no items, return unlocked empty result
            if not items_with_priority:
                logger.info(f"PopWithAck: no items available for actor {self.actor_id}")
                return {"items": [], "count": 0, "locked": False}

            # 4. Create lock
            lock_id = secrets.token_urlsafe(8)  # 11 char string
            ttl = min(max(data.get("ttl_seconds", 30), 1), 300)  # 1-300 seconds
            expires_at = time.time() + ttl

            # 5. Store lock with priority-aware structure
            counts["_active_lock"] = {
                "lock_id": lock_id,
                "items_with_priority": items_with_priority,
                "expires_at": expires_at,
                "created_at": time.time()
            }
            await self._state_manager.set_state("queue_counts", counts)
            await self._state_manager.save_state()

            logger.info(f"PopWithAck: created lock {lock_id} for {len(items_with_priority)} items, TTL={ttl}s for actor {self.actor_id}")

            # 6. Return just items to client (not priority metadata)
            return {
                "items": [entry["item"] for entry in items_with_priority],
                "count": len(items_with_priority),
                "locked": True,
                "lock_id": lock_id,
                "lock_expires_at": expires_at
            }

        except Exception as e:
            logger.error(f"Error in PopWithAck for actor {self.actor_id}: {e}", exc_info=True)
            return {"items": [], "count": 0, "locked": False, "message": f"Error: {str(e)}"}

    async def Acknowledge(self, data: Dict[str, Any]) -> dict:
        """
        Acknowledge popped items using lock ID.

        Validates the lock ID and removes the lock from state, completing the
        pop-acknowledge cycle. Items are already removed from the queue during
        PopWithAck.

        Args:
            data: Dictionary containing:
                - lock_id (str): The lock ID to acknowledge

        Returns:
            dict: {
                "success": bool,
                "message": str,
                "items_acknowledged": int (if success=True),
                "error_code": str (optional)
            }
        """
        try:
            lock_id = data.get("lock_id")
            if not lock_id:
                logger.warning(f"Acknowledge called without lock_id for actor {self.actor_id}")
                return {"success": False, "message": "lock_id is required"}

            # Load lock
            has_counts, counts = await self._state_manager.try_get_state("queue_counts")
            if not has_counts or "_active_lock" not in counts:
                logger.warning(f"Acknowledge failed: no active lock for actor {self.actor_id}")
                return {"success": False, "message": "No active lock found"}

            lock = counts["_active_lock"]

            # Check if expired
            if time.time() >= lock["expires_at"]:
                # Remove expired lock
                del counts["_active_lock"]
                await self._state_manager.set_state("queue_counts", counts)
                await self._state_manager.save_state()
                logger.info(f"Acknowledge failed: lock expired for actor {self.actor_id}")
                return {
                    "success": False,
                    "message": "Lock has expired",
                    "error_code": "LOCK_EXPIRED"
                }

            # Validate lock ID
            if lock["lock_id"] != lock_id:
                logger.warning(f"Acknowledge failed: invalid lock_id for actor {self.actor_id}")
                return {"success": False, "message": "Invalid lock_id"}

            # Remove lock (items are already removed from queue)
            item_count = len(lock["items_with_priority"])
            del counts["_active_lock"]
            await self._state_manager.set_state("queue_counts", counts)
            await self._state_manager.save_state()

            logger.info(f"Acknowledged {item_count} items for actor {self.actor_id}")
            return {
                "success": True,
                "message": "Items acknowledged successfully",
                "items_acknowledged": item_count
            }

        except Exception as e:
            logger.error(f"Error in Acknowledge for actor {self.actor_id}: {e}", exc_info=True)
            return {"success": False, "message": f"Error: {str(e)}"}

