from unittest.mock import MagicMock, patch

from app.domain.receipt.extraction.pdf import PdfExtractor


class TestPdfExtractor:
    @patch("app.domain.receipt.extraction.pdf.pdfplumber.open")
    def test_extract_returns_text_extracted_from_pdf(
        self,
        mock_pdf_open,
    ):
        page_1 = MagicMock()
        page_1.extract_text.return_value = "Página 1"

        page_2 = MagicMock()
        page_2.extract_text.return_value = "Página 2"

        pdf = MagicMock()
        pdf.pages = [page_1, page_2]

        mock_pdf_open.return_value.__enter__.return_value = pdf

        result = PdfExtractor.extract(b"pdf-content")

        assert result == "Página 1\nPágina 2"

        mock_pdf_open.assert_called_once()

    @patch("app.domain.receipt.extraction.pdf.pdfplumber.open")
    def test_extract_ignores_pages_without_text(
        self,
        mock_pdf_open,
    ):
        page_1 = MagicMock()
        page_1.extract_text.return_value = "Página 1"

        page_2 = MagicMock()
        page_2.extract_text.return_value = None

        page_3 = MagicMock()
        page_3.extract_text.return_value = ""

        pdf = MagicMock()
        pdf.pages = [page_1, page_2, page_3]

        mock_pdf_open.return_value.__enter__.return_value = pdf

        result = PdfExtractor.extract(b"pdf-content")

        assert result == "Página 1"

    @patch("app.domain.receipt.extraction.pdf.PdfExtractor._extract_ocr")
    @patch("app.domain.receipt.extraction.pdf.PdfExtractor._extract_text")
    def test_extract_uses_ocr_when_text_is_not_found(
        self,
        mock_extract_text,
        mock_extract_ocr,
    ):
        mock_extract_text.return_value = ""
        mock_extract_ocr.return_value = "Texto extraído por OCR"

        result = PdfExtractor.extract(b"pdf-content")

        assert result == "Texto extraído por OCR"

        mock_extract_text.assert_called_once_with(b"pdf-content")
        mock_extract_ocr.assert_called_once_with(b"pdf-content")

    @patch("app.domain.receipt.extraction.pdf.PdfExtractor._extract_ocr")
    @patch("app.domain.receipt.extraction.pdf.PdfExtractor._extract_text")
    def test_extract_does_not_use_ocr_when_text_is_found(
        self,
        mock_extract_text,
        mock_extract_ocr,
    ):
        mock_extract_text.return_value = "Texto extraído do PDF"

        result = PdfExtractor.extract(b"pdf-content")

        assert result == "Texto extraído do PDF"

        mock_extract_text.assert_called_once_with(b"pdf-content")
        mock_extract_ocr.assert_not_called()

    @patch("app.domain.receipt.extraction.pdf.convert_from_bytes")
    @patch("app.domain.receipt.extraction.pdf.ImageExtractor.extract_image")
    def test_extract_ocr_uses_pdf_pages_and_image_extractor(
        self,
        mock_extract_image,
        mock_convert_from_bytes,
    ):
        page_1 = MagicMock()
        page_2 = MagicMock()

        mock_convert_from_bytes.return_value = [
            page_1,
            page_2,
        ]

        mock_extract_image.side_effect = [
            "Página 1",
            "Página 2",
        ]

        result = PdfExtractor._extract_ocr(b"pdf-content")

        assert result == "Página 1\nPágina 2"

        mock_convert_from_bytes.assert_called_once_with(
            b"pdf-content",
            dpi=PdfExtractor.OCR_DPI,
        )

        assert mock_extract_image.call_count == 2
        mock_extract_image.assert_any_call(page_1)
        mock_extract_image.assert_any_call(page_2)

    @patch("app.domain.receipt.extraction.pdf.convert_from_bytes")
    @patch("app.domain.receipt.extraction.pdf.ImageExtractor.extract_image")
    def test_extract_ocr_ignores_pages_without_text(
        self,
        mock_extract_image,
        mock_convert_from_bytes,
    ):
        page_1 = MagicMock()
        page_2 = MagicMock()
        page_3 = MagicMock()

        mock_convert_from_bytes.return_value = [
            page_1,
            page_2,
            page_3,
        ]

        mock_extract_image.side_effect = [
            "Página 1",
            "",
            None,
        ]

        result = PdfExtractor._extract_ocr(b"pdf-content")

        assert result == "Página 1"

    @patch("app.domain.receipt.extraction.pdf.pdfplumber.open")
    def test_extract_text_strips_result(
        self,
        mock_pdf_open,
    ):
        page = MagicMock()
        page.extract_text.return_value = "  Texto do PDF  "

        pdf = MagicMock()
        pdf.pages = [page]

        mock_pdf_open.return_value.__enter__.return_value = pdf

        result = PdfExtractor._extract_text(b"pdf-content")

        assert result == "Texto do PDF"

    @patch("app.domain.receipt.extraction.pdf.pdfplumber.open")
    def test_extract_text_returns_empty_string_when_no_text_exists(
        self,
        mock_pdf_open,
    ):
        page = MagicMock()
        page.extract_text.return_value = None

        pdf = MagicMock()
        pdf.pages = [page]

        mock_pdf_open.return_value.__enter__.return_value = pdf

        result = PdfExtractor._extract_text(b"pdf-content")

        assert result == ""
