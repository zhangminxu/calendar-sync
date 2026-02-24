"""Google Calendar integration service."""
import json
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import settings
from app.models.event import CalendarEvent


class GoogleCalendarService:
    """Handles Google Calendar OAuth and event operations."""

    SCOPES = settings.GOOGLE_SCOPES

    def __init__(self):
        """Initialize Google Calendar service."""
        self.client_config = {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        }

    def get_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Generate Google OAuth2 authorization URL.

        Args:
            state: Optional state parameter for CSRF protection

        Returns:
            Tuple of (authorization_url, state)
        """
        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )

        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent',
            state=state
        )

        return authorization_url, state

    def exchange_code_for_credentials(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for credentials.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Credentials as dictionary (for session storage)
        """
        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.SCOPES,
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )

        flow.fetch_token(code=code)
        credentials = flow.credentials

        return self._credentials_to_dict(credentials)

    def _credentials_to_dict(self, credentials: Credentials) -> Dict[str, Any]:
        """Convert credentials to dictionary for storage."""
        return {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': list(credentials.scopes) if credentials.scopes else [],
            'expiry': credentials.expiry.isoformat() if credentials.expiry else None,
        }

    def _dict_to_credentials(self, creds_dict: Dict[str, Any]) -> Credentials:
        """Restore credentials from dictionary."""
        expiry = None
        if creds_dict.get('expiry'):
            expiry = datetime.fromisoformat(creds_dict['expiry'])

        return Credentials(
            token=creds_dict['token'],
            refresh_token=creds_dict.get('refresh_token'),
            token_uri=creds_dict.get('token_uri', 'https://oauth2.googleapis.com/token'),
            client_id=creds_dict.get('client_id', settings.GOOGLE_CLIENT_ID),
            client_secret=creds_dict.get('client_secret', settings.GOOGLE_CLIENT_SECRET),
            scopes=creds_dict.get('scopes', self.SCOPES),
            expiry=expiry
        )

    def get_calendar_service(self, credentials_dict: Dict[str, Any]):
        """
        Get Google Calendar API service.

        Args:
            credentials_dict: Stored credentials dictionary

        Returns:
            Google Calendar API service
        """
        credentials = self._dict_to_credentials(credentials_dict)
        return build('calendar', 'v3', credentials=credentials)

    def create_event(
        self,
        credentials_dict: Dict[str, Any],
        event: CalendarEvent,
        calendar_id: str = 'primary',
        timezone: str = 'America/Los_Angeles'
    ) -> Dict[str, Any]:
        """
        Create a single event in Google Calendar.

        Args:
            credentials_dict: Stored credentials
            event: CalendarEvent to create
            calendar_id: Target calendar ID
            timezone: Timezone for the event

        Returns:
            Created event data from Google Calendar API
        """
        service = self.get_calendar_service(credentials_dict)
        event_body = event.to_google_event(timezone=timezone)

        created_event = service.events().insert(
            calendarId=calendar_id,
            body=event_body
        ).execute()

        return created_event

    def create_events_batch(
        self,
        credentials_dict: Dict[str, Any],
        events: List[CalendarEvent],
        calendar_id: str = 'primary',
        timezone: str = 'America/Los_Angeles'
    ) -> List[Dict[str, Any]]:
        """
        Create multiple events using batch requests.

        Args:
            credentials_dict: Stored credentials
            events: List of CalendarEvent objects to create
            calendar_id: Target calendar ID
            timezone: Timezone for events

        Returns:
            List of created event data
        """
        if not events:
            return []

        service = self.get_calendar_service(credentials_dict)
        created_events = []
        errors = []

        # Google Calendar batch API is complex, use simple iteration for reliability
        for event in events:
            try:
                event_body = event.to_google_event(timezone=timezone)
                created = service.events().insert(
                    calendarId=calendar_id,
                    body=event_body
                ).execute()
                created_events.append({
                    'success': True,
                    'event': created,
                    'original': event.to_dict()
                })
            except HttpError as e:
                errors.append({
                    'success': False,
                    'error': str(e),
                    'original': event.to_dict()
                })

        return created_events + errors

    def list_calendars(self, credentials_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        List user's calendars.

        Args:
            credentials_dict: Stored credentials

        Returns:
            List of calendar metadata
        """
        service = self.get_calendar_service(credentials_dict)
        calendars = []

        page_token = None
        while True:
            calendar_list = service.calendarList().list(
                pageToken=page_token
            ).execute()

            for calendar in calendar_list.get('items', []):
                calendars.append({
                    'id': calendar['id'],
                    'summary': calendar.get('summary', 'Unnamed'),
                    'primary': calendar.get('primary', False),
                    'accessRole': calendar.get('accessRole', 'reader')
                })

            page_token = calendar_list.get('nextPageToken')
            if not page_token:
                break

        return calendars

    def verify_credentials(self, credentials_dict: Dict[str, Any]) -> bool:
        """
        Verify that credentials are still valid.

        Args:
            credentials_dict: Stored credentials

        Returns:
            True if credentials are valid
        """
        try:
            credentials = self._dict_to_credentials(credentials_dict)

            # Check if token is expired
            if credentials.expired and credentials.refresh_token:
                # Credentials will auto-refresh when used
                pass

            # Try to list calendars as a test
            service = self.get_calendar_service(credentials_dict)
            service.calendarList().list(maxResults=1).execute()

            return True
        except Exception:
            return False
