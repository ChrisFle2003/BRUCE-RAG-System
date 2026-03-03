FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY src/python/requirements.runtime.txt /tmp/requirements.runtime.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.runtime.txt

COPY src/python /app/src/python

ENV PYTHONPATH=/app/src/python

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "9998"]
