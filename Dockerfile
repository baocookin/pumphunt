# One image: FastAPI recorder/API + the Next.js dashboard as a static export.
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json ./
RUN npm install
COPY web/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot/app ./app
COPY --from=web /web/out ./static
ENV PH_STATIC_DIR=/app/static PH_DATA_DIR=/data
EXPOSE 8080
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8080"]
