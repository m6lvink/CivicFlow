FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.lock pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.lock

COPY civicflow ./civicflow
COPY artifacts/stage_a_classifier.joblib artifacts/stage_a_classifier.joblib
COPY artifacts/stage_b_regressor.joblib artifacts/stage_b_regressor.joblib
COPY artifacts/encoders.joblib artifacts/encoders.joblib
COPY artifacts/metrics.json artifacts/metrics.json
COPY artifacts/model_card.json artifacts/model_card.json
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn civicflow.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
