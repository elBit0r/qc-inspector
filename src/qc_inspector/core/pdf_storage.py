"""Importazione atomica dei PDF nella directory runtime."""

import hashlib
import os
import shutil
import tempfile
from pathlib import Path


def _sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def store_pdf(source_path: str | Path, pdf_dir: str | Path) -> str:
    source = Path(source_path)
    pdf_hash = _sha256_file(source)
    target_dir = Path(pdf_dir)
    target_path = target_dir / f"{pdf_hash}.pdf"
    target_dir.mkdir(parents=True, exist_ok=True)
    if target_path.is_symlink():
        raise ValueError("Il PDF di destinazione non può essere un link simbolico.")
    if target_path.exists() and not target_path.is_file():
        raise ValueError("Destinazione PDF non valida.")
    if not target_path.exists():
        fd, temporary_path = tempfile.mkstemp(prefix=".import-", dir=target_dir)
        try:
            with os.fdopen(fd, "wb") as destination, source.open("rb") as origin:
                shutil.copyfileobj(origin, destination)
                destination.flush()
                os.fsync(destination.fileno())
                if _sha256_file(temporary_path) != pdf_hash:
                    raise ValueError("Il PDF sorgente è cambiato durante la copia.")
                directory_gid = target_dir.stat().st_gid
                if os.fstat(destination.fileno()).st_gid != directory_gid:
                    os.fchown(destination.fileno(), -1, directory_gid)
                os.fchmod(destination.fileno(), 0o640)
            # Pubblica il file completo senza sovrascrivere import concorrenti.
            try:
                os.link(temporary_path, target_path)
            except FileExistsError:
                if target_path.is_symlink() or not target_path.is_file():
                    raise ValueError("Destinazione PDF non valida.")
        finally:
            os.unlink(temporary_path)
    return str(target_path)
