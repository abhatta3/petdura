FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

ENV APP_HOST=0.0.0.0
ENV APP_PORT=5000
ENV PET_SERVICE_PARQUET=/app/data/pet_services.parquet

CMD ["gunicorn", "--workers", "2", "--threads", "4", "--bind", "0.0.0.0:5000", "--timeout", "60", "app:app"]
