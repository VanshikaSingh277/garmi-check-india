# Thandak site: one container (FastAPI API + the built static frontend)
# stage 1: build the frontend (Vite) - only dist/ is carried over, so the image has no Node or node_modules
FROM node:22-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

# stage 2: the API
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY apps/api/requirements.txt /app/api/requirements.txt
RUN pip install --no-cache-dir -r /app/api/requirements.txt
COPY apps/api /app/api
COPY --from=web /web/dist /app/web
WORKDIR /app/api
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
