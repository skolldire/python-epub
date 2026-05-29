import shutil
from pathlib import Path

from pdf_epub.domain.ports import FileStoragePort


class LocalFileStorage(FileStoragePort):
    def __init__(self, upload_dir: Path, epub_dir: Path) -> None:
        self._upload_dir = upload_dir
        self._epub_dir = epub_dir
        upload_dir.mkdir(parents=True, exist_ok=True)
        epub_dir.mkdir(parents=True, exist_ok=True)

    def save_upload(self, job_id: str, filename: str, content: bytes) -> Path:
        safe_name = Path(filename).name  # strip any directory traversal
        dest = self._upload_dir / f"{job_id}_{safe_name}"
        dest.write_bytes(content)
        return dest

    def epub_output_path(self, job_id: str) -> Path:
        return self._epub_dir / f"{job_id}.epub"

    def cleanup(self, job_id: str) -> None:
        epub = self._epub_dir / f"{job_id}.epub"
        epub.unlink(missing_ok=True)
        # Remove uploaded PDF that matches the job — stored by job_id prefix when possible.
        # Falls back to leaving the original upload (no unique mapping in local storage).
        for f in self._upload_dir.glob(f"{job_id}*"):
            f.unlink(missing_ok=True)
