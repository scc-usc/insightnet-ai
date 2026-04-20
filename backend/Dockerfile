# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Keeps Python from generating .pyc files and enables log flushing
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer-cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Cloud Run injects PORT; default to 8080
ENV PORT=8080

# Use gunicorn + uvicorn workers for production concurrency
# Adjust --workers based on Cloud Run CPU allocation (1 CPU → 1-2 workers)
CMD ["sh", "-c", "uvicorn infra.server:app --host 0.0.0.0 --port $PORT --workers 2"]
