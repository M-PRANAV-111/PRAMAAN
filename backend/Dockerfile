# PRAMAAN API image. OCR (Tesseract) and PDF tooling are system dependencies.
FROM python:3.13-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng libgl1 libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 pramaan
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=pramaan:pramaan . .
ENV DATA_DIR=/data APP_ENV=production PYTHONUNBUFFERED=1
RUN mkdir -p /data && chown pramaan:pramaan /data
USER pramaan
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
