#!/usr/bin/env python3
"""
Example: Direct actor invocation using Dapr Python SDK.

This example shows how to interact with PushPopActor directly using
the Dapr Actor SDK without going through a REST API.

Prerequisites:
- Dapr runtime must be running (dapr run or docker-compose)
- Actor must be registered in your application
"""
import asyncio
from dapr.actor import ActorId, ActorProxy

from push_pop_actor import PushPopActorInterface


async def main():
    """Demonstrate direct actor usage."""
    print("=== Dapr PushPopActor Direct Usage Example ===\n")

    # Create actor proxy
    actor_id = "my-queue-123"
    print(f"Creating actor proxy for actor: {actor_id}")

    proxy = ActorProxy.create(
        actor_type="PushPopActor", actor_id=ActorId(actor_id), actor_interface=PushPopActorInterface
    )

    # Push some items
    print("\n1. Pushing items to queue...")
    items_to_push = [
        {"task_id": 1, "action": "send_email", "priority": "high"},
        {"task_id": 2, "action": "process_upload", "priority": "normal"},
        {"task_id": 3, "action": "generate_report", "priority": "low"},
    ]

    for item in items_to_push:
        success = await proxy.Push(item)
        if success:
            print(f"   ✓ Pushed: {item}")
        else:
            print(f"   ✗ Failed to push: {item}")

    # Pop items one at a time
    print("\n2. Popping items one at a time...")
    for i in range(2):
        items = await proxy.Pop(1)
        if items:
            print(f"   ✓ Popped: {items[0]}")
        else:
            print("   ✗ Queue is empty")

    # Pop remaining items in bulk
    print("\n3. Popping all remaining items...")
    items = await proxy.Pop(10)  # Pop up to 10 items
    print(f"   ✓ Popped {len(items)} item(s)")
    for item in items:
        print(f"     - {item}")

    # Try to pop from empty queue
    print("\n4. Attempting to pop from empty queue...")
    items = await proxy.Pop(5)
    if not items:
        print("   ✓ Queue is empty (as expected)")

    print("\n=== Example Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
