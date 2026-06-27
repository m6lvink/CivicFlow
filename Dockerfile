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
COPY models/stage_a_classifier.joblib models/stage_a_classifier.joblib
COPY models/stage_b_regressor.joblib models/stage_b_regressor.joblib
COPY models/encoders.joblib models/encoders.joblib
COPY models/metrics.json models/metrics.json
COPY models/model_card.json models/model_card.json
RUN pip install --no-cache-dir --no-deps .

EXPOSE 8000

CMD ["sh", "-c", "uvicorn civicflow.api:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
