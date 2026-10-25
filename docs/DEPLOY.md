# Deploying Thandak

How to run the backend in production (spec §8.10, §8.11, §9). Nothing here has been deployed yet. Picking a host and creating accounts is the team's decision (TEAM_TODO).

## 1. What runs

One image (`Dockerfile`) runs as two containers:

| Container | Command | Count |
|---|---|---|
| `api` | the image's default (`uvicorn main:app … --no-access-log --no-server-header --no-proxy-headers`) | **1** |
| `jobs` | `python -m app.jobs` (APScheduler; every job holds a `job_lock`) | **1** |

Both containers mount the same `/state` volume. It holds the SQLite database (WAL mode), the weather and normals cache, and the backups before upload.

**Keep one API process for now.** Rate limits and the weather single-flight are kept in memory, and SQLite takes one writer. Going above one process needs Redis (`REDIS_URL`) for the limits and Postgres for the database (spec §4), and neither is built yet.

The local load test (`docs/launch/load_test_results.md`) handled about 67 requests/s at the evening-peak mix on one laptop process, with p95 0.13 s.

## 2. Container hardening (spec §8.10)

- **Base images are pinned by digest** (`python:3.11-slim@sha256:…`, `node:22-slim@sha256:…`). To refresh them:
  1. Look up the current digest: `docker buildx imagetools inspect python:3.11-slim`, and the same for `node:22-slim`.
  2. Put the new digests in the `Dockerfile`.
  3. Rebuild and run the tests plus `scripts/attack_smoke.py`.
- **Python packages are installed from `apps/api/requirements.lock` with `--require-hashes`.**
  - After changing `requirements.txt`, run `python scripts/lock_requirements.py`, then `pip-audit --no-deps --disable-pip -r apps/api/requirements.lock`.
  - CI audits both files, and also runs `bandit`.
- **The container runs as a non-root user** (uid 10001). The code and `data/` are owned by root and made read-only in the image.
- **Run with a read-only root filesystem.** The only writable places are the `/state` volume and a tmpfs at `/tmp`:

  ```
  docker run -d --name thandak-api --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
    --cap-drop ALL --security-opt no-new-privileges \
    -v thandak-state:/state --env-file /secure/thandak.env -p 127.0.0.1:8000:8000 thandak:<git-sha>
  docker run -d --name thandak-jobs --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m \
    --cap-drop ALL --security-opt no-new-privileges \
    -v thandak-state:/state --env-file /secure/thandak.env thandak:<git-sha> python -m app.jobs
  ```

- **Keep secrets out of the image.** `.dockerignore` keeps `.env` files, local databases, backups and `.cache` out. Secrets come from the host's secret store or an env file outside the repo, readable only by the deploy user.
- **Data integrity:** with `ENV=prod`, the API refuses to start if any file in `data/` doesn't match `data/MANIFEST.json`.

## 3. Network

- Serve over **HTTPS only**, behind a CDN or WAF. The container listens on 127.0.0.1 or a private network only.
- Set `TRUSTED_PROXY_CIDRS` to the proxy's addresses only. `X-Forwarded-For` is trusted only from those addresses, and uvicorn's own proxy handling is off.
- Set `ALLOWED_HOSTS` to the public host names and `THANDAK_ORIGINS` to the website origin. Credentials are never allowed in CORS.
- HSTS is sent when `ENV=prod`. Docs routes stay off (`DOCS_ENABLED` unset).
- Block `/internal/*` at the proxy for everything except the jobs and monitoring hosts. They also need `x-job-secret`.

## 4. Settings

Names are in `env.example`. For production:

| Setting | Value |
|---|---|
| `ENV` | `prod` |
| `TOKEN_PEPPER`, `PHONE_HMAC_KEY`, `LOG_HASH_SECRET`, `INTERNAL_JOB_SECRET`, `WHATSAPP_WEBHOOK_SECRET`, `SMS_WEBHOOK_SECRET` | 32+ random bytes each, different from each other and from every test value |
| `PHONE_ENC_KEYS`, `PERSON_ENC_KEYS`, `BACKUP_ENC_KEY` | 32-byte keys, base64 (key rings: `id:key,…`; the first one encrypts) |
| `ALLOWED_HOSTS`, `THANDAK_ORIGINS`, `TRUSTED_PROXY_CIDRS` | Section 3 |
| `SENTRY_DSN` | The project DSN (PII is off and the scrubber is tested) |
| `ALERTS_ENABLED_GLOBAL` | `false` until the pilot (`docs/launch/PILOT_PLAN.md`) |
| `ALERT_TEST_ALLOWLIST` | Set by the team only |
| `HOUSEHOLDS_ENABLED`, `IMD_ENABLED` | `false` until their prerequisites are met (TEAM_TODO) |
| `RATE_STATELESS_PER_MIN` | 300 to start; tune from `/internal/metrics` |

To generate a key: `python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"`.

To rotate a key ring: put the new key first and keep the old one. The old key can be dropped once every row is re-encrypted (TEAM_TODO: re-encryption job).

## 5. Database and migrations

- The API and jobs containers run `alembic upgrade head` at start (`db.migrate()`), so start them one after the other on an upgrade.
- Before an upgrade, take a backup (section 6). To roll back: `alembic downgrade -1` in a one-off container, then deploy the old image.

## 6. Backups (spec §8.11)

- **How backups are made:** the `backup` job runs at 02:00 IST. It writes an AES-GCM encrypted copy to `BACKUP_DIR` and keeps 14 days of copies.
- **Getting them off the server:** copying to object storage is not in the app yet. A host cron job syncs `BACKUP_DIR` to a private bucket that keeps objects for 14 days and allows only the backup writer and two named people (TEAM_TODO: choose the bucket and who has access). For example, at 02:30: `rclone sync /var/lib/docker/volumes/thandak-state/_data/backups remote:thandak-backups`.
- **Restoring:** `python -m app.backup restore <file.db.enc> <new.db>` needs `BACKUP_ENC_KEY`. Check the restored copy with `sqlite3 new.db "pragma integrity_check"`, stop both containers, swap the file into `/state` and start them again.
- **Restore tests:** done in Phase 2 and again in Phase 7 (`docs/launch/GATE_P7_launch.md`). Repeat one every month.

## 7. After each deploy

1. `GET /api/health`: `db_ok`, `gazetteer_loaded` and `weather_last_ok_at` are set after the first request.
2. `python scripts/attack_smoke.py https://<host> --i-own-this-host` (it ends with a flood, so run it from an IP you don't need for the next minute).
3. `GET /internal/metrics` with the job secret.
4. Sentry shows no new errors.

## 8. Monitoring

- **Daily checks:** Sentry, `/internal/metrics` (requests, latency, cache hits, weather errors and budget, alerts sent/failed/opened, OTP cap) and the jobs container log (one line per job run).
- **Alert the on-call person if:**
  - `/api/health` fails for 5 minutes;
  - weather errors go above 5% in an hour;
  - the `backup` job doesn't run for 26 hours;
  - the OTP cap is 80% used.
- **When something goes wrong:** follow `docs/INCIDENT.md`.
