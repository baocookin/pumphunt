FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV PH_RUN_WORKER=1
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8080"]
