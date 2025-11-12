FROM python:3-alpine

RUN apk update && apk add git

WORKDIR /app

# Copy requirements.txt for dependency caching
COPY requirements.txt ./

# Install dependencies using uv (mounted temporarily for optimal caching)
RUN --mount=from=ghcr.io/astral-sh/uv:latest,source=/uv,target=/bin/uv \
    uv pip install --no-cache-dir --system -r requirements.txt

# Copy project files
COPY clients.yaml .
COPY google-service-account.json .
COPY .env .
COPY run.sh sender.logrotate .
COPY src ./src

# Set PYTHONPATH to include src directory
ENV PYTHONPATH=/app/src

CMD ["python", "-m", "src.cli"]
