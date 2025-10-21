FROM python:3.14-alpine

RUN apk update && apk add git

ADD /requirements.txt /

RUN pip install -r requirements.txt --no-cache

ADD /.env /

ADD /clients.py /settings.py /sender.py /supabase_logs.py /cron_utils.py /
ADD /google-service-account.json /

ADD clients.yaml /

CMD ["python", "/sender.py"]
