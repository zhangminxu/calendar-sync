"""Event data models."""
from dataclasses import dataclass, field
from datetime import datetime, date, time
from typing import Optional
from enum import Enum


class EventType(Enum):
    """Type of calendar event."""
    TIMED = "timed"
    ALL_DAY = "all_day"


@dataclass
class CalendarEvent:
    """Represents a calendar event extracted from an image."""

    title: str
    event_date: date
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    event_type: EventType = EventType.TIMED
    description: str = ""
    location: str = ""
    confidence: float = 1.0  # OCR confidence score

    def __post_init__(self):
        """Set event type based on time presence."""
        if self.start_time is None:
            self.event_type = EventType.ALL_DAY

    @property
    def is_all_day(self) -> bool:
        """Check if this is an all-day event."""
        return self.event_type == EventType.ALL_DAY

    def to_google_event(self, timezone: str = "America/Los_Angeles") -> dict:
        """Convert to Google Calendar API event format."""
        event = {
            "summary": self.title,
            "description": self.description,
            "location": self.location,
        }

        if self.is_all_day:
            # All-day event uses date format
            event["start"] = {"date": self.event_date.isoformat()}
            event["end"] = {"date": self.event_date.isoformat()}
        else:
            # Timed event uses datetime format
            start_dt = datetime.combine(self.event_date, self.start_time)
            event["start"] = {
                "dateTime": start_dt.isoformat(),
                "timeZone": timezone,
            }

            if self.end_time:
                end_dt = datetime.combine(self.event_date, self.end_time)
            else:
                # Default to 1 hour duration
                end_dt = datetime.combine(
                    self.event_date,
                    time(self.start_time.hour + 1, self.start_time.minute)
                )

            event["end"] = {
                "dateTime": end_dt.isoformat(),
                "timeZone": timezone,
            }

        return event

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "title": self.title,
            "date": self.event_date.isoformat(),
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "is_all_day": self.is_all_day,
            "description": self.description,
            "location": self.location,
            "confidence": self.confidence,
        }


@dataclass
class CalendarGrid:
    """Represents the detected calendar grid structure."""

    rows: int = 6  # Typical calendar has 5-6 week rows
    cols: int = 7  # 7 days per week
    cell_boundaries: list = field(default_factory=list)  # List of (x, y, w, h) tuples
    first_day_offset: int = 0  # Day of week for the 1st of the month (0=Sunday)

    def get_date_for_cell(self, row: int, col: int, year: int, month: int) -> Optional[date]:
        """Calculate the date for a given cell position."""
        from calendar import monthrange

        # Calculate day number
        day_num = (row * 7 + col) - self.first_day_offset + 1

        # Check if day is valid for this month
        _, days_in_month = monthrange(year, month)

        if 1 <= day_num <= days_in_month:
            return date(year, month, day_num)
        return None
