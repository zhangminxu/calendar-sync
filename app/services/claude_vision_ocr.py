"""Claude Vision API service for extracting events from calendar images."""
import base64
import json
import re
from datetime import date, timedelta
from typing import List, Optional

import anthropic

from app.config import settings
from app.models.event import CalendarEvent


class ClaudeVisionOCR:
    """Uses Claude Vision API to extract calendar events from images."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def extract_events(
        self,
        image_bytes: bytes,
        media_type: str,
        academic_year_start: int
    ) -> List[CalendarEvent]:
        """
        Extract events from a calendar image using Claude Vision.

        Args:
            image_bytes: Raw image bytes
            media_type: MIME type (image/png, image/jpeg, etc.)
            academic_year_start: Starting year of academic year

        Returns:
            List of CalendarEvent objects
        """
        # Encode image to base64
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        academic_year_end = academic_year_start + 1

        prompt = f"""Look at this academic calendar image. Extract ALL events listed on the right side of the calendar (the event listing section, not the grid).

For each event, output one line in this exact format:
DATE|EVENT_NAME

Rules:
- The academic year is {academic_year_start}-{academic_year_end} (August {academic_year_start} through July {academic_year_end})
- For date ranges like "August 17-18", output EACH date separately:
  {academic_year_start}-08-17|Student Orientation
  {academic_year_start}-08-18|Student Orientation
- For cross-month ranges like "December 21-January 1", output EACH date:
  {academic_year_start}-12-21|Winter Break
  {academic_year_start}-12-22|Winter Break
  ... (every date in range)
  {academic_year_end}-01-01|Winter Break
- Use ISO format for dates: YYYY-MM-DD
- August through December use year {academic_year_start}
- January through July use year {academic_year_end}
- Include ALL events from ALL sections (Semester 1, Semester 2, Summer, etc.)
- Include the color code legend events too if they appear as actual dated events
- Do NOT skip any events

Output ONLY the DATE|EVENT_NAME lines, nothing else."""

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        },
                    ],
                }
            ],
        )

        # Parse response
        response_text = response.content[0].text
        return self._parse_response(response_text)

    def extract_events_from_pdf_pages(
        self,
        page_images: List[bytes],
        media_type: str,
        academic_year_start: int
    ) -> List[CalendarEvent]:
        """
        Extract events from multiple PDF page images.

        Args:
            page_images: List of page image bytes
            media_type: MIME type for the images
            academic_year_start: Starting year

        Returns:
            List of CalendarEvent objects
        """
        all_events = []

        for page_bytes in page_images:
            events = self.extract_events(page_bytes, media_type, academic_year_start)
            all_events.extend(events)

        # Deduplicate
        seen = set()
        unique = []
        for event in all_events:
            key = (event.event_date, event.title.lower())
            if key not in seen:
                seen.add(key)
                unique.append(event)

        unique.sort(key=lambda e: (e.event_date, e.title.lower()))
        return unique

    def _parse_response(self, response_text: str) -> List[CalendarEvent]:
        """Parse Claude's response into CalendarEvent objects."""
        events = []

        for line in response_text.strip().split('\n'):
            line = line.strip()
            if not line or '|' not in line:
                continue

            parts = line.split('|', 1)
            if len(parts) != 2:
                continue

            date_str = parts[0].strip()
            title = parts[1].strip()

            if not title:
                continue

            try:
                event_date = date.fromisoformat(date_str)
                events.append(CalendarEvent(
                    title=title,
                    event_date=event_date,
                    description="From academic calendar"
                ))
            except ValueError:
                continue

        return events

    def get_raw_text(
        self,
        image_bytes: bytes,
        media_type: str
    ) -> str:
        """
        Get raw text extraction from image (for debugging).

        Args:
            image_bytes: Raw image bytes
            media_type: MIME type

        Returns:
            Extracted text
        """
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

        response = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract ALL text from this image exactly as it appears. Include everything - headers, event listings, color codes, dates, etc.",
                        },
                    ],
                }
            ],
        )

        return response.content[0].text
