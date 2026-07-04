FROM python:3.12-slim
WORKDIR /app
# Build context is ./backend — copy shared layer first for cache efficiency
COPY shared/              /app/shared/
COPY auth_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY auth_service/        /app/
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
