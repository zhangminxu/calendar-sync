"""EasyOCR service - better handling of colored backgrounds than Tesseract."""
import cv2
import numpy as np
from typing import List, Optional
from pathlib import Path
import io

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False


class EasyOCRService:
    """Text extraction using EasyOCR - handles colored backgrounds well."""

    _shared_reader = None

    def __init__(self, languages: Optional[List[str]] = None):
        if not EASYOCR_AVAILABLE:
            raise ImportError("easyocr is required. Install with: pip install easyocr")

        self.languages = languages or ['en']
        # Reuse a single reader instance across requests
        if EasyOCRService._shared_reader is None:
            EasyOCRService._shared_reader = easyocr.Reader(self.languages, gpu=False)
        self.reader = EasyOCRService._shared_reader

    def extract_text(self, image: np.ndarray) -> str:
        """
        Extract text from image using EasyOCR.

        Args:
            image: Input image (BGR or grayscale numpy array)

        Returns:
            Extracted text as string
        """
        # EasyOCR works with BGR or RGB numpy arrays directly
        results = self.reader.readtext(image, detail=1, paragraph=False)

        # Sort results by vertical position (top to bottom), then left to right
        results.sort(key=lambda r: (r[0][0][1], r[0][0][0]))

        # Group results into lines based on y-coordinate proximity
        lines = self._group_into_lines(results)

        # Join lines
        text_lines = []
        for line in lines:
            line_text = ' '.join([r[1] for r in line])
            text_lines.append(line_text)

        return '\n'.join(text_lines)

    def extract_text_from_bytes(self, image_bytes: bytes, filename: str) -> str:
        """
        Extract text from image bytes.

        Args:
            image_bytes: Raw image file bytes
            filename: Original filename for format detection

        Returns:
            Extracted text
        """
        ext = Path(filename).suffix.lower()

        if ext == '.pdf':
            return self._extract_from_pdf_bytes(image_bytes)

        # Load image from bytes
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if image is None:
            raise ValueError(f"Could not decode image from bytes")

        return self.extract_text(image)

    def _extract_from_pdf_bytes(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes by converting to images first."""
        from app.services.image_processor import ImageProcessor

        processor = ImageProcessor()
        images = processor.load_pdf_from_bytes(pdf_bytes)

        all_text = []
        for image in images:
            text = self.extract_text(image)
            if text:
                all_text.append(text)

        return '\n'.join(all_text)

    def _group_into_lines(self, results, y_threshold: int = 15) -> List[List]:
        """
        Group OCR results into lines based on y-coordinate proximity.

        Args:
            results: EasyOCR results [(bbox, text, confidence), ...]
            y_threshold: Maximum y-distance to consider same line

        Returns:
            List of lines, each line is a list of results
        """
        if not results:
            return []

        lines = []
        current_line = [results[0]]
        current_y = results[0][0][0][1]  # Top-left y coordinate

        for result in results[1:]:
            result_y = result[0][0][1]

            if abs(result_y - current_y) < y_threshold:
                # Same line
                current_line.append(result)
            else:
                # New line
                # Sort current line by x position
                current_line.sort(key=lambda r: r[0][0][0])
                lines.append(current_line)
                current_line = [result]
                current_y = result_y

        # Don't forget the last line
        current_line.sort(key=lambda r: r[0][0][0])
        lines.append(current_line)

        return lines
