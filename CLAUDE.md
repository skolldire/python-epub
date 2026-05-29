# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

FastAPI service for working with EPUB files. MIT licensed. Python 3.14.

## Environment

- Python 3.14 via a local `.venv` at the project root
- Activate: `source .venv/bin/activate`
- IDE: JetBrains PyCharm (`.idea/` present)

## Architecture — Lightweight Hexagonal (Ports & Adapters)

Three concentric layers. The domain never imports from outer layers.

```
src/<package>/
├── domain/               # Pure Python — no framework dependencies
│   ├── entities.py       # Business objects (dataclasses / Pydantic BaseModel)
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

## Code Conventions

- **Language**: all comments, docstrings, variable names, commit messages, and README content must be written in **English**.
- **No Spanish** in source code, regardless of who is working on it.
- Docstrings only on public API surface (modules, classes, public functions). One-line max unless the behavior is genuinely non-obvious.
- Type annotations on every public function signature.

## README Policy

**Update `README.md` after every meaningful change.** This is not optional.

What to document after each change:
- New endpoints: method, path, request/response shape, example `curl`.
- New configuration variables: name, type, default, purpose.
- New domain concepts: what they represent, why they exist.
- Changed behavior: what changed and the migration path if any.
- New dependencies: what they do, why they were added.

Format: clear sections, fenced code blocks for examples, no filler text.
