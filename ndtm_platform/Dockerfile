# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HOME=/opt/hf-cache \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

# Install OS libraries for ONNX Runtime / PyTorch CPU kernels
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl gcc python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Install CPU torch wheel first to save space, then install requirements
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 \
    && pip install -r requirements.txt

# Run as non-privileged app user
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /data/uploads /opt/hf-cache /app/models/student \
    && chown -R app:app /data /opt/hf-cache /app

COPY --chown=app:app . .

USER app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
