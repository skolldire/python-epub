import asyncio
import io
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse

from pdf_epub.application.use_cases.convert_pdf import ConvertPdf
from pdf_epub.application.use_cases.download_epub import DownloadEpub
from pdf_epub.application.use_cases.get_job_status import GetJobStatus
from pdf_epub.application.use_cases.upload_pdf import UploadPdf
from pdf_epub.auth import verify_api_key
from pdf_epub.dependencies import (
    get_convert_use_case,
    get_download_use_case,
    get_executor,
    get_job_repo,
    get_status_use_case,
    get_upload_use_case,
)
from pdf_epub.domain.entities import ConversionJob
from pdf_epub.domain.exceptions import ExtractionError, InvalidJobStateError
from pdf_epub.domain.ports import JobRepositoryPort
from pdf_epub.domain.value_objects import JobStatus
from pdf_epub.exceptions import AppError, NotFoundError, UnprocessableError
from pdf_epub.infrastructure.api.limiter import limiter
from pdf_epub.infrastructure.api.schemas.responses import JobResponse

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def _safe_download_name(filename: str) -> str:
    stem = re.sub(r"[\x00/\\]", "", Path(filename).stem).strip() or "book"
    return stem + ".epub"


router = APIRouter(
    prefix="/api/v1/jobs",
    tags=["jobs"],
    dependencies=[Depends(verify_api_key)],
)


def _to_response(job: ConversionJob, request: Request) -> JobResponse:
    epub_url = None
    if job.status == JobStatus.COMPLETED:
        epub_url = str(request.url_for("download_epub", job_id=job.id))
    return JobResponse(
        id=job.id,
        status=job.status,
        original_filename=job.original_filename,
        created_at=job.created_at,
        updated_at=job.updated_at,
        epub_url=epub_url,
        error=job.error,
        progress_step=job.progress_step,
    )


@router.post("/peek", include_in_schema=False)
@limiter.limit("30/minute")
async def peek_pdf(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """Fast metadata read — does not store the file."""
    content = await file.read()
    title, author, page_count = "", "", 0
    if content.startswith(b"%PDF-"):
        try:
            import pdfplumber
            with pdfplumber.open(io.BytesIO(content)) as pdf:
                meta = pdf.metadata or {}
                title      = str(meta.get("Title")  or "").strip()
                author     = str(meta.get("Author") or "").strip()
                page_count = len(pdf.pages)
        except Exception:
            pass
    return JSONResponse({"title": title, "author": author, "page_count": page_count})


@router.post("", status_code=status.HTTP_201_CREATED, response_model=JobResponse)
@limiter.limit("10/minute")
async def create_job(
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    author: str | None = Form(default=None),
    cover: UploadFile | None = File(default=None),
    upload: UploadPdf = Depends(get_upload_use_case),
    convert: ConvertPdf = Depends(get_convert_use_case),
    executor: ThreadPoolExecutor = Depends(get_executor),
) -> JobResponse:
    content  = await file.read()
    filename = file.filename or "upload.pdf"

    cover_bytes: bytes | None = None
    if cover and cover.filename:
        cover_bytes = await cover.read()

    try:
        job = upload.execute(
            filename=filename,
            content=content,
            custom_title=title or None,
            custom_author=author or None,
            custom_cover=cover_bytes,
        )
    except ExtractionError as exc:
        raise UnprocessableError(str(exc))

    # Run conversion in the dedicated executor — does not share uvicorn's threadpool.
    asyncio.get_running_loop().run_in_executor(executor, convert.execute, job.id)

    return _to_response(job, request)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    request: Request,
    status_uc: GetJobStatus = Depends(get_status_use_case),
) -> JobResponse:
    if not _UUID_RE.match(job_id):
        raise NotFoundError(f"Job {job_id}")
    try:
        job = status_uc.execute(job_id)
    except ExtractionError:
        raise NotFoundError(f"Job {job_id}")
    return _to_response(job, request)


@router.get("/{job_id}/epub", name="download_epub")
async def download_epub(
    job_id: str,
    download: DownloadEpub = Depends(get_download_use_case),
    status_uc: GetJobStatus = Depends(get_status_use_case),
) -> FileResponse:
    if not _UUID_RE.match(job_id):
        raise NotFoundError(f"Job {job_id}")
    try:
        epub_path = download.execute(job_id)
        job = status_uc.execute(job_id)
    except ExtractionError:
        raise NotFoundError(f"Job {job_id}")
    except InvalidJobStateError as exc:
        raise AppError(str(exc), status_code=409, code="not_ready")

    return FileResponse(
        path=epub_path,
        media_type="application/epub+zip",
        filename=_safe_download_name(job.original_filename),
    )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job(
    job_id: str,
    repo: JobRepositoryPort = Depends(get_job_repo),
) -> None:
    if not _UUID_RE.match(job_id):
        raise NotFoundError(f"Job {job_id}")
    if repo.get(job_id) is None:
        raise NotFoundError(f"Job {job_id}")
    repo.delete(job_id)
