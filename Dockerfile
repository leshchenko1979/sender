FROM python:3-alpine

RUN apk update && apk add git

WORKDIR /app

COPY pyproject.toml ./

RUN pip install --no-cache-dir .

COPY src ./src
COPY clients.yaml .
COPY google-service-account.json .
COPY .env .
COPY run.sh sender.logrotate .

CMD ["python", "-m", "src.cli"]
