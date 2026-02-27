#!/usr/bin/env python3
"""
Example FastAPI server demonstrating PushPopActor usage.

This server provides REST API endpoints for interacting with PushPopActor instances.
It can be used as-is or serve as a reference implementation for your own projects.

Endpoints:
- POST /queue/{queueId}/push - Push item to queue with optional priority
- POST /queue/{queueId}/pop?depth=N - Pop N items from queue (priority-ordered)
- GET /health - Health check
"""
import asyncio
import logging
import signal
import sys
from typing import Any, Dict, List

import uvicorn
from dapr.actor import ActorId, ActorProxy
from dapr.actor.runtime.config import ActorRuntimeConfig
from dapr.actor.runtime.runtime import ActorRuntime
from dapr.ext.fastapi import DaprActor
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from push_pop_actor import PushPopActor, PushPopActorInterface

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


# Request/Response models
class PushRequest(BaseModel):
    """Request body for pushing an item to the queue."""

    item: Dict[str, Any]
    priority: int = 0  # Priority level (0 = highest priority)


class PushResponse(BaseModel):
    """Response for push operation."""

    success: bool
    message: str


class PopResponse(BaseModel):
    """Response for pop operation."""

    items: List[Dict[str, Any]]
    count: int


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


# Create FastAPI app
app = FastAPI(
    title="Dapr Push-Pop Actor API",
    description="REST API for interacting with PushPopActor instances",
    version="0.1.0",
)

# Configure Dapr Actor runtime
config = ActorRuntimeConfig()
ActorRuntime.set_actor_config(config)

# Add Dapr Actor extension
actor_extension = DaprActor(app)


@app.on_event("startup")
async def startup_event():
    """Register actors on startup."""
    logger.info("Registering Dapr actors...")
    await actor_extension.register_actor(PushPopActor)
    logger.info("PushPopActor registered successfully")


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Returns:
        HealthResponse: Service health status
    """
    return HealthResponse(status="healthy", service="dapr-push-pop-actor-api")


@app.post("/queue/{queue_id}/push", response_model=PushResponse)
async def push_item(queue_id: str, request: PushRequest):
    """
    Push an item to the queue with optional priority.

    Args:
        queue_id: Unique identifier for the queue
        request: Push request containing the item and optional priority (0 = highest)

    Returns:
        PushResponse: Result of the push operation

    Raises:
        HTTPException: If the push operation fails
    """
    try:
        # Validate priority
        if request.priority < 0:
            raise HTTPException(status_code=400, detail="Priority must be non-negative")

        logger.info(f"Push request for queue {queue_id} with priority {request.priority}")

        # Create actor proxy
        proxy = ActorProxy.create(
            actor_type="PushPopActor",
            actor_id=ActorId(queue_id),
            actor_interface=PushPopActorInterface,
        )

        # Push item with priority
        # Note: Dapr actor proxy requires single dict argument
        success = await proxy.Push({"item": request.item, "priority": request.priority})

        if success:
            return PushResponse(
                success=True,
                message=f"Item pushed to queue {queue_id} at priority {request.priority}"
            )
        else:
            raise HTTPException(status_code=400, detail="Failed to push item")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pushing item to queue {queue_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@app.post("/queue/{queue_id}/pop", response_model=PopResponse)
async def pop_items(queue_id: str, depth: int = Query(1, ge=1, le=100)):
    """
    Pop items from the queue.

    Args:
        queue_id: Unique identifier for the queue
        depth: Number of items to pop (default: 1, max: 100)

    Returns:
        PopResponse: Popped items and count

    Raises:
        HTTPException: If the pop operation fails
    """
    try:
        logger.info(f"Pop request for queue {queue_id} with depth {depth}")

        # Create actor proxy
        proxy = ActorProxy.create(
            actor_type="PushPopActor",
            actor_id=ActorId(queue_id),
            actor_interface=PushPopActorInterface,
        )

        # Pop items
        items = await proxy.Pop(depth)

        return PopResponse(items=items, count=len(items))

    except Exception as e:
        logger.error(f"Error popping items from queue {queue_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


class APIServer:
    """Main API server class with graceful shutdown support."""

    def __init__(self, host: str = "0.0.0.0", port: int = 8000):
        self.host = host
        self.port = port
        self.shutdown_event = asyncio.Event()

    async def start(self):
        """Start the API server."""
        try:
            logger.info(f"Starting Dapr Push-Pop Actor API on {self.host}:{self.port}")

            config = uvicorn.Config(app=app, host=self.host, port=self.port, log_level="info")
            server = uvicorn.Server(config)

            # Run server until shutdown
            await server.serve()

        except Exception as e:
            logger.error(f"Error starting server: {e}")
            raise

    def signal_handler(self, signum, frame):
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, initiating shutdown...")
        self.shutdown_event.set()


def main():
    """Main entry point for the API server."""
    import argparse

    parser = argparse.ArgumentParser(description="Dapr Push-Pop Actor API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")

    args = parser.parse_args()
    server = APIServer(host=args.host, port=args.port)

    # Set up signal handlers
    def signal_handler(signum, frame):
        server.signal_handler(signum, frame)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
