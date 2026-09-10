FROM python:3.12-slim

WORKDIR /app

# Install dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/

# Create data directory for SQLite (will be overwritten by a volume in prod)
RUN mkdir -p /app/data

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD uvicorn src.web.app_slim:app --host 0.0.0.0 --port ${PORT:-8000}
