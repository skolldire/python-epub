from datetime import datetime

from pydantic import BaseModel

from pdf_epub.domain.value_objects import JobStatus


class JobResponse(BaseModel):
    id: str
    status: JobStatus
    original_filename: str
    created_at: datetime
    updated_at: datetime
    epub_url: str | None = None
    error: str | None = None
    progress_step: str | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
