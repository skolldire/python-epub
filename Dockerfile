# ─────────────────────────────────────────────
# bookforge — PDF to EPUB conversion service
# ─────────────────────────────────────────────

FROM python:3.14-slim

# System dependencies:
#   poppler-utils  → pdf2image (page rendering)
#   tesseract-ocr  → pytesseract (OCR engine)
#   tesseract-ocr-spa / eng → language packs for spa+eng OCR
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        poppler-utils \
        tesseract-ocr \
        tesseract-ocr-spa \
        tesseract-ocr-eng \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN groupadd -r bookforge && useradd -r -g bookforge -u 1000 bookforge

WORKDIR /app

# Install Python dependencies before copying source (better layer caching)
COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir --root-user-action=ignore --upgrade pip \
    && pip install --no-cache-dir --root-user-action=ignore .

# Copy application source
COPY src/ src/

# Persistent storage directories
RUN mkdir -p /data/uploads /data/epubs \
    && chown -R bookforge:bookforge /data /app

USER bookforge

# ── Runtime configuration ──────────────────
ENV PYTHONPATH=/app/src \
    ENVIRONMENT=production \
    LOG_LEVEL=INFO \
    DEBUG=false \
    UPLOAD_DIR=/data/uploads \
    EPUB_DIR=/data/epubs \
    OCR_LANG=spa+eng

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["python", "-m", "uvicorn", "pdf_epub.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", \
     "--no-access-log"]
