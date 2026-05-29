# bookforge — PDF to EPUB

A FastAPI service that converts PDF files to EPUB format. Supports text-based PDFs (via pdfplumber) and scanned PDFs (OCR via Tesseract). Built with a lightweight hexagonal (ports & adapters) architecture.

## Features

- **Web UI** — multi-file drag-and-drop; each file has its own progress pipeline (Upload → Analyze → Extract → Build → Done)
- **PDF metadata** auto-detected and pre-filled; user can override title, author, and cover image
- **Text-based PDFs** — layout-preserving extraction: headings, paragraphs, tables, inline formatting, drop caps, images
- **Scanned PDFs** — full-page OCR via Tesseract (Spanish + English by default; configurable)
- **REST API** — programmatic access for all operations
- **API key authentication** — optional; disabled when `API_KEY` is not set (safe for local development)
- **Rate limiting** — 10 requests/min on job creation, 30/min on metadata peek (per IP)
- **Safety limits** — configurable page count and conversion timeout protect against malformed or overly complex PDFs
- **Automatic cleanup** — completed/failed jobs and their files are removed after 24 h; stuck jobs after 1 h
- **Observability** — structured JSON logging in production, Prometheus metrics at `/metrics`
- **Security headers** on every response: CSP (no `unsafe-inline`), X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy

---

## Docker (recommended)

The image bundles all system dependencies: poppler-utils, Tesseract, and the `spa+eng` language packs.

### Quick start

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000).

### Production deployment

Set at minimum `API_KEY` and restrict `CORS_ORIGINS`:

```bash
API_KEY=$(openssl rand -hex 32)

docker compose run --rm \
  -e API_KEY="$API_KEY" \
  -e CORS_ORIGINS='["https://yourapp.example.com"]' \
  -e ENVIRONMENT=production \
  bookforge
```

Or edit `compose.yaml` to uncomment and fill the `API_KEY` line.

### Useful commands

```bash
# View logs
docker compose logs -f bookforge

# Stop
docker compose down

# Remove container + volume (deletes all uploaded/converted files)
docker compose down -v

# Rebuild after code changes
docker compose build --no-cache
```

---

## Local development (without Docker)

### System dependencies

```bash
# macOS
brew install poppler tesseract tesseract-lang

# Debian / Ubuntu
sudo apt-get install poppler-utils tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng
```

### Python setup

Requires Python 3.14.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running

```bash
PYTHONPATH=src uvicorn pdf_epub.main:app --reload
```

Open [http://localhost:8000](http://localhost:8000).

Set `DEBUG=true` to enable interactive API docs at `/docs`.

---

## Configuration

All settings can be overridden via environment variables or a `.env` file.
Copy `.env.example` to `.env` and edit as needed.

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Runtime environment (`development` / `production`) |
| `DEBUG` | `false` | Enables `/docs` and `/redoc` when `true` |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `UPLOAD_DIR` | `/tmp/pdf_epub/uploads` | Directory for uploaded PDFs |
| `EPUB_DIR` | `/tmp/pdf_epub/epubs` | Directory for generated EPUBs |
| `MAX_UPLOAD_BYTES` | `52428800` | Maximum upload size in bytes (default 50 MB) |
| `OCR_LANG` | `spa+eng` | Tesseract language(s) for OCR |
| `CORS_ORIGINS` | `["*"]` | Allowed CORS origins (JSON array). **Restrict in production.** |
| `API_KEY` | _(unset)_ | Bearer token required on all `/api/v1/*` endpoints. Leave unset to disable auth. |
| `MAX_PAGES` | `1000` | Maximum pages per PDF. Requests exceeding this are rejected before conversion. |
| `MAX_CONVERSION_SECONDS` | `300` | Per-job timeout in seconds. Conversion fails gracefully when exceeded. |
| `METRICS_ENABLED` | `true` | Exposes a Prometheus `/metrics` endpoint. Restrict at the reverse proxy in production. |

---

## Authentication

When `API_KEY` is configured, all `/api/v1/*` endpoints require the header:

```
Authorization: Bearer <your-api-key>
```

Requests without a valid key return `401 Unauthorized`. The health check (`/health`) and web UI are always public.

```bash
# Generate a strong key
API_KEY=$(openssl rand -hex 32)

# Use it in requests
curl -H "Authorization: Bearer $API_KEY" \
     -F "file=@document.pdf" \
     http://localhost:8000/api/v1/jobs
```

---

## API Reference

### Create conversion job

```
POST /api/v1/jobs
Content-Type: multipart/form-data
```

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | yes | PDF file (`.pdf`, max 50 MB, magic bytes validated) |
| `title` | string | no | Override extracted title (max 500 chars) |
| `author` | string | no | Override extracted author (max 500 chars) |
| `cover` | file | no | Custom cover image (JPEG or PNG, magic bytes validated) |

Auto-extracts title, author, and cover from the PDF when not supplied.

**Rate limit:** 10 requests / minute per IP.

**Response `201 Created`:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending",
  "original_filename": "document.pdf",
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:00:00Z",
  "epub_url": null,
  "error": null,
  "progress_step": null
}
```

```bash
# Minimal
curl -F "file=@document.pdf" http://localhost:8000/api/v1/jobs

# With auth and overrides
curl -H "Authorization: Bearer $API_KEY" \
     -F "file=@document.pdf" \
     -F "title=My Book" \
     -F "author=Jane Doe" \
     -F "cover=@cover.jpg" \
     http://localhost:8000/api/v1/jobs
```

---

### Get job status

```
GET /api/v1/jobs/{job_id}
```

**Response `200 OK`:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "processing",
  "original_filename": "document.pdf",
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:00:03Z",
  "epub_url": null,
  "error": null,
  "progress_step": "extracting"
}
```

`status` values:

| Value | Meaning |
|---|---|
| `pending` | Queued, conversion not started yet |
| `processing` | Conversion in progress |
| `completed` | EPUB ready — `epub_url` is populated |
| `failed` | Conversion failed — see `error` field |

`progress_step` values during `processing`:

| Value | Meaning |
|---|---|
| `analyzing` | Detecting PDF type (text vs. scanned) |
| `extracting` | Extracting text and images |
| `ocr_N_T` | OCR in progress — page N of T |
| `building` | Assembling EPUB file |

```bash
curl -H "Authorization: Bearer $API_KEY" \
     http://localhost:8000/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

---

### Download EPUB

```
GET /api/v1/jobs/{job_id}/epub
```

Returns the EPUB as `application/epub+zip`. Only available when `status == "completed"`. Returns `409 Conflict` if the job is not yet done.

```bash
curl -H "Authorization: Bearer $API_KEY" \
     -O http://localhost:8000/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/epub
```

---

### Delete job

```
DELETE /api/v1/jobs/{job_id}
```

Removes the job record and all associated files from disk. Returns `204 No Content`.

```bash
curl -H "Authorization: Bearer $API_KEY" \
     -X DELETE \
     http://localhost:8000/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

---

### Health check

```
GET /health
```

Always public (no auth required). Used by Docker's healthcheck.

```json
{ "status": "ok", "version": "0.1.0", "environment": "production" }
```

---

### Metrics

```
GET /metrics
```

Prometheus-format metrics: request counts, latencies, and process stats. Enabled when `METRICS_ENABLED=true` (default). Not included in the OpenAPI schema.

**Restrict at the reverse proxy in production** — this endpoint is unauthenticated by design so Prometheus scrapers can reach it without API key management:

```nginx
# Nginx example — block /metrics from public internet
location /metrics {
    allow 10.0.0.0/8;
    deny all;
}
```

---

## Error responses

All errors follow the same shape:

```json
{
  "error": {
    "code": "not_found",
    "message": "Job abc123 not found"
  }
}
```

| HTTP status | `code` | When |
|---|---|---|
| `400` | `bad_request` | Generic client error |
| `401` | `unauthorized` | Missing or invalid API key |
| `404` | `not_found` | Job ID does not exist |
| `409` | `not_ready` | EPUB not yet available for download |
| `422` | `unprocessable` | File validation failed (not a PDF, too large, invalid cover, page limit exceeded) |
| `429` | `rate_limit_exceeded` | Too many requests from this IP |
| `500` | `internal_error` | Unexpected server error |

---

## Development

```bash
# Run tests
PYTHONPATH=src pytest

# Run a single test file
PYTHONPATH=src pytest tests/unit/test_upload_validation.py -v

# Run tests with coverage report (threshold: 75%)
PYTHONPATH=src pytest --cov=src --cov-report=term-missing

# Lint + format
ruff check src/ tests/
ruff format src/ tests/

# Type checking
mypy src/
```

### Test structure

```
tests/
├── conftest.py              # Shared fixtures (TestClient with dependency overrides)
├── test_health.py           # Health endpoint
├── test_jobs.py             # Job lifecycle integration tests
├── test_auth.py             # API key authentication integration tests
└── unit/
    ├── test_upload_validation.py    # UploadPdf business rules (no HTTP/filesystem)
    ├── test_job_state_machine.py    # ConversionJob domain state transitions
    └── test_convert_limits.py       # max_pages and deadline enforcement
```

---

## Architecture

Lightweight hexagonal (ports & adapters). See [CLAUDE.md](CLAUDE.md) for the full guide.

```
Domain  (pure Python — no framework imports)
  └── Application  (use cases, orchestrates domain via port interfaces)
        └── Infrastructure  (FastAPI routers, pdfplumber, ebooklib, Tesseract, …)
```

Dependencies flow inward only: `Infrastructure → Application → Domain`.
