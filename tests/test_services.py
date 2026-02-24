"""Tests for calendar sync services."""
import pytest
from datetime import date, time
from unittest.mock import Mock, patch
import numpy as np

from app.models.event import CalendarEvent, EventType
from app.services.event_parser import EventParser
from app.services.academic_calendar_parser import AcademicCalendarParser, extract_events_from_academic_calendar
from app.services.grid_detector import GridDetector, CellBoundary


class TestCalendarEvent:
    """Tests for CalendarEvent model."""

    def test_all_day_event(self):
        """Test all-day event detection."""
        event = CalendarEvent(
            title="Meeting",
            event_date=date(2024, 3, 15)
        )
        assert event.is_all_day
        assert event.event_type == EventType.ALL_DAY

    def test_timed_event(self):
        """Test timed event."""
        event = CalendarEvent(
            title="Meeting",
            event_date=date(2024, 3, 15),
            start_time=time(9, 0),
            end_time=time(10, 0)
        )
        assert not event.is_all_day
        assert event.event_type == EventType.TIMED

    def test_to_google_event_all_day(self):
        """Test Google Calendar format for all-day event."""
        event = CalendarEvent(
            title="Holiday",
            event_date=date(2024, 3, 15)
        )
        google_event = event.to_google_event()

        assert google_event["summary"] == "Holiday"
        assert google_event["start"]["date"] == "2024-03-15"
        assert google_event["end"]["date"] == "2024-03-15"

    def test_to_google_event_timed(self):
        """Test Google Calendar format for timed event."""
        event = CalendarEvent(
            title="Meeting",
            event_date=date(2024, 3, 15),
            start_time=time(9, 30),
            end_time=time(10, 30)
        )
        google_event = event.to_google_event(timezone="America/New_York")

        assert google_event["summary"] == "Meeting"
        assert "dateTime" in google_event["start"]
        assert google_event["start"]["timeZone"] == "America/New_York"

    def test_to_dict(self):
        """Test dictionary serialization."""
        event = CalendarEvent(
            title="Test Event",
            event_date=date(2024, 3, 15),
            start_time=time(14, 0),
            confidence=0.85
        )
        d = event.to_dict()

        assert d["title"] == "Test Event"
        assert d["date"] == "2024-03-15"
        assert d["start_time"] == "14:00:00"
        assert d["confidence"] == 0.85


class TestAcademicCalendarParser:
    """Tests for AcademicCalendarParser service."""

    @pytest.fixture
    def parser(self):
        return AcademicCalendarParser(academic_year_start=2025)

    def test_get_year_for_month_fall(self, parser):
        """Test year calculation for fall semester months."""
        assert parser.get_year_for_month(8) == 2025  # August
        assert parser.get_year_for_month(9) == 2025  # September
        assert parser.get_year_for_month(12) == 2025  # December

    def test_get_year_for_month_spring(self, parser):
        """Test year calculation for spring semester months."""
        assert parser.get_year_for_month(1) == 2026  # January
        assert parser.get_year_for_month(5) == 2026  # May
        assert parser.get_year_for_month(6) == 2026  # June

    def test_parse_single_date(self, parser):
        """Test parsing single date event."""
        text = "August 20 Students Return"
        events = parser.parse_text(text)

        assert len(events) == 1
        assert events[0].title == "Students Return"
        assert events[0].event_date == date(2025, 8, 20)

    def test_parse_date_range_same_month(self, parser):
        """Test parsing date range within same month."""
        text = "August 11-12 Leadership Time"
        events = parser.parse_text(text)

        assert len(events) == 1
        assert events[0].title == "Leadership Time"
        assert events[0].event_date == date(2025, 8, 11)

    def test_parse_date_range_cross_month(self, parser):
        """Test parsing date range crossing months."""
        text = "December 22-January 2 Winter Break"
        events = parser.parse_text(text)

        assert len(events) == 1
        assert events[0].title == "Winter Break"
        assert events[0].event_date == date(2025, 12, 22)
        assert "January 02, 2026" in events[0].description

    def test_parse_multiple_events(self, parser):
        """Test parsing multiple events."""
        text = """
        August 11-12 Leadership Time
        August 13-19 Staff Development Time
        August 20 Students Return
        """
        events = parser.parse_text(text)

        assert len(events) == 3

    def test_parse_with_separator(self, parser):
        """Test parsing events with colon/pipe separators."""
        text = "September 1: Labor Day - No School"
        events = parser.parse_text(text)

        assert len(events) == 1
        assert "Labor Day" in events[0].title

    def test_parse_month_case_insensitive(self, parser):
        """Test that month names are case insensitive."""
        text = "AUGUST 20 Test Event"
        events = parser.parse_text(text)

        assert len(events) == 1
        assert events[0].event_date.month == 8

    def test_parse_empty_text(self, parser):
        """Test parsing empty text returns empty list."""
        events = parser.parse_text("")
        assert events == []

    def test_parse_no_events(self, parser):
        """Test parsing text with no recognizable events."""
        text = "This is just some random text without dates"
        events = parser.parse_text(text)
        assert events == []


class TestExtractEventsFromAcademicCalendar:
    """Tests for the main extraction function."""

    def test_extract_full_calendar(self):
        """Test extracting events from full calendar text."""
        ocr_text = """
        SEMESTER 1
        August 11-12 Leadership Time
        August 13-19 Staff Development Time
        August 20 Students Return
        September 1 Labor Day - No School
        November 24-28 Fall Break
        December 22-January 2 Winter Break

        SEMESTER 2
        January 6 Students Return
        March 20 Family Conferences
        April 6-10 Spring Break
        May 25 Memorial Day
        June 5 Graduation
        """

        events = extract_events_from_academic_calendar(ocr_text, 2025)

        # Should find multiple events
        assert len(events) >= 10

        # Check specific events
        titles = [e.title.lower() for e in events]
        assert any("leadership" in t for t in titles)
        assert any("students return" in t for t in titles)
        assert any("winter break" in t for t in titles)


class TestEventParser:
    """Tests for EventParser service (time-based parsing)."""

    @pytest.fixture
    def parser(self):
        return EventParser()

    def test_parse_time_with_am_pm(self, parser):
        """Test parsing time with AM/PM."""
        events = parser.parse_cell_text("Meeting 9:00 AM", date(2024, 3, 15))
        assert len(events) == 1
        assert events[0].start_time == time(9, 0)

    def test_parse_time_range(self, parser):
        """Test parsing time range."""
        events = parser.parse_cell_text("Meeting 9:00 AM - 10:30 AM", date(2024, 3, 15))
        assert len(events) == 1
        assert events[0].start_time == time(9, 0)
        assert events[0].end_time == time(10, 30)

    def test_parse_24_hour_format(self, parser):
        """Test parsing 24-hour time format."""
        events = parser.parse_cell_text("Meeting 14:30", date(2024, 3, 15))
        assert len(events) == 1
        assert events[0].start_time == time(14, 30)

    def test_parse_all_day_event(self, parser):
        """Test parsing all-day event (no time)."""
        events = parser.parse_cell_text("Holiday", date(2024, 3, 15))
        assert len(events) == 1
        assert events[0].is_all_day
        assert events[0].title == "Holiday"


class TestGridDetector:
    """Tests for GridDetector service."""

    @pytest.fixture
    def detector(self):
        return GridDetector(expected_cols=7, expected_rows=6)

    def test_cell_boundary_properties(self):
        """Test CellBoundary helper properties."""
        cell = CellBoundary(x=100, y=200, width=50, height=40, row=1, col=2)

        assert cell.center == (125, 220)
        assert cell.area == 2000

    def test_cell_extract_from_image(self):
        """Test extracting cell region from image."""
        # Create a test image
        image = np.zeros((500, 700, 3), dtype=np.uint8)
        image[200:240, 100:150] = 255  # White region in cell

        cell = CellBoundary(x=100, y=200, width=50, height=40, row=1, col=2)
        extracted = cell.extract_from_image(image, padding=5)

        assert extracted.shape[0] == 30  # height - 2*padding
        assert extracted.shape[1] == 40  # width - 2*padding

    def test_uniform_grid_creation(self, detector):
        """Test fallback uniform grid creation."""
        shape = (600, 700, 3)
        cells = detector._create_uniform_grid(shape)

        assert len(cells) == 42  # 7 cols * 6 rows


class TestImageProcessor:
    """Tests for ImageProcessor service."""

    def test_is_supported_format(self):
        """Test format support checking."""
        from app.services.image_processor import ImageProcessor

        assert ImageProcessor.is_supported_format("calendar.png")
        assert ImageProcessor.is_supported_format("calendar.PNG")
        assert ImageProcessor.is_supported_format("calendar.jpg")
        assert ImageProcessor.is_supported_format("calendar.jpeg")
        assert ImageProcessor.is_supported_format("calendar.pdf")
        assert not ImageProcessor.is_supported_format("calendar.txt")
        assert not ImageProcessor.is_supported_format("calendar.doc")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
