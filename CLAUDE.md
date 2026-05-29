# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FastAPI service for working with EPUB files. MIT licensed. Python 3.14.

## Environment

- Python 3.14 via a local `.venv` at the project root
- Activate: `source .venv/bin/activate`

## Architecture — Lightweight Hexagonal (Ports & Adapters)

Three concentric layers. The domain never imports from outer layers.

```
src/<package>/
├── domain/               # Pure Python — no framework dependencies
│   ├── entities.py       # Business objects (dataclasses only)
│   ├── value_objects.py
│   ├── exceptions.py     # Domain-level errors
│   └── ports.py          # Abstract repository/service interfaces (ABC or Protocol)
│
├── application/          # Use cases — orchestrates domain, calls ports
│   └── use_cases/
│       └── <action>.py   # One file per use case, one public function/class
│
├── infrastructure/       # Framework-specific implementations
│   ├── api/              # FastAPI routers, request/response Pydantic schemas
│   │   ├── routers/
│   │   └── schemas/
│   ├── persistence/      # Concrete repository implementations
│   └── adapters/         # External services (email, storage, third-party APIs)
│
├── config.py             # pydantic-settings Settings
├── log.py                # structlog configuration
├── exceptions.py         # HTTP exception handlers (wraps domain exceptions)
├── middleware.py         # RequestContextMiddleware (request-id, access log)
└── main.py               # Composition root: app factory + lifespan
```

### Dependency direction

```
infrastructure → application → domain
```

- **Domain**: entities, value objects, domain exceptions, port interfaces. Zero external imports.
- **Application**: use cases that call port interfaces. Receives concrete implementations via constructor injection or `Depends`.
- **Infrastructure**: FastAPI routers call use cases; persistence classes implement domain ports.

### Dependency injection

Use FastAPI `Depends` to wire concrete implementations into use cases at the router level. Keep use cases independent of FastAPI.

```python
# infrastructure/api/routers/epub.py
@router.post("/epubs")
async def create_epub(
    body: CreateEpubRequest,
    repo: EpubRepository = Depends(get_epub_repository),   # concrete impl
) -> EpubResponse:
    result = CreateEpub(repo).execute(body.to_domain())    # use case
    return EpubResponse.from_domain(result)
```

## Domain Rules

The domain layer must never import from:

- FastAPI or Starlette
- Pydantic or pydantic-settings
- SQLAlchemy or any ORM
- Storage SDKs (S3, GCS, Azure Blob, etc.)
- Logging frameworks (structlog, loguru)
- HTTP clients (httpx, requests, aiohttp)
- Cloud or third-party SDKs

Domain entities use plain Python `@dataclass`. Business rules live here — no framework knowledge allowed.

## Architecture Rules

Prefer:
- simple functions over classes where state isn't needed
- composition over inheritance
- explicit constructor injection over service locators
- pure business logic in the domain, I/O at the edges
- small, focused interfaces (ports with 1–3 methods)
- high cohesion within a layer, low coupling between layers

Avoid:
- framework leakage into the domain or application layers
- unnecessary abstractions before the need is proven
- generic base classes that exist only to share code
- deeply nested inheritance hierarchies
- overengineering for hypothetical future requirements

## Code Conventions

- **Language**: all comments, docstrings, variable names, commit messages, and README content must be written in **English**.
- **No Spanish** in source code, regardless of who is working on it.
- Docstrings only on public API surface (modules, classes, public functions). One-line max unless the behavior is genuinely non-obvious.
- Type annotations on every public function signature.

## Testing Rules

- Business rules must have unit tests.
- Domain tests must not require infrastructure (no DB, no HTTP, no filesystem).
- Mock only external dependencies (ports), never the domain itself.
- Tests must be deterministic — no random data, no time-dependent assertions without control.
- One test file per module; name it `test_<module>.py`.

## Dependency Rules

Prefer:
- the standard library
- lightweight, single-purpose packages
- well-maintained libraries with clear release history

Avoid:
- pulling in a framework when a small library or stdlib suffices
- two packages that solve the same problem
- packages with no recent activity or a single maintainer with no bus-factor mitigation

## README Policy

Update `README.md` whenever public-facing behavior changes:
- New or changed endpoints: method, path, request/response shape, example `curl`.
- New or changed configuration variables: name, type, default, purpose.
- New domain concepts: what they represent, why they exist.
- Behavior changes that require a migration path.
- New runtime dependencies: what they do, why they were added.

Internal refactors, performance improvements, and bug fixes that do not change observable behavior do not require a README update.

Format: clear sections, fenced code blocks for examples, no filler text.
