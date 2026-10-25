# Thandak site: one image (FastAPI API + the built static frontend), run as two containers: the API and the jobs process.
# Hardening (spec §8.10, docs/DEPLOY.md): base images pinned by digest, packages installed with --require-hashes,
# a non-root user, code and data owned by root and read-only; the only writable place is /state (a volume) plus /tmp.
# Digests looked up 2026-10-25 for python:3.11-slim and node:22-slim; refresh them with the steps in docs/DEPLOY.md.

# stage 1: build the frontend (Vite) - only dist/ is carried over, so the image has no Node or node_modules
FROM node:22-slim@sha256:de170b39439eb0e5a3444ad7d60b015614a381e10fecae2e30ec9e735122f38d AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
RUN npm run build

# stage 2: the API
FROM python:3.11-slim@sha256:b7a9e5f6a93d6d4a31f129bbd4bdee69efccb6ded0fb230d78aafaf37af98377
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin thandak \
 && mkdir -p /state && chown thandak /state
WORKDIR /app
COPY apps/api/requirements.lock /app/api/requirements.lock
RUN pip install --no-cache-dir --require-hashes --no-deps --default-timeout=120 --retries 10 -r /app/api/requirements.lock
COPY apps/api /app/api
COPY --from=web /web/dist /app/web
RUN chmod -R a-w /app
WORKDIR /app/api
ENV PORT=8000 THANDAK_STATE_DIR=/state PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001
VOLUME ["/state"]
EXPOSE 8000
# no access log (query strings hold coordinates), no Server header (spec §8.5-8.6); requests are logged by app/http.py.
# --no-proxy-headers: the client IP comes from app/http.py, which trusts X-Forwarded-For only from TRUSTED_PROXY_CIDRS.
# The jobs container runs the same image with: python -m app.jobs
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT} --no-access-log --no-server-header --no-proxy-headers"]
