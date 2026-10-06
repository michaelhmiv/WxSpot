FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/ .
RUN pip install --no-cache-dir . && useradd --create-home wxspot && mkdir /app/media && chown wxspot:wxspot /app/media
USER wxspot
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn wxspot.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
