# Claude Context: Push-Pop Actor

## Project Overview

**push-pop-actor** is a Python library providing a simple FIFO queue-based Dapr actor for storing and retrieving dictionaries. It's designed for lightweight message queuing, task scheduling, and ordered processing in Dapr applications.

- **Package Name**: `push-pop-actor` (PyPI/pip)
- **Python Module**: `push_pop_actor` (import name)
- **GitHub**: https://github.com/olitomlinson/dapr-push-pop-actor
- **Python**: 3.11+
- **Dapr**: 1.17.0+

## Project Structure

```
.
├── src/push_pop_actor/          # Main package source
│   ├── __init__.py              # Exports PushPopActor, PushPopActorInterface
│   └── actor.py                 # Core actor implementation
├── examples/
│   ├── direct_usage.py          # Direct actor invocation example
│   ├── api_server/              # FastAPI server example
│   │   └── main.py              # REST API with actor registration
│   └── curl_examples.sh         # API testing script
├── tests/
│   └── test_actor.py            # Unit tests with mocked state manager
├── docs/
│   ├── QUICKSTART.md            # Getting started guide
│   ├── ARCHITECTURE.md          # Design details
│   └── API_REFERENCE.md         # Complete API docs
├── dapr/
│   ├── components/              # Dapr component configs (state store)
│   └── config/                  # Dapr runtime config
├── pyproject.toml               # Package configuration
├── docker-compose.yml           # Full stack (PostgreSQL, Dapr, API)
└── Dockerfile                   # API server container

```

## Core API

### Actor Interface

```python
from push_pop_actor import PushPopActor, PushPopActorInterface

# Two methods only:
async def Push(self, item: dict) -> bool    # Add to end (FIFO)
async def Pop(self) -> list                  # Remove single item from front
```

### Usage Modes

1. **Library Mode**: Import and register actor in existing Dapr apps
2. **API Server Mode**: Run example REST API (`dapr-push-pop-server`)
3. **Docker Mode**: Full stack with PostgreSQL + Dapr placement

## Key Files

- **[src/push_pop_actor/actor.py](src/push_pop_actor/actor.py)**: Core `PushPopActor` implementation
- **[pyproject.toml](pyproject.toml)**: Package metadata, dependencies, scripts
- **[examples/api_server/main.py](examples/api_server/main.py)**: Reference FastAPI implementation
- **[tests/test_actor.py](tests/test_actor.py)**: Comprehensive unit tests

## Technology Stack

- **Dapr SDK**: `dapr>=1.17.0rc5`, `dapr-ext-fastapi>=1.17.0rc5`
- **Web Framework**: FastAPI + Uvicorn (optional, for API mode)
- **Testing**: pytest, pytest-asyncio, pytest-cov
- **Linting**: black, ruff, mypy

## Common Commands

```bash
# Install
pip install -e "."                          # Base install
pip install -e ".[api]"                     # With API extras
pip install -e ".[dev]"                     # With dev tools

# Test
pytest                                      # Run tests
pytest --cov=src/push_pop_actor            # With coverage

# Lint
black src/ tests/ examples/                # Format
ruff check src/ tests/ examples/           # Lint
mypy src/                                  # Type check

# Run
docker-compose up                          # Full stack
dapr-push-pop-server --host 0.0.0.0        # API server only
```

## Architecture Notes

### Actor Model
- Each actor ID = separate queue instance
- Single-threaded per actor (no race conditions)
- State persisted to Dapr state store (PostgreSQL, Redis, etc.)
- Automatic activation/deactivation via Dapr

### State Management
- Queue stored as single state key: `"queue"`
- Format: `List[dict]` in Dapr state store
- Push appends to end, Pop removes from front
- State saved after every operation

### REST API Endpoints
- `POST /queue/{queueId}/push` - Push item
- `POST /queue/{queueId}/pop` - Pop single item
- `GET /health` - Health check

## Development Conventions

### Code Style
- Line length: 100 characters
- Target: Python 3.11+
- Type hints: Optional (mypy strict mode disabled)
- Async/await: All actor methods are async

### Testing
- Mock `_state_manager` to avoid Dapr runtime dependency
- Coverage target: >95%
- Test file naming: `test_*.py`

### Import Patterns
```python
# External imports
from dapr.actor import ActorId, ActorProxy
from dapr.ext.fastapi import DaprActor

# Internal imports
from push_pop_actor import PushPopActor, PushPopActorInterface
```

## Important Notes

1. **Package vs Module Naming**:
   - PyPI package: `push-pop-actor` (hyphenated)
   - Python module: `push_pop_actor` (underscored)
   - GitHub repo: `dapr-push-pop-actor` (includes "dapr-" prefix)

2. **Actor Registration**: Must register `PushPopActor` before creating proxies

3. **Item Validation**: Push only accepts JSON-serializable dicts

4. **FIFO Guarantee**: Items always returned in insertion order

5. **Concurrency**: One operation per actor instance at a time

6. **Direct Actor API Access**: You can interact directly with actors via Dapr's HTTP API for testing and debugging. This allows you to invoke actor methods and inspect state without going through the application's REST API:
   ```bash
   # Invoke actor method directly
   curl -X POST http://localhost:3500/v1.0/actors/PushPopActor/my-queue/method/Push \
     -H "Content-Type: application/json" \
     -d '{"item": {"test": "data"}}'

   # Get actor state directly (useful for debugging)
   curl http://localhost:3500/v1.0/actors/PushPopActor/my-queue/state/queue
   ```
   - Dapr sidecar typically runs on port 3500 (configurable)
   - Actor type: `PushPopActor`
   - State key: `queue`
   - Full API reference: https://docs.dapr.io/reference/api/actors_api/

## Future Considerations

- Max queue size limits (currently unbounded)
- Batch push operations (currently one-at-a-time)
- Queue metrics/monitoring endpoints
- Alternative state store examples (Redis, CosmosDB)

## Quick Reference Links

- Dapr Docs: https://docs.dapr.io/
- Dapr Python SDK: https://github.com/dapr/python-sdk
- Project Issues: https://github.com/olitomlinson/dapr-push-pop-actor/issues
