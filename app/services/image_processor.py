"""Image processing service for loading PDF and image files."""
import os
from pathlib import Path
from typing import List, Union
import numpy as np
from PIL import Image
import cv2

# pdf2image requires poppler
try:
    from pdf2image import convert_from_path, convert_from_bytes
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False


class ImageProcessor:
    """Handles loading and preprocessing of calendar images."""

    SUPPORTED_IMAGE_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.tiff', '.webp'}

    def __init__(self):
        self.pdf_support = PDF_SUPPORT

    def load_image(self, file_path: Union[str, Path]) -> np.ndarray:
        """
        Load an image file and return as numpy array.

        Args:
            file_path: Path to the image file

        Returns:
            Image as numpy array in BGR format (OpenCV format)
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")

        # Load with PIL first for better format support
        pil_image = Image.open(file_path)

        # Convert to RGB if needed
        if pil_image.mode != 'RGB':
            pil_image = pil_image.convert('RGB')

        # Convert to numpy array and BGR for OpenCV
        image = np.array(pil_image)
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        return image

    def load_pdf(self, file_path: Union[str, Path], dpi: int = 200) -> List[np.ndarray]:
        """
        Load a PDF file and convert pages to images.

        Args:
            file_path: Path to the PDF file
            dpi: Resolution for PDF rendering

        Returns:
            List of images as numpy arrays in BGR format
        """
        if not self.pdf_support:
            raise ImportError(
                "PDF support requires pdf2image and poppler. "
                "Install with: brew install poppler && pip install pdf2image"
            )

        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        # Convert PDF pages to PIL images
        pil_images = convert_from_path(str(file_path), dpi=dpi)

        # Convert to numpy arrays
        images = []
        for pil_image in pil_images:
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            image = np.array(pil_image)
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            images.append(image)

        return images

    def load_pdf_from_bytes(self, pdf_bytes: bytes, dpi: int = 200) -> List[np.ndarray]:
        """
        Load a PDF from bytes and convert pages to images.

        Args:
            pdf_bytes: PDF file content as bytes
            dpi: Resolution for PDF rendering

        Returns:
            List of images as numpy arrays in BGR format
        """
        if not self.pdf_support:
            raise ImportError(
                "PDF support requires pdf2image and poppler. "
                "Install with: brew install poppler && pip install pdf2image"
            )

        # Convert PDF pages to PIL images
        pil_images = convert_from_bytes(pdf_bytes, dpi=dpi)

        # Convert to numpy arrays
        images = []
        for pil_image in pil_images:
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            image = np.array(pil_image)
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            images.append(image)

        return images

    def load_from_bytes(self, image_bytes: bytes, filename: str) -> List[np.ndarray]:
        """
        Load an image or PDF from bytes.

        Args:
            image_bytes: File content as bytes
            filename: Original filename to determine type

        Returns:
            List of images as numpy arrays
        """
        ext = Path(filename).suffix.lower()

        if ext == '.pdf':
            return self.load_pdf_from_bytes(image_bytes)
        elif ext in self.SUPPORTED_IMAGE_FORMATS:
            # Load image from bytes
            import io
            pil_image = Image.open(io.BytesIO(image_bytes))
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            image = np.array(pil_image)
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            return [image]
        else:
            raise ValueError(f"Unsupported file format: {ext}")

    def preprocess_for_ocr(self, image: np.ndarray) -> np.ndarray:
        """
        Preprocess image for better OCR accuracy.

        Args:
            image: Input image in BGR format

        Returns:
            Preprocessed grayscale image
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            11, 2
        )

        # Denoise
        denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)

        return denoised

    def enhance_for_grid_detection(self, image: np.ndarray) -> np.ndarray:
        """
        Enhance image for better grid line detection.

        Args:
            image: Input image in BGR format

        Returns:
            Enhanced grayscale image
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Apply bilateral filter to reduce noise while keeping edges
        filtered = cv2.bilateralFilter(gray, 9, 75, 75)

        # Apply Canny edge detection
        edges = cv2.Canny(filtered, 50, 150)

        # Dilate to connect broken lines
        kernel = np.ones((2, 2), np.uint8)
        dilated = cv2.dilate(edges, kernel, iterations=1)

        return dilated

    @staticmethod
    def is_supported_format(filename: str) -> bool:
        """Check if a filename has a supported format."""
        ext = Path(filename).suffix.lower()
        return ext == '.pdf' or ext in ImageProcessor.SUPPORTED_IMAGE_FORMATS
