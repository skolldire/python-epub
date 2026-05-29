# pdf-epub

A FastAPI web service that converts PDF files to EPUB format. Supports text-based PDFs (via pdfplumber) and scanned PDFs (via OCR with Tesseract). Built with a lightweight hexagonal architecture.

## Features

- Multi-file drag-and-drop web interface — each file gets its own progress bar and can be started independently
- PDF metadata auto-detected and pre-filled in the UI; user can override or clear before converting
- Real-time step indicator: Analyzing → Extracting → Building → Done (exposed via `progress_step` field)
- Optional per-file overrides: custom title, author, and cover image
- Text extraction with layout preservation (headings, paragraphs, tables, inline formatting)
- Drop-cap and first-character formatting correctly preserved
- Handles PDFs with vector-heavy pages (Notes, Keynote exports) without hanging
- Image extraction and embedding
- OCR for scanned PDFs (Spanish + English by default)
- Async background conversion with real-time status polling
- REST API for programmatic access
- Security headers on every response (CSP, X-Frame-Options, X-Content-Type-Options, …)

## Docker (recommended)

The container image is named **bookforge** and bundles all system dependencies (poppler, Tesseract + `spa+eng` language packs).

### Quick start

```bash
# Build and run
docker compose up --build

# Run in background
docker compose up -d --build
```

Open [http://localhost:8000](http://localhost:8000).

### Useful commands

```bash
# View logs
docker compose logs -f bookforge

# Stop
docker compose down

# Remove container + volume (deletes all uploaded/converted files)
docker compose down -v

# Rebuild image after code changes
docker compose build --no-cache
```

### Override settings at runtime

```bash
docker compose run --rm \
  -e DEBUG=true \
  -e LOG_LEVEL=DEBUG \
  -e OCR_LANG=spa \
  bookforge
```

### Build the image standalone

```bash
docker build -t bookforge:latest .
docker run -p 8000:8000 -v bookforge_data:/data bookforge:latest
```

---

## Local development (without Docker)

### System dependencies

```bash
# macOS
brew install poppler tesseract
brew install tesseract-lang   # all language packs, or selectively per language
```

### Python

Python 3.12+ (project uses Python 3.14).

### Installation

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

For interactive API docs, set `DEBUG=true` and visit `/docs`.

## Configuration

All settings can be overridden via environment variables or a `.env` file.
Copy `.env.example` to `.env` and edit as needed.

| Variable | Default | Description |
|----------|---------|-------------|
| `ENVIRONMENT` | `development` | Runtime environment (`development` / `production`) |
| `DEBUG` | `false` | Enables `/docs` and `/redoc` when `true` |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `UPLOAD_DIR` | `/tmp/pdf_epub/uploads` | Directory where uploaded PDFs are stored |
| `EPUB_DIR` | `/tmp/pdf_epub/epubs` | Directory where generated EPUBs are stored |
| `MAX_UPLOAD_BYTES` | `52428800` | Maximum upload size in bytes (default: 50 MB) |
| `OCR_LANG` | `spa+eng` | Tesseract language(s) for OCR |
| `CORS_ORIGINS` | `["*"]` | Allowed CORS origins (JSON array) |

## API Reference

### Create conversion job

```
POST /api/v1/jobs
Content-Type: multipart/form-data
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | yes | PDF file (`.pdf` extension, max 50 MB, magic bytes validated) |
| `title` | string | no | Override the extracted book title (max 500 chars) |
| `author` | string | no | Override the extracted author (max 500 chars) |
| `cover` | file | no | Custom cover image (JPEG or PNG, magic bytes validated) |

If `title`, `author`, or `cover` are omitted, the service auto-extracts them from the PDF.

**Response `201 Created`:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "pending",
  "original_filename": "document.pdf",
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:00:00Z",
  "epub_url": null,
  "error": null
}
```

```bash
# Minimal
curl -F "file=@document.pdf" http://localhost:8000/api/v1/jobs

# With overrides
curl -F "file=@document.pdf" \
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
  "status": "completed",
  "original_filename": "document.pdf",
  "created_at": "2026-05-28T10:00:00Z",
  "updated_at": "2026-05-28T10:00:05Z",
  "epub_url": "http://localhost:8000/api/v1/jobs/3fa85f64.../epub",
  "error": null
}
```

Job `status` values:

| Value | Meaning |
|-------|---------|
| `pending` | Queued, not started yet |
| `processing` | Conversion in progress |
| `completed` | EPUB ready for download |
| `failed` | Conversion failed — see `error` field |

```bash
curl http://localhost:8000/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

---

### Download EPUB

```
GET /api/v1/jobs/{job_id}/epub
```

Returns the EPUB file as `application/epub+zip`. Only available when `status == "completed"`. Returns `409 Conflict` if the job is not yet complete.

```bash
curl -O http://localhost:8000/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6/epub
```

---

### Delete job

```
DELETE /api/v1/jobs/{job_id}
```

Removes the job record and all associated files. Returns `204 No Content`.

```bash
curl -X DELETE http://localhost:8000/api/v1/jobs/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

---

### Health check

```
GET /health
```

```json
{ "status": "ok", "version": "0.1.0", "environment": "development" }
```

## Development

```bash
# Run tests
pytest

# Lint + format
ruff check src/ tests/
ruff format src/ tests/

# Type checking
mypy src/
```

## Architecture

Lightweight hexagonal (ports & adapters). See [CLAUDE.md](CLAUDE.md) for the full architecture guide.

```
Domain (pure Python)
  └── Application (use cases)
        └── Infrastructure (FastAPI, pdfplumber, ebooklib, …)
```

Key dependency rule: **domain never imports from application or infrastructure**; infrastructure depends on everything.
