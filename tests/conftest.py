import pytest
from fastapi.testclient import TestClient

from pdf_epub.config import get_settings
from pdf_epub.dependencies import get_job_repo, get_storage
from pdf_epub.infrastructure.persistence.in_memory_job_repo import InMemoryJobRepository
from pdf_epub.infrastructure.storage.local_file_storage import LocalFileStorage
from pdf_epub.main import create_app


@pytest.fixture(scope="session")
def tmp_dirs(tmp_path_factory):
    base = tmp_path_factory.mktemp("pdf_epub")
    return base / "uploads", base / "epubs"


@pytest.fixture()
def client(tmp_dirs):
    upload_dir, epub_dir = tmp_dirs
    repo = InMemoryJobRepository()
    storage = LocalFileStorage(upload_dir=upload_dir, epub_dir=epub_dir)

    app = create_app()
    app.dependency_overrides[get_job_repo] = lambda: repo
    app.dependency_overrides[get_storage] = lambda: storage

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
