FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Cloud Run injects $PORT at runtime
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn infra.server:app --host 0.0.0.0 --port $PORT"]
