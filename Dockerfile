FROM python:3.12-slim

WORKDIR /app

COPY manage.py .
COPY feeds/ feeds/

CMD ["python", "-u", "manage.py"]
