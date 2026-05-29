from functools import lru_cache

from fastapi import Depends

from pdf_epub.application.use_cases.convert_pdf import ConvertPdf
from pdf_epub.application.use_cases.download_epub import DownloadEpub
from pdf_epub.application.use_cases.get_job_status import GetJobStatus
from pdf_epub.application.use_cases.upload_pdf import UploadPdf
from pdf_epub.config import Settings, get_settings
from pdf_epub.domain.ports import JobRepositoryPort, FileStoragePort
from pdf_epub.infrastructure.builders.ebooklib_builder import EbooklibBuilder
from pdf_epub.infrastructure.extractors.pdfplumber_extractor import PdfPlumberExtractor
from pdf_epub.infrastructure.extractors.tesseract_ocr import TesseractOcr
from pdf_epub.infrastructure.persistence.in_memory_job_repo import InMemoryJobRepository
from pdf_epub.infrastructure.renderers.poppler_renderer import PopplerRenderer
from pdf_epub.infrastructure.storage.local_file_storage import LocalFileStorage


# Singletons — one instance per process lifetime.
@lru_cache
def _job_repo() -> InMemoryJobRepository:
    return InMemoryJobRepository()


@lru_cache
def _file_storage(settings: Settings = get_settings()) -> LocalFileStorage:
    return LocalFileStorage(
        upload_dir=settings.upload_dir,
        epub_dir=settings.epub_dir,
    )


@lru_cache
def _extractor() -> PdfPlumberExtractor:
    return PdfPlumberExtractor()


@lru_cache
def _renderer() -> PopplerRenderer:
    return PopplerRenderer()


@lru_cache
def _ocr() -> TesseractOcr:
    return TesseractOcr()


@lru_cache
def _builder() -> EbooklibBuilder:
    return EbooklibBuilder()


# ---------------------------------------------------------------------------
# FastAPI dependency functions
# ---------------------------------------------------------------------------


def get_job_repo() -> JobRepositoryPort:
    return _job_repo()


def get_storage() -> FileStoragePort:
    return _file_storage()


def get_upload_use_case(
    settings: Settings = Depends(get_settings),
    repo: JobRepositoryPort = Depends(get_job_repo),
    storage: FileStoragePort = Depends(get_storage),
) -> UploadPdf:
    return UploadPdf(repo=repo, storage=storage, max_bytes=settings.max_upload_bytes)


def get_convert_use_case(
    settings: Settings = Depends(get_settings),
    repo: JobRepositoryPort = Depends(get_job_repo),
    storage: FileStoragePort = Depends(get_storage),
) -> ConvertPdf:
    return ConvertPdf(
        repo=repo,
        storage=storage,
        extractor=_extractor(),
        renderer=_renderer(),
        ocr=_ocr(),
        builder=_builder(),
        ocr_lang=settings.ocr_lang,
    )


def get_status_use_case(
    repo: JobRepositoryPort = Depends(get_job_repo),
) -> GetJobStatus:
    return GetJobStatus(repo=repo)


def get_download_use_case(
    repo: JobRepositoryPort = Depends(get_job_repo),
) -> DownloadEpub:
    return DownloadEpub(repo=repo)
