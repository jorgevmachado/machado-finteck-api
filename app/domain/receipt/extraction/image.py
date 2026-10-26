from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image
import pytesseract
from pytesseract import Output


@dataclass(frozen=True)
class OcrWord:
    text: str
    left: int
    top: int
    width: int
    height: int
    confidence: float

    @property
    def center_y(self) -> float:
        return self.top + (self.height / 2)


class ImageExtractor:
    OCR_LANGUAGE = "por"
    LINE_TOLERANCE = 10

    @classmethod
    def extract(cls, content: bytes) -> str:
        image = Image.open(io.BytesIO(content))

        words = cls._extract_words(image)

        return cls._build_text(words)

    @classmethod
    def extract_image(cls, image: Image.Image) -> str:
        words = cls._extract_words(image)
        return cls._build_text(words)

    @classmethod
    def _extract_words(cls, image: Image.Image) -> list[OcrWord]:
        data = pytesseract.image_to_data(
            image,
            lang=cls.OCR_LANGUAGE,
            output_type=Output.DICT,
        )

        words: list[OcrWord] = []

        for index, text in enumerate(data["text"]):
            text = text.strip()

            if not text:
                continue

            try:
                confidence = float(data["conf"][index])
            except (TypeError, ValueError):
                continue

            if confidence < 0:
                continue

            words.append(
                OcrWord(
                    text=text,
                    left=int(data["left"][index]),
                    top=int(data["top"][index]),
                    width=int(data["width"][index]),
                    height=int(data["height"][index]),
                    confidence=confidence,
                )
            )

        return words

    @classmethod
    def _build_text(cls, words: list[OcrWord]) -> str:
        if not words:
            return ""

        lines: list[list[OcrWord]] = []

        for word in sorted(words, key=lambda item: (item.top, item.left)):
            line = cls._find_line(lines, word)

            if line is None:
                lines.append([word])
                continue

            line.append(word)

        lines.sort(key=lambda line: min(word.top for word in line))

        result: list[str] = []

        for line in lines:
            line.sort(key=lambda word: word.left)

            result.append(" ".join(word.text for word in line))

        return "\n".join(result).strip()

    @classmethod
    def _find_line(
        cls,
        lines: list[list[OcrWord]],
        word: OcrWord,
    ) -> list[OcrWord] | None:
        for line in reversed(lines):
            reference = line[-1]

            if abs(reference.center_y - word.center_y) <= cls.LINE_TOLERANCE:
                return line

        return None
