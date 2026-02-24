"""API routes for calendar sync application."""
import os
import io
import uuid
import json
from datetime import date
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.services.google_calendar import GoogleCalendarService
from app.services.academic_calendar_parser import extract_events_from_academic_calendar
from app.models.event import CalendarEvent

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

# Initialize services
google_calendar = GoogleCalendarService()

# Simple in-memory session storage (use Redis in production)
sessions = {}

SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg', '.pdf', '.bmp', '.webp'}


def get_session(request: Request) -> dict:
    """Get or create session for request."""
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        return sessions[session_id]
    return {}


def set_session(response, session_data: dict) -> str:
    """Set session data and return session ID."""
    session_id = str(uuid.uuid4())
    sessions[session_id] = session_data
    response.set_cookie("session_id", session_id, httponly=True, max_age=3600)
    return session_id


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main upload page."""
    session = get_session(request)
    is_authenticated = "google_credentials" in session

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "is_authenticated": is_authenticated,
            "current_year": date.today().year,
        }
    )


@router.post("/upload")
async def upload_calendar(
    request: Request,
    file: UploadFile = File(...),
    academic_year_start: int = Form(...),
    timezone: str = Form("America/Los_Angeles")
):
    """
    Upload and process an academic calendar image.
    Uses Claude Vision if ANTHROPIC_API_KEY is set, otherwise falls back to EasyOCR.
    """
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload PNG, JPEG, or PDF."
        )

    if not (2000 <= academic_year_start <= 2100):
        raise HTTPException(status_code=400, detail="Invalid academic year")

    content = await file.read()

    if len(content) > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {settings.MAX_UPLOAD_SIZE // (1024*1024)}MB"
        )

    try:
        all_events = []
        raw_text = ""

        # Try Claude Vision first if API key is set
        if settings.ANTHROPIC_API_KEY:
            try:
                from app.services.claude_vision_ocr import ClaudeVisionOCR
                vision_ocr = ClaudeVisionOCR()

                MIME_TYPES = {
                    '.png': 'image/png', '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg', '.webp': 'image/webp',
                    '.bmp': 'image/bmp', '.gif': 'image/gif',
                }

                if ext == '.pdf':
                    from app.services.image_processor import ImageProcessor
                    import cv2
                    from PIL import Image
                    import numpy as np

                    processor = ImageProcessor()
                    images = processor.load_pdf_from_bytes(content)

                    page_images = []
                    for img in images:
                        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                        pil_img = Image.fromarray(img_rgb)
                        buf = io.BytesIO()
                        pil_img.save(buf, format='PNG')
                        page_images.append(buf.getvalue())

                    all_events = vision_ocr.extract_events_from_pdf_pages(
                        page_images, 'image/png', academic_year_start
                    )
                else:
                    media_type = MIME_TYPES.get(ext, 'image/png')
                    all_events = vision_ocr.extract_events(
                        content, media_type, academic_year_start
                    )

                raw_text = "Processed with Claude Vision"
            except Exception as e:
                # Fall back to EasyOCR if Claude Vision fails
                all_events = []
                raw_text = f"Claude Vision failed ({str(e)}), falling back to EasyOCR..."

        # Fall back to EasyOCR
        if not all_events:
            from app.services.easyocr_service import EasyOCRService
            ocr = EasyOCRService()

            text = ocr.extract_text_from_bytes(content, file.filename)
            raw_text = text

            if text:
                all_events = extract_events_from_academic_calendar(
                    text, academic_year_start
                )

        # Sort by date
        all_events.sort(key=lambda e: (e.event_date, e.title.lower()))

        # Store events in session for syncing
        session = get_session(request)
        session["pending_events"] = [e.to_dict() for e in all_events]
        session["timezone"] = timezone

        response = JSONResponse({
            "success": True,
            "events": [e.to_dict() for e in all_events],
            "count": len(all_events),
            "raw_text": raw_text
        })

        session_id = request.cookies.get("session_id")
        if session_id:
            sessions[session_id] = session
        else:
            set_session(response, session)

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")


@router.get("/auth/google")
async def google_auth(request: Request):
    """Initiate Google OAuth flow."""
    state = str(uuid.uuid4())

    session = get_session(request)
    session["oauth_state"] = state

    session_id = request.cookies.get("session_id")
    if session_id:
        sessions[session_id] = session

    auth_url, _ = google_calendar.get_authorization_url(state=state)
    response = RedirectResponse(url=auth_url)

    if not session_id:
        set_session(response, session)

    return response


@router.get("/auth/callback")
async def google_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...)
):
    """Handle Google OAuth callback."""
    session = get_session(request)

    stored_state = session.get("oauth_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    try:
        credentials = google_calendar.exchange_code_for_credentials(code)
        session["google_credentials"] = credentials
        del session["oauth_state"]

        session_id = request.cookies.get("session_id")
        if session_id:
            sessions[session_id] = session

        return RedirectResponse(url="/?authenticated=true")

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")


@router.post("/sync-selected")
async def sync_selected_to_google(request: Request):
    """Sync user-selected events to Google Calendar."""
    session = get_session(request)

    credentials = session.get("google_credentials")
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated with Google")

    body = await request.json()
    selected_events = body.get("events", [])

    if not selected_events:
        raise HTTPException(status_code=400, detail="No events selected")

    timezone = session.get("timezone", "America/Los_Angeles")

    events = []
    for event_dict in selected_events:
        from datetime import time as dt_time
        event = CalendarEvent(
            title=event_dict["title"],
            event_date=date.fromisoformat(event_dict["date"]),
            start_time=dt_time.fromisoformat(event_dict["start_time"]) if event_dict.get("start_time") else None,
            end_time=dt_time.fromisoformat(event_dict["end_time"]) if event_dict.get("end_time") else None,
            description=event_dict.get("description", ""),
            confidence=event_dict.get("confidence", 1.0)
        )
        events.append(event)

    try:
        results = google_calendar.create_events_batch(
            credentials, events, timezone=timezone
        )

        successes = [r for r in results if r.get("success")]
        failures = [r for r in results if not r.get("success")]

        return JSONResponse({
            "success": True,
            "synced": len(successes),
            "failed": len(failures),
            "results": results
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/sync")
async def sync_to_google(request: Request):
    """Sync extracted events to Google Calendar."""
    session = get_session(request)

    credentials = session.get("google_credentials")
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated with Google")

    pending_events = session.get("pending_events", [])
    if not pending_events:
        raise HTTPException(status_code=400, detail="No events to sync")

    timezone = session.get("timezone", "America/Los_Angeles")

    events = []
    for event_dict in pending_events:
        from datetime import time as dt_time
        event = CalendarEvent(
            title=event_dict["title"],
            event_date=date.fromisoformat(event_dict["date"]),
            start_time=dt_time.fromisoformat(event_dict["start_time"]) if event_dict.get("start_time") else None,
            end_time=dt_time.fromisoformat(event_dict["end_time"]) if event_dict.get("end_time") else None,
            description=event_dict.get("description", ""),
            confidence=event_dict.get("confidence", 1.0)
        )
        events.append(event)

    try:
        results = google_calendar.create_events_batch(
            credentials, events, timezone=timezone
        )

        session["pending_events"] = []
        session_id = request.cookies.get("session_id")
        if session_id:
            sessions[session_id] = session

        successes = [r for r in results if r.get("success")]
        failures = [r for r in results if not r.get("success")]

        return JSONResponse({
            "success": True,
            "synced": len(successes),
            "failed": len(failures),
            "results": results
        })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/success", response_class=HTMLResponse)
async def success_page(request: Request, synced: int = 0):
    """Render success page after sync."""
    return templates.TemplateResponse(
        "success.html",
        {"request": request, "synced_count": synced}
    )


@router.get("/calendars")
async def list_calendars(request: Request):
    """List user's Google Calendars."""
    session = get_session(request)
    credentials = session.get("google_credentials")
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated with Google")

    try:
        calendars = google_calendar.list_calendars(credentials)
        return JSONResponse({"calendars": calendars})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list calendars: {str(e)}")


@router.post("/logout")
async def logout(request: Request):
    """Clear session and logout."""
    session_id = request.cookies.get("session_id")
    if session_id and session_id in sessions:
        del sessions[session_id]

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("session_id")
    return response
