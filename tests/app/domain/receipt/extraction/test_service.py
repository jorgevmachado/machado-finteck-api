from http import HTTPStatus
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.domain.receipt.extraction.service import ExtractionService


class TestExtractionService:
    @pytest.mark.asyncio
    @patch("app.domain.receipt.extraction.service.PdfExtractor.extract")
    async def test_extract_pdf(
        self,
        mock_extract,
    ):
        mock_extract.return_value = "Texto extraído do PDF"

        content = b"pdf-content"

        result = await ExtractionService().extract(
            content=content,
            content_type="application/pdf",
        )

        assert result == "Texto extraído do PDF"

        mock_extract.assert_called_once_with(content)

    @pytest.mark.asyncio
    @patch("app.domain.receipt.extraction.service.ImageExtractor.extract")
    async def test_extract_jpeg(
        self,
        mock_extract,
    ):
        mock_extract.return_value = "Texto extraído da imagem"

        content = b"jpeg-content"

        result = await ExtractionService().extract(
            content=content,
            content_type="image/jpeg",
        )

        assert result == "Texto extraído da imagem"

        mock_extract.assert_called_once_with(content)

    @pytest.mark.asyncio
    @patch("app.domain.receipt.extraction.service.ImageExtractor.extract")
    async def test_extract_png(
        self,
        mock_extract,
    ):
        mock_extract.return_value = "Texto extraído da imagem"

        content = b"png-content"

        result = await ExtractionService().extract(
            content=content,
            content_type="image/png",
        )

        assert result == "Texto extraído da imagem"

        mock_extract.assert_called_once_with(content)

    @pytest.mark.asyncio
    @patch("app.domain.receipt.extraction.service.PdfExtractor.extract")
    @patch("app.domain.receipt.extraction.service.ImageExtractor.extract")
    async def test_extract_raises_exception_for_unsupported_file_type(
        self,
        mock_image_extract,
        mock_pdf_extract,
    ):
        content = b"unsupported-content"

        with pytest.raises(HTTPException) as exception:
            await ExtractionService().extract(
                content=content,
                content_type="text/plain",
            )

        assert exception.value.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert exception.value.detail == "Unsupported file type"

        mock_pdf_extract.assert_not_called()
        mock_image_extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_extract_raises_exception_when_content_type_is_none(self):
        with pytest.raises(HTTPException) as exception:
            await ExtractionService().extract(
                content=b"file-content",
                content_type=None,
            )

        assert exception.value.status_code == HTTPStatus.UNSUPPORTED_MEDIA_TYPE
        assert exception.value.detail == "Unsupported file type"
