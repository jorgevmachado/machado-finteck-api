from io import BytesIO
from unittest.mock import patch

from PIL import Image

from app.domain.receipt.extraction.image import (
    ImageExtractor,
    OcrWord,
)


class TestOcrWord:
    def test_center_y_returns_vertical_center(self):
        word = OcrWord(
            text="Caixa",
            left=100,
            top=20,
            width=80,
            height=20,
            confidence=95.0,
        )

        assert word.center_y == 30.0


class TestImageExtractor:
    @patch("app.domain.receipt.extraction.image.ImageExtractor._extract_words")
    def test_extract_returns_built_text_from_image(
        self,
        mock_extract_words,
    ):
        words = [
            OcrWord(
                text="CAIXA",
                left=10,
                top=10,
                width=50,
                height=20,
                confidence=95.0,
            ),
        ]

        mock_extract_words.return_value = words

        image = Image.new("RGB", (100, 100))
        buffer = BytesIO()

        image.save(buffer, format="PNG")

        result = ImageExtractor.extract(buffer.getvalue())

        assert result == "CAIXA"

        mock_extract_words.assert_called_once()

    @patch("app.domain.receipt.extraction.image.ImageExtractor._extract_words")
    def test_extract_image_returns_built_text(
        self,
        mock_extract_words,
    ):
        words = [
            OcrWord(
                text="CAIXA",
                left=10,
                top=10,
                width=50,
                height=20,
                confidence=95.0,
            ),
        ]

        mock_extract_words.return_value = words

        image = Image.new("RGB", (100, 100))

        result = ImageExtractor.extract_image(image)

        assert result == "CAIXA"

        mock_extract_words.assert_called_once_with(image)

    @patch("app.domain.receipt.extraction.image.pytesseract.image_to_data")
    def test_extract_words_converts_tesseract_data_to_ocr_words(
        self,
        mock_image_to_data,
    ):
        mock_image_to_data.return_value = {
            "text": ["CAIXA", " ", "Pagamento"],
            "conf": ["95.5", "90.0", "88.2"],
            "left": ["10", "70", "100"],
            "top": ["20", "20", "20"],
            "width": ["50", "10", "80"],
            "height": ["20", "20", "20"],
        }

        image = Image.new("RGB", (300, 100))

        result = ImageExtractor._extract_words(image)

        assert result == [
            OcrWord(
                text="CAIXA",
                left=10,
                top=20,
                width=50,
                height=20,
                confidence=95.5,
            ),
            OcrWord(
                text="Pagamento",
                left=100,
                top=20,
                width=80,
                height=20,
                confidence=88.2,
            ),
        ]

        mock_image_to_data.assert_called_once_with(
            image,
            lang="por",
            output_type=__import__(
                "pytesseract",
            ).Output.DICT,
        )

    @patch("app.domain.receipt.extraction.image.pytesseract.image_to_data")
    def test_extract_words_ignores_empty_text(
        self,
        mock_image_to_data,
    ):
        mock_image_to_data.return_value = {
            "text": ["CAIXA", "", "   ", "Pagamento"],
            "conf": ["95.5", "90.0", "90.0", "88.2"],
            "left": ["10", "70", "80", "100"],
            "top": ["20", "20", "20", "20"],
            "width": ["50", "10", "10", "80"],
            "height": ["20", "20", "20", "20"],
        }

        image = Image.new("RGB", (300, 100))

        result = ImageExtractor._extract_words(image)

        assert [word.text for word in result] == [
            "CAIXA",
            "Pagamento",
        ]

    @patch("app.domain.receipt.extraction.image.pytesseract.image_to_data")
    def test_extract_words_ignores_invalid_confidence(
        self,
        mock_image_to_data,
    ):
        mock_image_to_data.return_value = {
            "text": ["CAIXA", "Pagamento", "Banco"],
            "conf": ["95.5", "invalid", "-1"],
            "left": ["10", "70", "100"],
            "top": ["20", "20", "20"],
            "width": ["50", "80", "50"],
            "height": ["20", "20", "20"],
        }

        image = Image.new("RGB", (300, 100))

        result = ImageExtractor._extract_words(image)

        assert [word.text for word in result] == ["CAIXA"]

    @patch("app.domain.receipt.extraction.image.pytesseract.image_to_data")
    def test_extract_words_uses_configured_language(
        self,
        mock_image_to_data,
    ):
        mock_image_to_data.return_value = {
            "text": [],
            "conf": [],
            "left": [],
            "top": [],
            "width": [],
            "height": [],
        }

        image = Image.new("RGB", (100, 100))

        ImageExtractor._extract_words(image)

        mock_image_to_data.assert_called_once_with(
            image,
            lang="por",
            output_type=__import__(
                "pytesseract",
            ).Output.DICT,
        )

    def test_build_text_returns_empty_string_when_no_words(self):
        result = ImageExtractor._build_text([])

        assert result == ""

    def test_build_text_groups_words_from_same_line(self):
        words = [
            OcrWord(
                text="CAIXA",
                left=10,
                top=10,
                width=50,
                height=20,
                confidence=95.0,
            ),
            OcrWord(
                text="ECONOMICA",
                left=70,
                top=11,
                width=80,
                height=20,
                confidence=95.0,
            ),
        ]

        result = ImageExtractor._build_text(words)

        assert result == "CAIXA ECONOMICA"

    def test_build_text_creates_new_line_when_words_are_far_apart_vertically(self):
        words = [
            OcrWord(
                text="CAIXA",
                left=10,
                top=10,
                width=50,
                height=20,
                confidence=95.0,
            ),
            OcrWord(
                text="Pagamento",
                left=10,
                top=50,
                width=80,
                height=20,
                confidence=95.0,
            ),
        ]

        result = ImageExtractor._build_text(words)

        assert result == "CAIXA\nPagamento"

    def test_build_text_orders_words_from_left_to_right(self):
        words = [
            OcrWord(
                text="Pagamento",
                left=100,
                top=10,
                width=80,
                height=20,
                confidence=95.0,
            ),
            OcrWord(
                text="de",
                left=80,
                top=10,
                width=15,
                height=20,
                confidence=95.0,
            ),
            OcrWord(
                text="Comprovante",
                left=10,
                top=10,
                width=60,
                height=20,
                confidence=95.0,
            ),
        ]

        result = ImageExtractor._build_text(words)

        assert result == "Comprovante de Pagamento"

    def test_build_text_orders_lines_from_top_to_bottom(self):
        words = [
            OcrWord(
                text="Segunda",
                left=10,
                top=50,
                width=60,
                height=20,
                confidence=95.0,
            ),
            OcrWord(
                text="Primeira",
                left=10,
                top=10,
                width=60,
                height=20,
                confidence=95.0,
            ),
        ]

        result = ImageExtractor._build_text(words)

        assert result == "Primeira\nSegunda"

    def test_build_text_respects_line_tolerance(self):
        words = [
            OcrWord(
                text="Primeira",
                left=10,
                top=10,
                width=60,
                height=20,
                confidence=95.0,
            ),
            OcrWord(
                text="Palavra",
                left=80,
                top=20,
                width=60,
                height=20,
                confidence=95.0,
            ),
        ]

        result = ImageExtractor._build_text(words)

        assert result == "Primeira Palavra"

    def test_build_text_does_not_merge_lines_outside_tolerance(self):
        words = [
            OcrWord(
                text="Primeira",
                left=10,
                top=10,
                width=60,
                height=20,
                confidence=95.0,
            ),
            OcrWord(
                text="Segunda",
                left=10,
                top=31,
                width=60,
                height=20,
                confidence=95.0,
            ),
        ]

        result = ImageExtractor._build_text(words)

        assert result == "Primeira\nSegunda"

    def test_find_line_returns_matching_line(self):
        first_word = OcrWord(
            text="CAIXA",
            left=10,
            top=10,
            width=50,
            height=20,
            confidence=95.0,
        )

        lines = [[first_word]]

        word = OcrWord(
            text="Pagamento",
            left=70,
            top=11,
            width=80,
            height=20,
            confidence=95.0,
        )

        result = ImageExtractor._find_line(lines, word)

        assert result is lines[0]

    def test_find_line_returns_none_when_word_is_outside_tolerance(self):
        first_word = OcrWord(
            text="CAIXA",
            left=10,
            top=10,
            width=50,
            height=20,
            confidence=95.0,
        )

        lines = [[first_word]]

        word = OcrWord(
            text="Pagamento",
            left=70,
            top=30,
            width=80,
            height=20,
            confidence=95.0,
        )

        result = ImageExtractor._find_line(lines, word)

        assert result is None
