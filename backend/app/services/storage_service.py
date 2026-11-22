"""Secure storage of uploaded audio files.

Files are stored outside the web root under ``storage/audio/<user_id>/`` with a
random UUID name. The original filename is only kept as metadata, so a hostile
filename can never influence a filesystem path.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile

from app.core.config import settings
from app.core.errors import AppError

ALLOWED_EXTENSIONS = {"wav", "mp3"}
CHUNK_SIZE = 256 * 1024  # 256 KiB -> low memory footprint


class StorageError(AppError):
    status_code = 500
    code = "storage_error"


@dataclass
class StoredFile:
    reference: str  # relative path stored in the database, e.g. "1/abc.wav"
    path: Path
    size: int
    filename: str  # sanitised display filename
    file_format: str  # "wav" | "mp3"


def sanitize_filename(name: str | None) -> str:
    base = os.path.basename((name or "audio").replace("\\", "/"))
    base = re.sub(r"[^A-Za-z0-9._ -]", "_", base).strip(" ._")
    if not base:
        base = "audio"
    stem, dot, ext = base.rpartition(".")
    if not dot:
        return base[:120]
    stem = stem[:110] or "audio"
    return f"{stem}.{ext.lower()[:10]}"


def ensure_storage_dirs() -> None:
    for directory in (settings.audio_dir, settings.report_dir, settings.tmp_dir):
        directory.mkdir(parents=True, exist_ok=True)


def audio_path_for(reference: str) -> Path:
    """Resolve a stored reference to an absolute path inside the audio directory."""
    base = settings.audio_dir.resolve()
    candidate = (base / reference).resolve()
    if not candidate.is_relative_to(base):
        raise StorageError("Invalid file reference.")
    return candidate


def _detect_format(header: bytes) -> str | None:
    if len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE":
        return "wav"
    if len(header) >= 3 and header[:3] == b"ID3":
        return "mp3"
    # MPEG audio frame sync: 11 set bits
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return "mp3"
    return None


async def save_upload(upload: UploadFile, user_id: int) -> StoredFile:
    """Persist an upload safely, enforcing extension + size + header checks."""
    display_name = sanitize_filename(upload.filename)
    extension = display_name.rsplit(".", 1)[-1].lower() if "." in display_name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise AppError(
            "Only WAV and MP3 audio files are supported.",
            code="unsupported_format",
            status_code=415,
        )

    ensure_storage_dirs()
    user_dir = settings.audio_dir / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    reference = f"{user_id}/{uuid.uuid4().hex}.{extension}"
    destination = audio_path_for(reference)
    temp_path = destination.with_suffix(destination.suffix + ".part")

    size = 0
    header = b""
    try:
        with temp_path.open("wb") as out:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise AppError(
                        f"File is larger than the {settings.max_upload_mb} MB limit.",
                        code="file_too_large",
                        status_code=413,
                    )
                if len(header) < 12:
                    header += chunk[: 12 - len(header)]
                out.write(chunk)
        if size == 0:
            raise AppError("The uploaded file is empty.", code="empty_file", status_code=415)

        detected = _detect_format(header)
        if detected is None:
            raise AppError(
                "The file does not appear to be a valid WAV or MP3 audio file.",
                code="invalid_audio",
                status_code=415,
            )
        if detected != extension:
            raise AppError(
                f"File content ({detected.upper()}) does not match the .{extension} extension.",
                code="format_mismatch",
                status_code=415,
            )

        temp_path.replace(destination)
    except AppError:
        temp_path.unlink(missing_ok=True)
        raise
    except OSError as exc:  # pragma: no cover - disk failures
        temp_path.unlink(missing_ok=True)
        raise StorageError("Could not store the uploaded file.") from exc
    finally:
        await upload.close()

    return StoredFile(
        reference=reference,
        path=destination,
        size=size,
        filename=display_name,
        file_format=detected,
    )


STREAM_CHUNK_MAX_BYTES = 8 * 1024 * 1024


async def save_stream_chunk(upload: UploadFile, user_id: int) -> StoredFile:
    """Persist a live chunk in the temporary directory for scoring only.

    The caller is responsible for deleting the file immediately after decoding;
    nothing here is written under the permanent audio directory.
    """
    display_name = sanitize_filename(upload.filename)
    extension = display_name.rsplit(".", 1)[-1].lower() if "." in display_name else ""
    if extension not in ALLOWED_EXTENSIONS:
        raise AppError(
            "Live chunks must be WAV or MP3 audio.", code="unsupported_format", status_code=415
        )

    ensure_storage_dirs()
    destination = settings.tmp_dir / f"live-{user_id}-{uuid.uuid4().hex}.{extension}"
    size = 0
    header = b""
    try:
        with destination.open("wb") as out:
            while chunk := await upload.read(CHUNK_SIZE):
                size += len(chunk)
                if size > STREAM_CHUNK_MAX_BYTES:
                    raise AppError(
                        "This live chunk is too large.", code="chunk_too_large", status_code=413
                    )
                if len(header) < 12:
                    header += chunk[: 12 - len(header)]
                out.write(chunk)
        if size == 0:
            raise AppError("The live chunk is empty.", code="empty_file", status_code=415)
        detected = _detect_format(header)
        if detected is None or detected != extension:
            raise AppError(
                "This live chunk is not a valid WAV or MP3 file.",
                code="invalid_audio",
                status_code=415,
            )
    except AppError:
        destination.unlink(missing_ok=True)
        raise
    except OSError as exc:  # pragma: no cover - disk failures
        destination.unlink(missing_ok=True)
        raise StorageError("Could not store the live chunk.") from exc
    finally:
        await upload.close()
    return StoredFile(
        reference=str(destination),
        path=destination,
        size=size,
        filename=display_name,
        file_format=detected,
    )


def delete_stored_file(reference: str) -> None:
    try:
        audio_path_for(reference).unlink(missing_ok=True)
    except (StorageError, OSError):  # pragma: no cover - best effort cleanup
        pass


def purge_temporary_files(max_age_seconds: int = 3600) -> int:
    """Remove stale ``.part`` files left behind by interrupted uploads."""
    removed = 0
    now = 0
    try:
        import time

        now = time.time()
        for directory in (settings.audio_dir, settings.tmp_dir):
            if not directory.exists():
                continue
            for path in directory.rglob("*.part"):
                try:
                    if now - path.stat().st_mtime > max_age_seconds:
                        path.unlink(missing_ok=True)
                        removed += 1
                except OSError:
                    continue
    except Exception:  # pragma: no cover
        pass
    return removed


def storage_usage_bytes() -> int:
    total = 0
    try:
        for path in settings.audio_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
    except OSError:
        pass
    return total


def clear_user_directory(user_id: int) -> None:
    path = settings.audio_dir / str(user_id)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
