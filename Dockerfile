FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps: espeak-ng for fallback phonemes
RUN apt-get update && \
    apt-get install -y --no-install-recommends espeak-ng && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (build cache friendly)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy server code
COPY server.py .

EXPOSE 8080

# Configurable defaults
ENV LANG_CODE=a \
    DEFAULT_VOICE=af_heart \
    DEFAULT_SPEED=1.0 \
    SAMPLE_RATE=24000

# Start the API
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
