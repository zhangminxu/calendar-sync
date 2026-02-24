FROM python:3.11-slim

# Install system dependencies for OpenCV, Tesseract, Poppler
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir easyocr

# Pre-download EasyOCR model so it doesn't download at runtime
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"

# Copy app code
COPY . .

# Cloud Run sets PORT env var
ENV PORT=8080
EXPOSE 8080

CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
