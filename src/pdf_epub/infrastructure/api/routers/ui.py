from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from pdf_epub.application.use_cases.get_job_status import GetJobStatus
from pdf_epub.dependencies import get_status_use_case
from pdf_epub.domain.exceptions import ExtractionError
from pdf_epub.exceptions import NotFoundError

import pathlib

_TEMPLATES_DIR = pathlib.Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["ui"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
async def job_page(
    request: Request,
    job_id: str,
    status_uc: GetJobStatus = Depends(get_status_use_case),
) -> HTMLResponse:
    try:
        status_uc.execute(job_id)
    except ExtractionError:
        raise NotFoundError(f"Job {job_id}")

    return templates.TemplateResponse(request, "job.html", {"job_id": job_id})
