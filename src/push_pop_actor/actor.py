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

    def _get_queue_count(self, metadata: dict, priority: int) -> int:
        """Get count for a priority queue from metadata."""
        queue_key = f"queue_{priority}"
        if "queues" not in metadata or queue_key not in metadata["queues"]:
            return 0
        return metadata["queues"][queue_key]["metadata"].get("count", 0)

    def _set_queue_count(self, metadata: dict, priority: int, count: int) -> None:
        """Set count for a priority queue in metadata."""
        queue_key = f"queue_{priority}"
        if "queues" not in metadata:
            metadata["queues"] = {}
        if queue_key not in metadata["queues"]:
            metadata["queues"][queue_key] = {"metadata": {}}
        metadata["queues"][queue_key]["metadata"]["count"] = count

    def _delete_queue_metadata(self, metadata: dict, priority: int) -> None:
        """Delete queue metadata when count reaches zero."""
        queue_key = f"queue_{priority}"
        if "queues" in metadata and queue_key in metadata["queues"]:
            del metadata["queues"][queue_key]

    def _get_priority_keys(self, metadata: dict) -> list:
        """Extract priority numbers from metadata queues."""
        if "queues" not in metadata:
            return []
        priorities = []
        for queue_key in metadata["queues"].keys():
            # Parse "queue_0" -> 0, "queue_1" -> 1, etc.
            if queue_key.startswith("queue_"):
                try:
                    priority = int(queue_key.split("_")[1])
                    priorities.append(priority)
                except (IndexError, ValueError):
                    continue
        return sorted(priorities)

    def _get_segment_key(self, priority: int, segment: int) -> str:
        """Build segment key: queue_0_seg_0"""
        return f"queue_{priority}_seg_{segment}"

    def _get_segment_size(self, metadata: dict) -> int:
        """Get configured segment size (default 100)"""
        return metadata.get("config", {}).get("segment_size", 100)

    def _get_head_segment(self, metadata: dict, priority: int) -> int:
        """Get head segment number for priority (default 0)"""
        queue_key = f"queue_{priority}"
        return metadata.get("queues", {}).get(queue_key, {}).get("metadata", {}).get("head_segment", 0)

    def _get_tail_segment(self, metadata: dict, priority: int) -> int:
        """Get tail segment number for priority (default 0)"""
        queue_key = f"queue_{priority}"
        return metadata.get("queues", {}).get(queue_key, {}).get("metadata", {}).get("tail_segment", 0)

    def _set_segment_pointers(self, metadata: dict, priority: int, head: int, tail: int) -> None:
        """Update head/tail segment pointers"""
        queue_key = f"queue_{priority}"
        if "queues" not in metadata:
            metadata["queues"] = {}
        if queue_key not in metadata["queues"]:
            metadata["queues"][queue_key] = {"metadata": {}}
        metadata["queues"][queue_key]["metadata"]["head_segment"] = head
        metadata["queues"][queue_key]["metadata"]["tail_segment"] = tail

    async def _on_activate(self) -> None:
        """
        Called when the actor is activated.
        Initializes the metadata map if it doesn't exist.
        """
        logger.info(f"PushPopActor activating: {self.actor_id}")

        # Check if metadata exists, if not initialize it
        has_metadata, _ = await self._state_manager.try_get_state("metadata")
        if not has_metadata:
            await self._state_manager.set_state("metadata", {
                "config": {"segment_size": 100},
                "queues": {}
            })
            await self._state_manager.save_state()
            logger.info(f"Initialized empty metadata map with segment config for actor {self.actor_id}")

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

            # Load metadata map
            has_metadata, metadata = await self._state_manager.try_get_state("metadata")
            if not has_metadata:
                metadata = {"config": {"segment_size": 100}, "queues": {}}

            # Get tail segment number for this priority
            tail_segment = self._get_tail_segment(metadata, priority)
            segment_key = self._get_segment_key(priority, tail_segment)

            # Load tail segment (or create empty)
            has_segment, segment = await self._state_manager.try_get_state(segment_key)
            if not has_segment:
                segment = []

            # Check if segment is full
            segment_size = self._get_segment_size(metadata)
            if len(segment) >= segment_size:
                # Allocate new segment
                tail_segment += 1
                segment_key = self._get_segment_key(priority, tail_segment)
                segment = []

            # Append item to segment (FIFO)
            segment.append(item)

            # Update metadata (count and pointers)
            current_count = self._get_queue_count(metadata, priority)
            head_segment = self._get_head_segment(metadata, priority)
            self._set_queue_count(metadata, priority, current_count + 1)
            self._set_segment_pointers(metadata, priority, head_segment, tail_segment)

            # Save segment and metadata
            await self._state_manager.set_state(segment_key, segment)
            await self._state_manager.set_state("metadata", metadata)
            await self._state_manager.save_state()

            logger.info(
                f"Pushed item to priority {priority} segment {tail_segment} for actor {self.actor_id}. Segment size: {len(segment)}, Total count: {current_count + 1}"
            )
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
            # Load metadata map
            has_metadata, metadata = await self._state_manager.try_get_state("metadata")
            if not has_metadata or not metadata:
                logger.info(f"Pop called but no queues have items for actor {self.actor_id}")
                return []

            # Sort priority keys numerically (0, 1, 2, ...), excluding _active_lock
            priority_keys = self._get_priority_keys(metadata)

            # Process each priority level in order
            for priority in priority_keys:
                count = self._get_queue_count(metadata, priority)
                if count == 0:
                    continue

                # Get head and tail segment numbers
                head_segment = self._get_head_segment(metadata, priority)
                tail_segment = self._get_tail_segment(metadata, priority)
                segment_key = self._get_segment_key(priority, head_segment)

                # Load head segment
                has_segment, segment = await self._state_manager.try_get_state(segment_key)

                if not has_segment or not segment:
                    # Defensive: fix count desync
                    logger.warning(f"Count desync detected for priority {priority}, fixing...")
                    self._delete_queue_metadata(metadata, priority)
                    continue

                # Pop single item from front
                item = segment[0]
                segment = segment[1:]

                # Get the segment number before any modifications (for logging)
                popped_from_segment = head_segment

                # Handle segment cleanup
                if len(segment) == 0:
                    if head_segment < tail_segment:
                        # More segments exist, move to next
                        # Clear the empty segment from state
                        await self._state_manager.set_state(segment_key, [])
                        head_segment += 1
                        # Update metadata pointers
                        new_count = count - 1
                        self._set_queue_count(metadata, priority, new_count)
                        self._set_segment_pointers(metadata, priority, head_segment, tail_segment)
                        await self._state_manager.set_state("metadata", metadata)
                        await self._state_manager.save_state()
                        logger.info(
                            f"Popped 1 item from priority {priority} segment {popped_from_segment} (now empty, moved to segment {head_segment}). Remaining count: {new_count}"
                        )
                        return [item]
                    else:
                        # Last segment empty, queue is now empty
                        # Clear the segment from state (set to empty list to effectively delete it)
                        await self._state_manager.set_state(segment_key, [])
                        self._delete_queue_metadata(metadata, priority)
                        await self._state_manager.set_state("metadata", metadata)
                        await self._state_manager.save_state()
                        logger.info(
                            f"Popped last item from priority {priority} for actor {self.actor_id}. Queue now empty."
                        )
                        return [item]

                # Save updated segment and metadata (segment not empty)
                await self._state_manager.set_state(segment_key, segment)
                new_count = count - 1
                self._set_queue_count(metadata, priority, new_count)
                self._set_segment_pointers(metadata, priority, head_segment, tail_segment)
                await self._state_manager.set_state("metadata", metadata)
                await self._state_manager.save_state()

                logger.info(
                    f"Popped 1 item from priority {priority} segment {popped_from_segment} for actor {self.actor_id}. Remaining count: {new_count}"
                )
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

            # Load current metadata
            has_metadata, metadata = await self._state_manager.try_get_state("metadata")
            if not has_metadata:
                metadata = {"config": {"segment_size": 100}, "queues": {}}

            # Return items to each priority queue (prepend to head segment)
            for priority, items in items_by_priority.items():
                # Get head segment for this priority
                head_segment = self._get_head_segment(metadata, priority)
                segment_key = self._get_segment_key(priority, head_segment)

                # Load existing head segment
                has_segment, segment = await self._state_manager.try_get_state(segment_key)
                if not has_segment:
                    segment = []

                # Prepend items to front (FIFO, they were already popped)
                # Note: Segment may temporarily exceed segment_size limit
                # This is acceptable for returned items (avoids complex splitting logic)
                segment = items + segment

                # Update metadata
                current_count = self._get_queue_count(metadata, priority)
                tail_segment = self._get_tail_segment(metadata, priority)
                self._set_queue_count(metadata, priority, current_count + len(items))
                self._set_segment_pointers(metadata, priority, head_segment, tail_segment)

                # Save segment
                await self._state_manager.set_state(segment_key, segment)

                logger.info(
                    f"Returned {len(items)} expired lock items to priority {priority} segment {head_segment} for actor {self.actor_id}"
                )

            # Save updated metadata
            await self._state_manager.set_state("metadata", metadata)
            await self._state_manager.save_state()

            logger.info(
                f"Returned {len(items_with_priority)} total expired lock items to original priorities for actor {self.actor_id}"
            )

        except Exception as e:
            logger.error(
                f"Error returning items to queue for actor {self.actor_id}: {e}", exc_info=True
            )

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
            has_metadata, metadata = await self._state_manager.try_get_state("metadata")
            if has_metadata and "_active_lock" in metadata:
                lock = metadata["_active_lock"]
                # Check if expired
                if time.time() < lock["expires_at"]:
                    # Lock still valid - return 423 info
                    logger.info(f"PopWithAck blocked: active lock exists for actor {self.actor_id}")
                    return {
                        "items": [],
                        "count": 0,
                        "locked": True,
                        "lock_expires_at": lock["expires_at"],
                        "message": "Queue is locked pending acknowledgement",
                    }
                else:
                    # Expired - return items to queue and remove lock
                    logger.info(f"Lock expired for actor {self.actor_id}, returning items to queue")
                    await self._return_items_to_queue(lock["items_with_priority"])
                    del metadata["_active_lock"]
                    await self._state_manager.set_state("metadata", metadata)
                    await self._state_manager.save_state()

            # 2. Pop single item WITH priority tracking
            items_with_priority = []

            # Reload metadata after potential cleanup
            has_metadata, metadata = await self._state_manager.try_get_state("metadata")
            if not has_metadata or not metadata:
                logger.info(f"PopWithAck called but no queues have items for actor {self.actor_id}")
                return {"items": [], "count": 0, "locked": False}

            # Sort priority keys numerically (0, 1, 2, ...), excluding _active_lock
            priority_keys = self._get_priority_keys(metadata)

            # Process each priority level in order
            for priority in priority_keys:
                count = self._get_queue_count(metadata, priority)
                if count == 0:
                    continue

                # Get head and tail segment numbers
                head_segment = self._get_head_segment(metadata, priority)
                tail_segment = self._get_tail_segment(metadata, priority)
                segment_key = self._get_segment_key(priority, head_segment)

                # Load head segment
                has_segment, segment = await self._state_manager.try_get_state(segment_key)

                if not has_segment or not segment:
                    # Defensive: fix count desync
                    logger.warning(f"Count desync detected for priority {priority}, fixing...")
                    self._delete_queue_metadata(metadata, priority)
                    continue

                # Pop single item from front
                item = segment[0]
                segment = segment[1:]

                # Add to result WITH priority metadata
                items_with_priority.append({"item": item, "priority": priority})

                # Handle segment cleanup
                if len(segment) == 0:
                    if head_segment < tail_segment:
                        # More segments exist, move to next
                        # Clear the empty segment from state
                        await self._state_manager.set_state(segment_key, [])
                        head_segment += 1
                    # If head_segment == tail_segment, we'll handle this after creating lock
                else:
                    # Save updated segment (only if not empty)
                    await self._state_manager.set_state(segment_key, segment)

                # Update metadata map
                new_count = count - 1
                if new_count == 0:
                    self._delete_queue_metadata(metadata, priority)
                else:
                    self._set_queue_count(metadata, priority, new_count)
                    self._set_segment_pointers(metadata, priority, head_segment, tail_segment)

                logger.info(
                    f"PopWithAck: popped 1 item from priority {priority} segment {head_segment} for actor {self.actor_id}"
                )
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
            metadata["_active_lock"] = {
                "lock_id": lock_id,
                "items_with_priority": items_with_priority,
                "expires_at": expires_at,
                "created_at": time.time(),
            }
            await self._state_manager.set_state("metadata", metadata)
            await self._state_manager.save_state()

            logger.info(
                f"PopWithAck: created lock {lock_id} for {len(items_with_priority)} items, TTL={ttl}s for actor {self.actor_id}"
            )

            # 6. Return just items to client (not priority metadata)
            return {
                "items": [entry["item"] for entry in items_with_priority],
                "count": len(items_with_priority),
                "locked": True,
                "lock_id": lock_id,
                "lock_expires_at": expires_at,
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
            has_metadata, metadata = await self._state_manager.try_get_state("metadata")
            if not has_metadata or "_active_lock" not in metadata:
                logger.warning(f"Acknowledge failed: no active lock for actor {self.actor_id}")
                return {"success": False, "message": "No active lock found"}

            lock = metadata["_active_lock"]

            # Check if expired
            if time.time() >= lock["expires_at"]:
                # Remove expired lock
                del metadata["_active_lock"]
                await self._state_manager.set_state("metadata", metadata)
                await self._state_manager.save_state()
                logger.info(f"Acknowledge failed: lock expired for actor {self.actor_id}")
                return {
                    "success": False,
                    "message": "Lock has expired",
                    "error_code": "LOCK_EXPIRED",
                }

            # Validate lock ID
            if lock["lock_id"] != lock_id:
                logger.warning(f"Acknowledge failed: invalid lock_id for actor {self.actor_id}")
                return {"success": False, "message": "Invalid lock_id"}

            # Remove lock (items are already removed from queue)
            item_count = len(lock["items_with_priority"])
            del metadata["_active_lock"]
            await self._state_manager.set_state("metadata", metadata)
            await self._state_manager.save_state()

            logger.info(f"Acknowledged {item_count} items for actor {self.actor_id}")
            return {
                "success": True,
                "message": "Items acknowledged successfully",
                "items_acknowledged": item_count,
            }

        except Exception as e:
            logger.error(f"Error in Acknowledge for actor {self.actor_id}: {e}", exc_info=True)
            return {"success": False, "message": f"Error: {str(e)}"}
