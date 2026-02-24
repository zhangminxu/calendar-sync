"""OCR service using Tesseract with multiple preprocessing strategies."""
import cv2
import numpy as np
from typing import List, Tuple, Optional, Set
from dataclasses import dataclass

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False


@dataclass
class OCRResult:
    """Result from OCR processing."""
    text: str
    confidence: float
    bounding_box: Optional[Tuple[int, int, int, int]] = None


class OCRService:
    """Handles text extraction using Tesseract OCR with multiple strategies."""

    def __init__(self, tesseract_cmd: Optional[str] = None):
        if not TESSERACT_AVAILABLE:
            raise ImportError(
                "pytesseract is required. Install with: pip install pytesseract\n"
                "Also install Tesseract OCR: brew install tesseract (macOS)"
            )

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def extract_text(self, image: np.ndarray, preprocess: bool = True) -> str:
        """
        Extract text using multiple strategies and combine results.
        """
        all_texts = []

        # Strategy 1: Original image with PSM 3 (fully automatic)
        try:
            text1 = pytesseract.image_to_string(image, config='--psm 3')
            if text1.strip():
                all_texts.append(text1.strip())
        except Exception:
            pass

        # Strategy 2: Original image with PSM 6 (uniform block of text)
        try:
            text2 = pytesseract.image_to_string(image, config='--psm 6')
            if text2.strip():
                all_texts.append(text2.strip())
        except Exception:
            pass

        # Strategy 3: Grayscale with light preprocessing
        try:
            gray = self._to_grayscale(image)
            text3 = pytesseract.image_to_string(gray, config='--psm 6')
            if text3.strip():
                all_texts.append(text3.strip())
        except Exception:
            pass

        # Strategy 4: Enhanced contrast
        try:
            enhanced = self._enhance_contrast(image)
            text4 = pytesseract.image_to_string(enhanced, config='--psm 6')
            if text4.strip():
                all_texts.append(text4.strip())
        except Exception:
            pass

        # Strategy 5: Threshold preprocessing
        try:
            thresh = self._threshold_preprocess(image)
            text5 = pytesseract.image_to_string(thresh, config='--psm 6')
            if text5.strip():
                all_texts.append(text5.strip())
        except Exception:
            pass

        # Strategy 6: Scale up image for small text
        try:
            scaled = self._scale_image(image, 2.0)
            text6 = pytesseract.image_to_string(scaled, config='--psm 6')
            if text6.strip():
                all_texts.append(text6.strip())
        except Exception:
            pass

        # Combine all texts and deduplicate lines
        combined = self._combine_texts(all_texts)
        return combined

    def _combine_texts(self, texts: List[str]) -> str:
        """Combine multiple OCR results, keeping unique lines."""
        all_lines: Set[str] = set()
        ordered_lines: List[str] = []

        for text in texts:
            for line in text.split('\n'):
                line = line.strip()
                if line and line not in all_lines:
                    # Check if this line is substantially different from existing
                    is_duplicate = False
                    for existing in all_lines:
                        # Simple similarity check
                        if self._similar_lines(line, existing):
                            is_duplicate = True
                            break

                    if not is_duplicate:
                        all_lines.add(line)
                        ordered_lines.append(line)

        return '\n'.join(ordered_lines)

    def _similar_lines(self, line1: str, line2: str) -> bool:
        """Check if two lines are similar (likely duplicates)."""
        # Normalize for comparison
        l1 = line1.lower().replace(' ', '')
        l2 = line2.lower().replace(' ', '')

        if l1 == l2:
            return True

        # Check if one contains the other
        if len(l1) > 10 and len(l2) > 10:
            if l1 in l2 or l2 in l1:
                return True

        return False

    def _to_grayscale(self, image: np.ndarray) -> np.ndarray:
        """Convert to grayscale."""
        if len(image.shape) == 3:
            return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        return image

    def _enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """Enhance image contrast using CLAHE."""
        gray = self._to_grayscale(image)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)
        return enhanced

    def _threshold_preprocess(self, image: np.ndarray) -> np.ndarray:
        """Apply adaptive thresholding."""
        gray = self._to_grayscale(image)

        # Denoise
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        # Adaptive threshold
        thresh = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2
        )
        return thresh

    def _scale_image(self, image: np.ndarray, scale: float) -> np.ndarray:
        """Scale image by factor."""
        h, w = image.shape[:2]
        new_w = int(w * scale)
        new_h = int(h * scale)
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    def extract_text_with_confidence(
        self,
        image: np.ndarray,
        preprocess: bool = True
    ) -> List[OCRResult]:
        """Extract text with confidence scores."""
        if preprocess:
            image = self._threshold_preprocess(image)

        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

        results = []
        n_boxes = len(data['text'])

        for i in range(n_boxes):
            text = data['text'][i].strip()
            conf = int(data['conf'][i])

            if text and conf > 0:
                result = OCRResult(
                    text=text,
                    confidence=conf / 100.0,
                    bounding_box=(
                        data['left'][i],
                        data['top'][i],
                        data['width'][i],
                        data['height'][i]
                    )
                )
                results.append(result)

        return results

    def extract_from_cell(
        self,
        image: np.ndarray,
        min_confidence: float = 0.3
    ) -> Tuple[str, float]:
        """Extract text from a calendar cell."""
        results = self.extract_text_with_confidence(image, preprocess=True)
        filtered = [r for r in results if r.confidence >= min_confidence]

        if not filtered:
            return "", 0.0

        text = " ".join(r.text for r in filtered)
        avg_confidence = sum(r.confidence for r in filtered) / len(filtered)

        return text, avg_confidence
