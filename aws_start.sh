#!/bin/bash
# AWS Compute Node Startup for petdura
export APP_HOST=0.0.0.0
export APP_PORT=5050
export PET_SERVICE_PARQUET="$PWD/data/pet_services.parquet"

.venv/bin/gunicorn \
  --workers 2 \
  --threads 4 \
  --bind 0.0.0.0:5050 \
  --timeout 60 \
  app:app
