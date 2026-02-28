# Quick Start Guide

Get up and running with Dapr PushPopActor in 5 minutes.

## Prerequisites

- **Docker & Docker Compose** (for Docker mode)
- **Python 3.11+** (for library mode)
- **Dapr CLI** (optional, for local development)

## Quick Start with Docker (Recommended)

The fastest way to try PushPopActor is using Docker Compose.

### 1. Clone the Repository

```bash
git clone https://github.com/olitomlinson/dapr-push-pop-actor.git
cd dapr-push-pop-actor
```

### 2. Start Services

```bash
docker-compose up
```

This starts:
- PostgreSQL database (state store)
- Dapr placement service
- API server with Dapr sidecar

Wait for all services to be healthy (~30 seconds).

### 3. Test the API

Open a new terminal and run the example script:

```bash
chmod +x examples/curl_examples.sh
./examples/curl_examples.sh
```

Or manually test with curl:

```bash
# Push an item
curl -X POST http://localhost:8000/queue/my-queue/push \
  -H "Content-Type: application/json" \
  -d '{"item": {"task": "hello", "priority": "high"}}'

# Pop items
curl -X POST "http://localhost:8000/queue/my-queue/pop"
```

## Quick Start as Library

Use PushPopActor in your existing Python/Dapr application.

### 1. Install Package

```bash
pip install push-pop-actor
```

### 2. Register Actor

In your FastAPI app with Dapr:

```python
from dapr.ext.fastapi import DaprActor
from push_pop_actor import PushPopActor

app = FastAPI()
actor_extension = DaprActor(app)

@app.on_event("startup")
async def startup():
    await actor_extension.register_actor(PushPopActor)
```

### 3. Use the Actor

```python
from dapr.actor import ActorId, ActorProxy
from push_pop_actor import PushPopActorInterface

# Create proxy
proxy = ActorProxy.create(
    actor_type="PushPopActor",
    actor_id=ActorId("my-queue"),
    actor_interface=PushPopActorInterface
)

# Push items
await proxy.Push({"task": "send_email"})

# Pop items
items = await proxy.Pop(5)
```

## Quick Start with Example API Server

Run the included API server example.

### 1. Install with API Extras

```bash
pip install push-pop-actor[api]
```

### 2. Start Dapr Services

You need PostgreSQL and Dapr placement service. Use Docker Compose:

```bash
docker-compose up postgres-db placement
```

### 3. Run API Server

```bash
dapr run \
  --app-id push-pop-service \
  --app-port 8000 \
  --resources-path ./dapr/components \
  --config ./dapr/config/config.yml \
  -- dapr-push-pop-server
```

### 4. Test API

```bash
curl http://localhost:8000/health
```

## Verify Installation

Run the test suite to verify everything works:

```bash
pip install push-pop-actor[dev]
pytest
```

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) to understand how it works
- See [API_REFERENCE.md](API_REFERENCE.md) for complete API documentation
- Check [examples/](../examples/) for more usage patterns
- Explore configuration options in `dapr/components/` and `dapr/config/`

## Troubleshooting

### Docker Compose Issues

**Services not starting:**
```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs api-server
docker-compose logs api-server-dapr
```

**Port conflicts:**
Edit `docker-compose.yml` and change port mappings:
```yaml
ports:
  - "8001:8000"  # Changed from 8000:8000
```

### Library Installation Issues

**Dapr SDK not found:**
```bash
# Install latest Dapr SDK
pip install --upgrade dapr dapr-ext-fastapi
```

**Import errors:**
```bash
# Ensure package is installed in editable mode
pip install -e .
```

### Actor Registration Issues

**Actor not found:**
- Ensure actor is registered before creating proxy
- Check Dapr logs for registration errors
- Verify Dapr sidecar is running

**State not persisting:**
- Check state store configuration in `dapr/components/`
- Verify database connection string
- Check Dapr component logs

## Common Patterns

### Multiple Queues

Each actor ID is a separate queue:

```bash
# Queue 1
curl -X POST http://localhost:8000/queue/queue-1/push -d '{"item": {"data": 1}}'

# Queue 2
curl -X POST http://localhost:8000/queue/queue-2/push -d '{"item": {"data": 2}}'

# They're independent
curl -X POST "http://localhost:8000/queue/queue-1/pop0"  # Returns item 1 only
```

### Batch Processing

Pop multiple items at once:

```bash
# Pop up to 50 items
curl -X POST "http://localhost:8000/queue/batch-queue/pop"
```

### Task Queue Pattern

```python
# Producer: Push tasks
for task in tasks:
    await proxy.Push({"task_id": task.id, "data": task.data})

# Consumer: Pop and process
while True:
    items = await proxy.Pop(10)  # Process 10 at a time
    for item in items:
        await process_task(item)
    if not items:
        await asyncio.sleep(1)  # Wait for more tasks
```

## Getting Help

- Check [README.md](../README.md) for overview
- Read [ARCHITECTURE.md](ARCHITECTURE.md) for design details
- Browse [examples/](../examples/) for code samples
- Open an issue on GitHub for bugs
