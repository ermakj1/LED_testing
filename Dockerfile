FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir flask Pillow

COPY manage.py .
COPY ui_manage.html .
COPY feeds/ feeds/

CMD ["python", "-u", "manage.py"]
