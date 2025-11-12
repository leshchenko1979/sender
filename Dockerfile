FROM python:3-alpine

RUN apk update && apk add git

WORKDIR /app

# Copy requirements.txt for dependency caching
COPY requirements.txt ./

# Install dependencies (this layer will be cached when requirements don't change)
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY pyproject.toml ./
COPY src ./src
COPY clients.yaml .
COPY google-service-account.json .
COPY .env .
COPY run.sh sender.logrotate .

# Set PYTHONPATH to include src directory
ENV PYTHONPATH=/app/src

CMD ["python", "-m", "src.cli"]
