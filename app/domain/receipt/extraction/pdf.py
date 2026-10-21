from __future__ import annotations

import io

import pdfplumber
from pdf2image import convert_from_bytes

from app.domain.receipt.extraction.image import ImageExtractor


class PdfExtractor:
    OCR_DPI = 300

    @staticmethod
    def extract(content: bytes) -> str:
        text = PdfExtractor._extract_text(content)

        if text:
            return text

        return PdfExtractor._extract_ocr(content)

    @staticmethod
    def _extract_text(content: bytes) -> str:
        pages: list[str] = []
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()

                if text:
                    pages.append(text)

        return "\n".join(pages).strip()

    @staticmethod
    def _extract_ocr(content: bytes) -> str:
        pages = convert_from_bytes(content, dpi=PdfExtractor.OCR_DPI)
        texts: list[str] = []
        for page in pages:
            text = ImageExtractor.extract_image(page)
            if text:
                texts.append(text)
        return "\n".join(texts).strip()
