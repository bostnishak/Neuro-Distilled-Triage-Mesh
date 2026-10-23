FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.8.2

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libgeos-dev \
    libgomp1 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt pyproject.toml ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

COPY . /app

EXPOSE 8000 50051

CMD ["uvicorn", "presentation.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--log-config", "core/log_config.json"]
