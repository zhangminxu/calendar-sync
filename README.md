# Academic Calendar to Google Calendar Sync

A web application that extracts events from academic calendar images (PDF/PNG/JPEG) and syncs them directly to Google Calendar.

## Features

- Upload academic calendar images (PNG, JPEG) or PDF files
- OCR-based text extraction using Tesseract
- Smart parsing of academic calendar event formats:
  - Single dates: "August 20 Students Return"
  - Date ranges: "August 11-12 Leadership Time"
  - Cross-month ranges: "December 22-January 2 Winter Break"
- Automatic year assignment for academic year (e.g., 2025-2026)
- Google Calendar OAuth2 authentication
- Batch event creation in Google Calendar
- Modern, responsive web interface with drag-and-drop upload

## User Flow

```
Upload Calendar Image → Select Academic Year → Extract Events → Authenticate Google → Sync → Done
```

## Prerequisites

### System Dependencies

**macOS:**
```bash
# Install Tesseract OCR
brew install tesseract

# Install Poppler (for PDF support)
brew install poppler
```

**Ubuntu/Debian:**
```bash
sudo apt-get install tesseract-ocr poppler-utils
```

### Python Requirements

- Python 3.10 or higher

## Installation

1. **Clone or navigate to the project:**
   ```bash
   cd calendar-sync
   ```

2. **Create a virtual environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up Google Cloud credentials:**

   a. Go to [Google Cloud Console](https://console.cloud.google.com/)

   b. Create a new project or select an existing one

   c. Enable the Google Calendar API:
      - Navigate to "APIs & Services" > "Enable APIs and Services"
      - Search for "Google Calendar API" and enable it

   d. Create OAuth 2.0 credentials:
      - Go to "APIs & Services" > "Credentials"
      - Click "Create Credentials" > "OAuth client ID"
      - Select "Web application"
      - Add `http://localhost:8000/auth/callback` to "Authorized redirect URIs"
      - Download or copy the client ID and secret

5. **Configure environment variables:**
   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your Google credentials:
   ```
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   GOOGLE_REDIRECT_URI=http://localhost:8000/auth/callback
   SECRET_KEY=your-random-secret-key
   ```

## Usage

1. **Start the server:**
   ```bash
   uvicorn app.main:app --reload
   ```

2. **Open your browser:**
   Navigate to `http://localhost:8000`

3. **Upload a calendar image:**
   - Drag and drop or click to select an academic calendar image
   - Select the academic year (e.g., 2025-2026 for calendars running Aug 2025 - Jul 2026)
   - Click "Extract Events"

4. **Review extracted events:**
   - Events are grouped by month
   - Verify the extracted events look correct

5. **Authenticate with Google:**
   - Click "Sign in with Google"
   - Grant calendar access permissions

6. **Sync events:**
   - Click "Sync to Google Calendar"
   - Events will be added to your primary Google Calendar

## Project Structure

```
calendar-sync/
├── app/
│   ├── __init__.py
│   ├── main.py                      # FastAPI app entry point
│   ├── config.py                    # Environment configuration
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py                # API endpoints
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── image_processor.py       # PDF/image loading
│   │   ├── ocr_service.py           # Tesseract OCR wrapper
│   │   ├── academic_calendar_parser.py  # Academic calendar event parsing
│   │   ├── event_parser.py          # Time-based event parsing
│   │   ├── grid_detector.py         # Calendar grid detection
│   │   └── google_calendar.py       # Google Calendar API
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── event.py                 # Event data models
│   │
│   ├── templates/
│   │   ├── index.html               # Main upload page
│   │   └── success.html             # Success confirmation
│   │
│   └── static/
│       └── styles.css               # Application styles
│
├── tests/
│   └── test_services.py             # Unit tests
│
├── requirements.txt
├── .env.example
└── README.md
```

## Supported Date Formats

The academic calendar parser recognizes these date formats:

| Format | Example | Result |
|--------|---------|--------|
| Single date | `August 20 Students Return` | Aug 20 event |
| Same-month range | `August 11-12 Leadership Time` | Aug 11 event (notes end date) |
| Cross-month range | `December 22-January 2 Winter Break` | Dec 22 event (notes end date) |

Events without specific times are created as all-day events.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main upload page |
| `/upload` | POST | Upload and process calendar image |
| `/auth/google` | GET | Initiate Google OAuth flow |
| `/auth/callback` | GET | OAuth callback handler |
| `/sync` | POST | Sync extracted events to Google Calendar |
| `/calendars` | GET | List user's Google Calendars |
| `/success` | GET | Success confirmation page |
| `/health` | GET | Health check endpoint |

## Running Tests

```bash
# Install pytest if not already installed
pip install pytest

# Run tests
pytest tests/ -v
```

## Troubleshooting

### OCR not detecting text
- Ensure the image is clear and high resolution (at least 150 DPI)
- Try uploading a PNG instead of JPEG for better quality
- The calendar text should be clearly readable
- Darker text on lighter backgrounds works best

### Google authentication fails
- Verify your OAuth credentials in `.env`
- Ensure the redirect URI matches exactly: `http://localhost:8000/auth/callback`
- Check that the Calendar API is enabled in Google Cloud Console
- Make sure you're using the correct Google account

### PDF processing fails
- Install Poppler: `brew install poppler` (macOS) or `apt-get install poppler-utils` (Linux)

### Events not parsed correctly
- Check that dates follow the expected format (e.g., "August 20" not "Aug 20" or "8/20")
- Verify the academic year is set correctly
- Review the OCR output for accuracy issues

## License

MIT
