"""Calendar grid detection service using OpenCV."""
import cv2
import numpy as np
from typing import List, Tuple, Optional
from dataclasses import dataclass


@dataclass
class CellBoundary:
    """Represents a detected calendar cell."""
    x: int
    y: int
    width: int
    height: int
    row: int
    col: int

    @property
    def center(self) -> Tuple[int, int]:
        """Get center point of cell."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        """Get area of cell."""
        return self.width * self.height

    def extract_from_image(self, image: np.ndarray, padding: int = 5) -> np.ndarray:
        """Extract cell region from image with optional padding."""
        h, w = image.shape[:2]
        x1 = max(0, self.x + padding)
        y1 = max(0, self.y + padding)
        x2 = min(w, self.x + self.width - padding)
        y2 = min(h, self.y + self.height - padding)
        return image[y1:y2, x1:x2]


class GridDetector:
    """Detects calendar grid structure from images."""

    def __init__(self, expected_cols: int = 7, expected_rows: int = 6):
        """
        Initialize grid detector.

        Args:
            expected_cols: Expected number of columns (days per week)
            expected_rows: Expected number of rows (weeks)
        """
        self.expected_cols = expected_cols
        self.expected_rows = expected_rows

    def detect_grid(self, image: np.ndarray) -> List[CellBoundary]:
        """
        Detect calendar grid cells from an image.

        Args:
            image: Input image in BGR format

        Returns:
            List of detected cell boundaries
        """
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # Try multiple detection methods
        cells = self._detect_via_lines(gray, image.shape)

        if len(cells) < self.expected_cols:
            # Fallback: try contour-based detection
            cells = self._detect_via_contours(gray, image.shape)

        if len(cells) < self.expected_cols:
            # Final fallback: create uniform grid
            cells = self._create_uniform_grid(image.shape)

        return cells

    def _detect_via_lines(self, gray: np.ndarray, shape: tuple) -> List[CellBoundary]:
        """Detect grid using line detection."""
        height, width = shape[:2]

        # Apply adaptive threshold
        thresh = cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            15, 2
        )

        # Detect horizontal lines
        horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (width // 10, 1))
        horizontal_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, horizontal_kernel)

        # Detect vertical lines
        vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, height // 10))
        vertical_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, vertical_kernel)

        # Find line positions
        h_positions = self._find_line_positions(horizontal_lines, axis=0)
        v_positions = self._find_line_positions(vertical_lines, axis=1)

        # Create cells from line intersections
        cells = self._create_cells_from_lines(h_positions, v_positions, height, width)

        return cells

    def _find_line_positions(self, line_image: np.ndarray, axis: int) -> List[int]:
        """Find positions of detected lines."""
        # Sum along axis to find line positions
        projection = np.sum(line_image, axis=axis)

        # Find peaks (line positions)
        threshold = np.max(projection) * 0.3
        positions = []

        in_peak = False
        peak_start = 0

        for i, val in enumerate(projection):
            if val > threshold and not in_peak:
                in_peak = True
                peak_start = i
            elif val <= threshold and in_peak:
                in_peak = False
                positions.append((peak_start + i) // 2)

        return positions

    def _create_cells_from_lines(
        self,
        h_positions: List[int],
        v_positions: List[int],
        height: int,
        width: int
    ) -> List[CellBoundary]:
        """Create cell boundaries from line positions."""
        cells = []

        # Add boundaries at edges if needed
        if not h_positions or h_positions[0] > height * 0.1:
            h_positions = [0] + h_positions
        if not h_positions or h_positions[-1] < height * 0.9:
            h_positions = h_positions + [height]

        if not v_positions or v_positions[0] > width * 0.1:
            v_positions = [0] + v_positions
        if not v_positions or v_positions[-1] < width * 0.9:
            v_positions = v_positions + [width]

        # Create cells from grid intersections
        for row_idx, (y1, y2) in enumerate(zip(h_positions[:-1], h_positions[1:])):
            for col_idx, (x1, x2) in enumerate(zip(v_positions[:-1], v_positions[1:])):
                cell = CellBoundary(
                    x=x1,
                    y=y1,
                    width=x2 - x1,
                    height=y2 - y1,
                    row=row_idx,
                    col=col_idx
                )
                cells.append(cell)

        return cells

    def _detect_via_contours(self, gray: np.ndarray, shape: tuple) -> List[CellBoundary]:
        """Detect grid using contour detection."""
        height, width = shape[:2]

        # Apply threshold
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

        # Filter contours by size (looking for cell-sized rectangles)
        min_cell_area = (width * height) / (self.expected_cols * self.expected_rows * 4)
        max_cell_area = (width * height) / (self.expected_cols * self.expected_rows) * 2

        candidate_cells = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_cell_area < area < max_cell_area:
                x, y, w, h = cv2.boundingRect(contour)
                aspect_ratio = w / h if h > 0 else 0

                # Calendar cells are typically wider than tall or square
                if 0.5 < aspect_ratio < 3:
                    candidate_cells.append((x, y, w, h))

        # Sort and organize into grid
        cells = self._organize_into_grid(candidate_cells)

        return cells

    def _organize_into_grid(self, candidates: List[Tuple[int, int, int, int]]) -> List[CellBoundary]:
        """Organize detected rectangles into a grid structure."""
        if not candidates:
            return []

        # Sort by y, then x
        candidates.sort(key=lambda c: (c[1], c[0]))

        cells = []
        current_row = 0
        current_y = candidates[0][1] if candidates else 0
        row_threshold = candidates[0][3] * 0.5 if candidates else 50

        for x, y, w, h in candidates:
            # Check if this is a new row
            if y - current_y > row_threshold:
                current_row += 1
                current_y = y

            col = len([c for c in cells if c.row == current_row])

            cell = CellBoundary(
                x=x, y=y, width=w, height=h,
                row=current_row, col=col
            )
            cells.append(cell)

        return cells

    def _create_uniform_grid(self, shape: tuple) -> List[CellBoundary]:
        """Create a uniform grid as fallback."""
        height, width = shape[:2]

        # Assume calendar takes most of the image
        margin_x = int(width * 0.05)
        margin_y = int(height * 0.15)  # More margin at top for month header

        grid_width = width - 2 * margin_x
        grid_height = height - margin_y - int(height * 0.05)

        cell_width = grid_width // self.expected_cols
        cell_height = grid_height // self.expected_rows

        cells = []
        for row in range(self.expected_rows):
            for col in range(self.expected_cols):
                cell = CellBoundary(
                    x=margin_x + col * cell_width,
                    y=margin_y + row * cell_height,
                    width=cell_width,
                    height=cell_height,
                    row=row,
                    col=col
                )
                cells.append(cell)

        return cells

    def visualize_grid(self, image: np.ndarray, cells: List[CellBoundary]) -> np.ndarray:
        """
        Draw detected grid on image for debugging.

        Args:
            image: Original image
            cells: Detected cells

        Returns:
            Image with grid overlay
        """
        result = image.copy()

        for cell in cells:
            # Draw rectangle
            cv2.rectangle(
                result,
                (cell.x, cell.y),
                (cell.x + cell.width, cell.y + cell.height),
                (0, 255, 0), 2
            )

            # Draw cell index
            cv2.putText(
                result,
                f"{cell.row},{cell.col}",
                (cell.x + 5, cell.y + 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (255, 0, 0), 1
            )

        return result
