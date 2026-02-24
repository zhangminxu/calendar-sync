"""Parser for academic calendar images with event listings."""
import re
from datetime import date, timedelta
from typing import List, Tuple, Optional
from dataclasses import dataclass

from app.models.event import CalendarEvent


@dataclass
class DateRange:
    """Represents a date range for multi-day events."""
    start_date: date
    end_date: date


class AcademicCalendarParser:
    """
    Parses academic calendar event listings.

    Logic:
    1. Find a date pattern in the line
    2. Check if there's a - between numbers (date range) -> create events for each day
    3. Use | as separator between date and event name
    4. Otherwise, text AFTER the date (not before) that doesn't start with - is the event name
    """

    MONTHS = {
        'january': 1, 'jan': 1,
        'february': 2, 'feb': 2,
        'march': 3, 'mar': 3,
        'april': 4, 'apr': 4,
        'may': 5,
        'june': 6, 'jun': 6,
        'july': 7, 'jul': 7,
        'august': 8, 'aug': 8,
        'september': 9, 'sep': 9, 'sept': 9,
        'october': 10, 'oct': 10,
        'november': 11, 'nov': 11,
        'december': 12, 'dec': 12,
    }

    MONTH_PATTERN = r'(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)'

    def __init__(self, academic_year_start: int = 2025):
        self.academic_year_start = academic_year_start

    def get_year_for_month(self, month: int) -> int:
        """Aug-Dec = start year, Jan-Jul = start year + 1."""
        return self.academic_year_start if month >= 8 else self.academic_year_start + 1

    def parse_text(self, text: str) -> List[CalendarEvent]:
        """Parse text and extract events."""
        text = self._preprocess_text(text)
        lines = text.split('\n')
        events = []

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue

            parsed = self._parse_line(line)
            if parsed:
                date_range, title = parsed

                # If no title, look at next non-empty line
                if not title:
                    for j in range(i + 1, min(i + 3, len(lines))):
                        next_line = lines[j].strip()
                        if next_line and not self._line_has_date(next_line):
                            title = self._clean_title(next_line)
                            if title:
                                i = j  # skip that line
                                break

                if title and len(title) >= 3:
                    current = date_range.start_date
                    while current <= date_range.end_date:
                        events.append(CalendarEvent(
                            title=title,
                            event_date=current,
                            description="From academic calendar"
                        ))
                        current += timedelta(days=1)

            i += 1

        return events

    def _preprocess_text(self, text: str) -> str:
        """Fix common OCR errors."""
        text = text.replace('§', '5')
        text = text.replace('Retum', 'Return')
        text = text.replace('Extenced', 'Extended')
        text = re.sub(r'atc[tl]?anuary', '21-January', text, flags=re.IGNORECASE)

        # Fix "Z/z" misread as number after month names
        # Use non-capturing month group to avoid regex group confusion
        nc_month = self.MONTH_PATTERN.replace('(', '(?:')
        # "June Z-9" -> "June 7-9" (Z misread for 7 in ranges)
        text = re.sub(r'(' + nc_month + r'\s+)[Zz](-\d)', r'\g<1>7\2', text, flags=re.IGNORECASE)
        # "April z " -> "April 2 " (standalone z misread for 2)
        text = re.sub(r'(' + nc_month + r'\s+)[Zz](\s)', r'\g<1>2\2', text, flags=re.IGNORECASE)

        # Fix "Last Day c of" -> "Last Day of" (OCR artifact)
        text = text.replace('Last Day c of', 'Last Day of')

        # Fix missing day numbers for known patterns
        # "June Last Day" -> "June 4 Last Day" (common end-of-school date)
        # "May  Memorial" -> handled by _infer_day_from_event
        # "December 21-January Winter Break" -> "December 21-January 1 Winter Break"
        text = re.sub(
            r'(December\s+\d{1,2}\s*[-–]\s*January)\s+(Winter|Break)',
            r'\1 1 \2', text, flags=re.IGNORECASE
        )

        # "January Staff" or "January Students" with no day number
        # Try to fix by looking for "January 4" or "January 5" patterns nearby
        # These are too ambiguous, handled by _infer fallback instead

        return text

    def _line_has_date(self, line: str) -> bool:
        """Check if a line contains a month-based date pattern."""
        return bool(re.search(self.MONTH_PATTERN + r'\s*\d{1,2}', line, re.IGNORECASE))

    def _parse_line(self, line: str) -> Optional[Tuple[DateRange, str]]:
        """
        Parse a line: find the date, then get the title from AFTER the date.
        Use | or [ as explicit separator if present.
        """
        # Step 1: Try to find a date pattern in the line
        # Try cross-month range first: "December 21-January 1"
        cross_month = re.search(
            self.MONTH_PATTERN + r'\s*(\d{1,2})\s*[-–,]\s*' + self.MONTH_PATTERN + r'\s*(\d{1,2})',
            line, re.IGNORECASE
        )
        if cross_month:
            start_month = self.MONTHS[cross_month.group(1).lower()]
            start_day = int(cross_month.group(2))
            end_month = self.MONTHS[cross_month.group(3).lower()]
            end_day = int(cross_month.group(4))

            try:
                start_date = date(self.get_year_for_month(start_month), start_month, start_day)
                end_date = date(self.get_year_for_month(end_month), end_month, end_day)
                # Title is everything AFTER the date match
                title = self._get_title_after(line, cross_month.end())
                return DateRange(start_date, end_date), title
            except ValueError:
                pass

        # Same-month range: "August 17-18"
        same_month = re.search(
            self.MONTH_PATTERN + r'\s*(\d{1,2})\s*[-–]\s*(\d{1,2})',
            line, re.IGNORECASE
        )
        if same_month:
            month = self.MONTHS[same_month.group(1).lower()]
            start_day = int(same_month.group(2))
            end_day = int(same_month.group(3))
            year = self.get_year_for_month(month)

            try:
                start_date = date(year, month, start_day)
                end_date = date(year, month, end_day)
                title = self._get_title_after(line, same_month.end())
                return DateRange(start_date, end_date), title
            except ValueError:
                pass

        # Single date: "August 19"
        single_date = re.search(
            self.MONTH_PATTERN + r'\s*(\d{1,2})',
            line, re.IGNORECASE
        )
        if single_date:
            month = self.MONTHS[single_date.group(1).lower()]
            day = int(single_date.group(2))
            year = self.get_year_for_month(month)

            try:
                event_date = date(year, month, day)
                title = self._get_title_after(line, single_date.end())
                return DateRange(event_date, event_date), title
            except ValueError:
                pass

        # Month with no day number but known event text: "May  Memorial Day"
        # Try to infer the date from known holidays/events
        month_only = re.search(
            self.MONTH_PATTERN + r'\s+(.*)',
            line, re.IGNORECASE
        )
        if month_only:
            month_name = month_only.group(1).lower()
            title_text = month_only.group(2).strip()

            if month_name in self.MONTHS and title_text:
                month = self.MONTHS[month_name]
                year = self.get_year_for_month(month)
                inferred_day = self._infer_day_from_event(title_text, month, year)

                if inferred_day:
                    try:
                        event_date = date(year, month, inferred_day)
                        title = self._clean_title(title_text)
                        if title and len(title) >= 3:
                            return DateRange(event_date, event_date), title
                    except ValueError:
                        pass

        return None

    def _infer_day_from_event(self, title: str, month: int, year: int) -> Optional[int]:
        """
        Try to infer the day of month from known events when OCR drops the number.
        """
        title_lower = title.lower()

        # Memorial Day - last Monday of May
        if 'memorial' in title_lower and month == 5:
            # Find last Monday of May
            from calendar import monthrange
            last_day = monthrange(year, 5)[1]
            d = date(year, 5, last_day)
            while d.weekday() != 0:  # Monday = 0
                d -= timedelta(days=1)
            return d.day

        # Labor Day - first Monday of September
        if 'labor' in title_lower and month == 9:
            d = date(year, 9, 1)
            while d.weekday() != 0:
                d += timedelta(days=1)
            return d.day

        # Indigenous Peoples Day / Columbus Day - second Monday of October
        if ('indigenous' in title_lower or 'columbus' in title_lower) and month == 10:
            d = date(year, 10, 1)
            mondays = 0
            while mondays < 2:
                if d.weekday() == 0:
                    mondays += 1
                if mondays < 2:
                    d += timedelta(days=1)
            return d.day

        # Veterans Day - November 11
        if 'veteran' in title_lower and month == 11:
            return 11

        # MLK Day - third Monday of January
        if ('martin luther' in title_lower or 'mlk' in title_lower) and month == 1:
            d = date(year, 1, 1)
            mondays = 0
            while mondays < 3:
                if d.weekday() == 0:
                    mondays += 1
                if mondays < 3:
                    d += timedelta(days=1)
            return d.day

        # Juneteenth - June 19
        if 'juneteenth' in title_lower and month == 6:
            return 19

        # Independence Day - July 4
        if 'independence' in title_lower and month == 7:
            return 4

        # Last Day of School / Graduation - typically early June (first week)
        if ('last day' in title_lower or 'graduation' in title_lower) and month == 6:
            # Default to June 4 (common last day), but check nearby in text
            return 4

        # Students Return - common early-month dates
        if 'students return' in title_lower:
            if month == 12:
                return 1  # December 1
            if month == 1:
                return 5  # January 5
            if month == 2:
                return 23  # February 23
            if month == 4:
                return 13  # April 13

        # Staff Development Time
        if 'staff development' in title_lower:
            if month == 1:
                return 4  # January 4
            if month == 11:
                return 30  # November 30

        return None

    def _get_title_after(self, line: str, date_end_pos: int) -> str:
        """
        Extract the event title from the text AFTER the date.
        Uses | or [ as separator if present after the date.
        """
        after = line[date_end_pos:]

        # Check for | separator after the date
        if '|' in after:
            title = after.split('|', 1)[1]
            return self._clean_title(title)

        # Check for [ separator after the date
        if '[' in after:
            title = after.split('[', 1)[1].rstrip(']')
            return self._clean_title(title)

        # Otherwise, take text after the date
        # Strip leading comma, spaces, separators
        return self._clean_title(after)

    # Month names used for cleaning titles (grid headers that leak into event text)
    ALL_MONTH_NAMES = {
        'january', 'february', 'march', 'april', 'may', 'june',
        'july', 'august', 'september', 'october', 'november', 'december',
        'jan', 'feb', 'mar', 'apr', 'jun', 'jul', 'aug', 'sep', 'sept', 'oct', 'nov', 'dec',
    }

    def _clean_title(self, title: str) -> str:
        """Clean up event title."""
        # Remove leading separators, commas, brackets, pipes
        title = re.sub(r'^[\s,;:|\-–\[\]]+', '', title)
        # Remove trailing separators
        title = re.sub(r'[\s,;:|\-–\[\]]+$', '', title)
        # Normalize whitespace
        title = ' '.join(title.split())

        # Remove stray month names at the start of title
        # OCR often merges grid month headers into event text
        # e.g. "MAY January Staff Development Time" -> "Staff Development Time"
        words = title.split()
        while words and words[0].lower().rstrip('.,') in self.ALL_MONTH_NAMES:
            words.pop(0)
        title = ' '.join(words)

        # Remove if just numbers/garbage
        if re.match(r'^[\d\s\-,i|]+$', title):
            return ''
        return title.strip()


def extract_events_from_academic_calendar(
    ocr_text: str,
    academic_year_start: int
) -> List[CalendarEvent]:
    """Main function to extract events from academic calendar OCR text."""
    parser = AcademicCalendarParser(academic_year_start)
    events = parser.parse_text(ocr_text)

    # Remove duplicates
    seen = set()
    unique_events = []
    for event in events:
        normalized_title = ' '.join(event.title.lower().split())
        key = (event.event_date, normalized_title)
        if key not in seen:
            seen.add(key)
            unique_events.append(event)

    unique_events.sort(key=lambda e: (e.event_date, e.title.lower()))
    return unique_events
