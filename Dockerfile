# Single image: builds the React UI, then serves UI + API from one FastAPI process.
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim AS app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/app backend/app
COPY data data
COPY evals evals
COPY --from=ui /ui/dist frontend/dist
RUN useradd -m appuser && mkdir -p /app/storage && chown -R appuser /app/storage
USER appuser
ENV ENV=prod STATIC_DIR=/app/frontend/dist STORAGE_DIR=/app/storage DATA_DIR=/app/data PORT=8000
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://localhost:'+os.environ.get('PORT','8000')+'/api/health')"
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
