from http import HTTPStatus

from fastapi import HTTPException

from app.domain.receipt.extraction.image import ImageExtractor
from app.domain.receipt.extraction.pdf import PdfExtractor


class ExtractionService:

    @staticmethod
    async def extract(content: bytes, content_type: str | None) -> str:
        if content_type == "application/pdf":
            return PdfExtractor.extract(content)

        if content_type in {"image/jpeg", "image/png"}:
            return ImageExtractor.extract(content)

        raise HTTPException(
            status_code=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type",
        )
