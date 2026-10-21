import hashlib
from http import HTTPStatus
from fastapi import UploadFile, HTTPException

from app.core.settings import Settings

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
}

MAX_FILE_SIZE = Settings().RECEIPT_MAX_FILE_SIZE_MB * 1024 * 1024
MAX_BATCH_FILES = Settings().RECEIPT_BATCH_MAX_FILES or 10

async def validate_file(file: UploadFile) -> bytes:
    if not file.filename:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail="File name is required."
        )

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail="Unsupported file type. Allowed types are: PDF, JPEG, PNG.",
        )
    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY, detail="File is empty."
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
            detail=f"File size exceeds the maximum allowed size of {MAX_FILE_SIZE} bytes.",
        )

    return content

def calculate_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

def validate_batch_size(files: list[UploadFile]) -> None:
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=(f"A maximum of {MAX_BATCH_FILES} files can be uploaded at once."),
        )