FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

# Python deps
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (mql5/signals is created below and mounted as a volume)
COPY backend/ ./backend/

# Create log, signal and data directories
RUN mkdir -p /app/logs /app/mql5/signals /app/data

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "backend.api.api_server:app", "--host", "0.0.0.0", "--port", "8000"]
