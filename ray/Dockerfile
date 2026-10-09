# Rây: the real-time scorer. Build from the repository root:
#   docker build -f ray/Dockerfile -t ray .
# The frozen sieve filters are copied from research/sieve/filters.py unchanged (hash-checked at start).
# AWS's public mirror of Docker Hub's official image: GitHub runners hit Docker Hub's pull limit (429)
FROM public.ecr.aws/docker/library/python:3.13-slim
WORKDIR /app
COPY ray/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY ray/app ./app
COPY research/sieve/filters.py ./sieve/filters.py
ARG BUILD_SHA=dev
# /data is the app's persistent volume on Bunny (the research recorder's files stay there);
# an env var set in the Bunny app (PH_DATA_DIR or RAY_DATA_DIR) still wins.
ENV RAY_BUILD_SHA=$BUILD_SHA RAY_SIEVE_DIR=/app/sieve PH_DATA_DIR=/data
EXPOSE 8080
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8080"]
