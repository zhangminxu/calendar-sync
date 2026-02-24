"""Event parsing service for extracting events from OCR text."""
import re
from datetime import date, time
from typing import List, Optional, Tuple
from dataclasses import dataclass

from app.models.event import CalendarEvent


@dataclass
class ParsedTime:
    """Represents a parsed time value."""
    hour: int
    minute: int

    def to_time(self) -> time:
        """Convert to datetime.time object."""
        return time(self.hour, self.minute)


class EventParser:
    """Parses calendar events from OCR-extracted text."""

    # Time patterns (order matters - more specific patterns first)
    TIME_PATTERNS = [
        # 9:00 AM - 10:00 PM (time range with AM/PM)
        r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?\s*[-–]\s*(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)?',
        # 9:00 - 10:00 (time range without AM/PM)
        r'(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})',
        # 9 AM - 10 PM (hour range with AM/PM)
        r'(\d{1,2})\s*(AM|PM|am|pm)\s*[-–]\s*(\d{1,2})\s*(AM|PM|am|pm)',
        # 9:00 AM or 9:00 PM (single time with AM/PM)
        r'(\d{1,2}):(\d{2})\s*(AM|PM|am|pm)',
        # 9 AM or 9 PM (hour only with AM/PM)
        r'(\d{1,2})\s*(AM|PM|am|pm)',
        # 14:30 (24-hour format)
        r'(\d{1,2}):(\d{2})(?!\s*[-–])',
    ]

    def __init__(self):
        """Initialize event parser with compiled patterns."""
        self.time_patterns = [re.compile(p) for p in self.TIME_PATTERNS]

    def parse_cell_text(
        self,
        text: str,
        cell_date: date,
        confidence: float = 1.0
    ) -> List[CalendarEvent]:
        """
        Parse events from a calendar cell's text.

        Args:
            text: OCR-extracted text from the cell
            cell_date: Date for this calendar cell
            confidence: OCR confidence score

        Returns:
            List of parsed CalendarEvent objects
        """
        if not text or not text.strip():
            return []

        events = []

        # Split text into potential event lines
        lines = self._split_into_events(text)

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Try to extract time information
            time_info = self._extract_time(line)

            if time_info:
                start_time, end_time, remaining_text = time_info
                title = remaining_text.strip() or "Event"
            else:
                start_time = None
                end_time = None
                title = line

            # Clean up the title
            title = self._clean_title(title)

            if title:
                event = CalendarEvent(
                    title=title,
                    event_date=cell_date,
                    start_time=start_time,
                    end_time=end_time,
                    confidence=confidence
                )
                events.append(event)

        return events

    def _split_into_events(self, text: str) -> List[str]:
        """Split text into individual event strings."""
        # Split by newlines
        lines = text.split('\n')

        # Also split by common separators
        result = []
        for line in lines:
            # Split by bullet points or dashes at start of items
            parts = re.split(r'(?:^|\s)[•·\-]\s+', line)
            result.extend(parts)

        # Filter empty strings
        return [line.strip() for line in result if line.strip()]

    def _extract_time(
        self,
        text: str
    ) -> Optional[Tuple[time, Optional[time], str]]:
        """
        Extract time information from text.

        Returns:
            Tuple of (start_time, end_time, remaining_text) or None
        """
        for i, pattern in enumerate(self.time_patterns):
            match = pattern.search(text)
            if match:
                result = self._parse_time_match(match, i)
                if result:
                    start, end = result
                    # Remove matched time from text
                    remaining = text[:match.start()] + text[match.end():]
                    return (start, end, remaining.strip())

        return None

    def _parse_time_match(
        self,
        match: re.Match,
        pattern_index: int
    ) -> Optional[Tuple[time, Optional[time]]]:
        """Parse a regex match into time objects based on pattern index."""
        groups = match.groups()

        try:
            if pattern_index == 0:
                # Time range with minutes and optional AM/PM
                # Groups: (start_h, start_m, start_ampm, end_h, end_m, end_ampm)
                start = self._parse_hm_ampm(groups[0], groups[1], groups[2] or groups[5])
                end = self._parse_hm_ampm(groups[3], groups[4], groups[5])
                return (start, end)

            elif pattern_index == 1:
                # Time range without AM/PM (assume 24-hour or context)
                # Groups: (start_h, start_m, end_h, end_m)
                start = self._parse_hm(groups[0], groups[1])
                end = self._parse_hm(groups[2], groups[3])
                return (start, end)

            elif pattern_index == 2:
                # Hour range with AM/PM
                # Groups: (start_h, start_ampm, end_h, end_ampm)
                start = self._parse_h_ampm(groups[0], groups[1])
                end = self._parse_h_ampm(groups[2], groups[3])
                return (start, end)

            elif pattern_index == 3:
                # Single time with minutes and AM/PM
                # Groups: (h, m, ampm)
                start = self._parse_hm_ampm(groups[0], groups[1], groups[2])
                return (start, None)

            elif pattern_index == 4:
                # Single hour with AM/PM
                # Groups: (h, ampm)
                start = self._parse_h_ampm(groups[0], groups[1])
                return (start, None)

            elif pattern_index == 5:
                # 24-hour format
                # Groups: (h, m)
                start = self._parse_hm(groups[0], groups[1])
                return (start, None)

        except (ValueError, IndexError):
            pass

        return None

    def _parse_hm_ampm(
        self,
        hour_str: str,
        minute_str: str,
        ampm: Optional[str]
    ) -> time:
        """Parse hour, minute, and AM/PM into time object."""
        hour = int(hour_str)
        minute = int(minute_str)

        if ampm:
            ampm = ampm.upper()
            if ampm == 'PM' and hour != 12:
                hour += 12
            elif ampm == 'AM' and hour == 12:
                hour = 0

        return time(hour % 24, minute)

    def _parse_h_ampm(self, hour_str: str, ampm: str) -> time:
        """Parse hour and AM/PM into time object."""
        return self._parse_hm_ampm(hour_str, '0', ampm)

    def _parse_hm(self, hour_str: str, minute_str: str) -> time:
        """Parse hour and minute (24-hour format) into time object."""
        hour = int(hour_str)
        minute = int(minute_str)

        # If hour is 1-7 without AM/PM, assume PM for typical calendar events
        if 1 <= hour <= 7:
            hour += 12

        return time(hour % 24, minute)

    def _clean_title(self, title: str) -> str:
        """Clean up event title."""
        # Remove extra whitespace
        title = ' '.join(title.split())

        # Remove common OCR artifacts
        title = re.sub(r'[|_]{2,}', '', title)

        # Remove leading/trailing punctuation
        title = title.strip('.,;:-_|')

        # Remove day numbers that might have been included
        title = re.sub(r'^\d{1,2}\s+', '', title)

        return title.strip()

    def parse_bulk_text(
        self,
        text: str,
        year: int,
        month: int
    ) -> List[CalendarEvent]:
        """
        Parse events from bulk calendar text (without grid detection).

        This is useful when grid detection fails and we have raw OCR text.

        Args:
            text: Full OCR text from calendar image
            year: Calendar year
            month: Calendar month

        Returns:
            List of parsed CalendarEvent objects
        """
        events = []

        # Look for date markers (e.g., "15" followed by event text)
        date_pattern = re.compile(r'\b(\d{1,2})\b\s*[-:]?\s*(.+?)(?=\b\d{1,2}\b\s*[-:]|\Z)', re.DOTALL)

        for match in date_pattern.finditer(text):
            try:
                day = int(match.group(1))
                if 1 <= day <= 31:
                    event_text = match.group(2).strip()
                    try:
                        event_date = date(year, month, day)
                        cell_events = self.parse_cell_text(event_text, event_date)
                        events.extend(cell_events)
                    except ValueError:
                        continue
            except ValueError:
                continue

        return events
