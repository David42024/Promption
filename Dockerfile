# Prompt Injection Filter — FastAPI + Streamlit
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app

WORKDIR /app

# system deps for ML/native wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dashboard.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt && \
    pip install -r requirements-dashboard.txt

COPY . .

EXPOSE 8000 8501

# default: FastAPI (docker-compose overrides for the dashboard service)
# $PORT permite que Render/Heroku inyecten el puerto de escucha (usa 8000 localmente)
CMD uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}