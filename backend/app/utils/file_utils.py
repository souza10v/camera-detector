import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile, HTTPException
from app.config import settings


def ensure_dirs():
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.processed_dir).mkdir(parents=True, exist_ok=True)


def get_file_extension(filename: str) -> str:
    return Path(filename).suffix.lower()


def generate_unique_filename(original_filename: str) -> str:
    ext = get_file_extension(original_filename)
    return f"{uuid.uuid4().hex}{ext}"


def validate_file_type(content_type: str, filename: str) -> str:
    allowed = settings.allowed_image_types_list + settings.allowed_video_types_list
    if content_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de arquivo não suportado: {content_type}. Tipos aceitos: {', '.join(allowed)}"
        )
    if content_type in settings.allowed_image_types_list:
        return "image"
    return "video"


def validate_file_size(file_size: int):
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    if file_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Arquivo muito grande. Tamanho máximo: {settings.max_file_size_mb}MB"
        )


async def save_upload_file(upload_file: UploadFile) -> tuple[str, str]:
    ensure_dirs()
    unique_name = generate_unique_filename(upload_file.filename)
    file_path = os.path.join(settings.upload_dir, unique_name)
    async with aiofiles.open(file_path, "wb") as f:
        content = await upload_file.read()
        validate_file_size(len(content))
        await f.write(content)
    return file_path, unique_name


def get_processed_image_path(original_name: str) -> str:
    stem = Path(original_name).stem
    return os.path.join(settings.processed_dir, f"{stem}_processed.jpg")
