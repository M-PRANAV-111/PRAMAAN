FROM node:22-bookworm-slim AS front
WORKDIR /build/front
COPY front/package*.json ./
RUN npm ci --no-audit --no-fund
COPY contracts /build/contracts
COPY front/ ./
RUN npm run typecheck && npm run build

FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 pramaan
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=pramaan:pramaan backend/ ./
COPY --from=front --chown=pramaan:pramaan /build/front/dist /app/front/dist
ENV APP_ENV=production DATA_DIR=/data FRONT_DIST=/app/front/dist PYTHONUNBUFFERED=1 SHOW_DEMO_ACCOUNTS=false
RUN mkdir -p /data && chown pramaan:pramaan /data
USER pramaan
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]
