FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmupdf-dev mupdf-tools \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY shared/              /app/shared/
COPY pdf_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY pdf_service/         /app/
EXPOSE 8002
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8002"]
