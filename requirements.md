# MangaForge AI - Dependency Guide

## Recommended runtime

- Python 3.12 (64-bit)
- OpenRouter API key for the default free-model router
- Ollama only when offline development is required

Python 3.12 is recommended for predictable compatibility across LangGraph,
LangChain, database drivers, and development tooling. The project may work on
newer Python versions, but those versions should be validated separately.

## Dependency groups

### API server

- `fastapi`: REST API and automatic OpenAPI documentation.
- `uvicorn[standard]`: ASGI development/production server.

### Multi-agent pipeline

- `langgraph`: Stateful workflow graph for the four manga agents.
- `langchain`: Prompt, message, and structured-output abstractions.
- `langchain-openai`: OpenAI-compatible provider adapter used by OpenRouter.
- `langchain-ollama`: Optional local development adapter.

### Configuration and validation

- `pydantic`: Strict request, response, and agent-output schemas.
- `pydantic-settings`: Typed settings loaded from environment variables.
- `python-dotenv`: Local `.env` file support.

### Persistence

- `sqlalchemy[asyncio]`: Async ORM and database abstraction.
- `alembic`: Database schema migrations.
- `aiosqlite`: Temporary local SQLite backend.
- `psycopg[binary]`: PostgreSQL driver for the production-ready path.

### Testing and HTTP

- `httpx`: Async HTTP client and FastAPI test client dependency.
- `pytest`: Test runner.
- `pytest-asyncio`: Async test support.

## Versioning policy

`requirements.txt` uses compatible-release constraints (`~=`). This keeps each
dependency within its selected minor release line while allowing compatible
patch updates. Once the first working pipeline is verified, generate a fully
resolved lock file for reproducible CI and deployment builds.

## Installation

From the project root, create and activate a virtual environment, then run:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

External model runtimes are deployment adapters and are intentionally not
installed as Python dependencies.
