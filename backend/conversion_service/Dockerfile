FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice libreoffice-writer libreoffice-calc libreoffice-impress \
    libmupdf-dev mupdf-tools fonts-liberation \
    fonts-noto-core \
    fonts-noto-unhinted \
    fonts-indic \
    fonts-freefont-ttf \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY shared/                  /app/shared/
COPY conversion_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY conversion_service/      /app/
EXPOSE 8005
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8005"]
