FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-eng libmupdf-dev mupdf-tools \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY shared/              /app/shared/
COPY ocr_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ocr_service/         /app/
EXPOSE 8004
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8004"]
