# Deployment

> Status: the single-process mode (uvicorn serving the API and the built client) was run and tested in the development workspace, without nginx or TLS. The Docker images and compose file were written but **not built there** (no Docker daemon was available). Build them once on a machine with Docker before relying on them.

## Option A — single server, one process (simplest)

```bash
# on an Ubuntu 22.04+/24.04 VM
sudo apt install -y python3.12-venv tesseract-ocr nodejs npm
git clone <repo> pramaan && cd pramaan
cd front && npm install && npm run build && cd ..
cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
cp ../.env.example ../.env   # set APP_ENV=production, a 64-char JWT_SECRET, COOKIE_SECURE=true, DATA_DIR=/var/lib/pramaan
set -a; . ../.env; set +a
FRONT_DIST=$PWD/../front/dist uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Put nginx (or the government data centre's load balancer) in front to terminate TLS and forward to `127.0.0.1:8000`. Run uvicorn under systemd with `Restart=always` and a dedicated non-root user that owns `DATA_DIR`.

## Option B — containers

```bash
cp .env.example .env    # fill in production values
docker compose up --build -d
# web client + API on http://localhost:8080 (put TLS in front)
```

`backend` runs as UID 10001 with data in the `pramaan-data` volume and a health check on `/api/v1/health`. `front` is nginx serving the built client and proxying `/api` with the same security headers. Seed synthetic data only in a separate development instance; production refuses the seed command.

## HTTPS
- Terminate TLS at nginx/LB with TLS 1.2+; redirect HTTP to HTTPS.
- `COOKIE_SECURE=true` (enforced in production) so the session cookie is HTTPS-only. HSTS is added by the API in production.
- Keep the API and web client on one origin so `SameSite=Strict` cookies work without CORS.

## Health and readiness
- Liveness: `GET /api/v1/health`
- Readiness: `GET /api/v1/ready` → 503 if the database, active rule pack, storage or OCR is unavailable.

## Configuration checklist (production)
`APP_ENV=production` · random `JWT_SECRET` ≥ 32 chars (64 recommended) · `COOKIE_SECURE=true` · `DATA_DIR` on an encrypted, backed-up volume · no `CORS_ORIGINS` unless needed · `WORKER_THREADS` ≥ 1 · Tesseract installed · integrations disabled until authorized.

## Backup and restore
Everything stateful is in `DATA_DIR`: `pramaan.sqlite3` (+ WAL files) and `files/` (content-addressed originals).

```bash
# online, consistent backup of the database, then the file store
sqlite3 $DATA_DIR/pramaan.sqlite3 ".backup '/backups/pramaan-$(date +%F).sqlite3'"
tar -C $DATA_DIR -czf /backups/pramaan-files-$(date +%F).tgz files
# restore: stop the service, copy both back, start, then check
curl -s localhost:8000/api/v1/ready && curl -s -b session localhost:8000/api/v1/audit/verify
```
After restore, verify the audit chain from the Audit page or `/api/v1/audit/verify`.

## Rollback
1. Keep the previous release directory (or image tag).
2. Stop the service, switch the symlink/tag back, start.
3. Migrations are forward-only; if a release added one, restore the database backup taken before the upgrade.
4. Rule-pack rollback needs no deployment: an administrator proposes the earlier parameters and a second administrator activates them.

## Retention
Define with AICTE under the DPDP Act 2023: how long originals, extracted values and decisions are kept, and how deletion requests are handled. The audit log should outlive the documents it references.

## Scaling path
SQLite + in-process worker suits a single server. For more load: PostgreSQL (migrations are ANSI-leaning), a Redis/RQ worker pool, S3-compatible object storage behind the `LocalStorage` interface, and Redis-backed rate limits. No Kubernetes is needed for a pilot.

## Core backend configuration (23 October 2026)

New variables are documented in `.env.example`. Empty values select defaults. Environment files are examples, not automatically loaded by the Python application; load them with your platform's secret manager or environment-file support.

| Variables | Purpose / defaults |
|---|---|
| `PUBLIC_BASE_URL` | Absolute URL for account links, default `http://localhost:8000`; public HTTPS required in production |
| `EMAIL_PROVIDER`, `EMAIL_FROM` | `console`, `smtp` or `resend`; console is development/test only; configure a verified sender for live delivery |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | SMTP with mandatory STARTTLS; port defaults to 587 |
| `RESEND_API_KEY` | Needed only for the Resend provider |
| `NOTIFY_EMAIL` | Optional generic notification emails; defaults false |
| `JOB_TIMEOUT_SECONDS` | Job execution deadline, default 300; production worker threads supervise a separate subprocess per job |
| `BACKUP_SCHEDULE`, `BACKUP_HOUR_UTC` | Enable an in-process daily backup; default false, hour 2 UTC |
| `BACKUP_S3_ENDPOINT`, `BACKUP_S3_BUCKET`, `BACKUP_S3_KEY_ID`, `BACKUP_S3_SECRET` | Optional S3-compatible target; configure all four; HTTPS required |
| `LOG_FORMAT` | `text` (default) or JSON request records |
| `METRICS_TOKEN` | Separate Bearer secret for `/api/v1/metrics`; empty disables the endpoint |
| `SENTRY_DSN` | Optional scrubbed exception reporting; `sentry-sdk` is imported only when set |
| `TRUST_PROXY` | False locally; defaults true when Railway/Fly markers are present; only enable behind restricted trusted ingress |
| `DEMO_ACCOUNTS` | Defaults false; production refuses it, `SEED_DEMO_PASSWORD`, and existing synthetic accounts |

Install `backend/requirements.txt`; `boto3` is used only by optional backup uploads. Configure `WORKER_THREADS>=1` for hard timeouts. Use one ASGI process for the SQLite/in-memory limiter design; the instance lock deliberately refuses a second server using the same data directory. Keep migrations `0002`–`0007` with this release and never edit an applied migration. Existing users remain verified and institutions remain active; sessions from before this release require a new login.

For a local console-email journey, start with `APP_ENV=development`, set `PUBLIC_BASE_URL` to the actual local origin, register, read the `.eml` under `DATA_DIR/outbox`, follow its verification link, and accept the registration as an administrator. Staff administration requires an existing administrator provisioned by the operator; production has no public administrator bootstrap. The synthetic seed is for isolated development data only and refuses production.

### Managed backups

From `backend/`, run `python -m scripts.backup`. Each successful set under `DATA_DIR/backups` has `backup-<UTC timestamp>-<random suffix>.sqlite3`, `.tar.gz` and `.json` manifest files. The newest 14 completed sets are retained locally and, when configured, under the dedicated `pramaan-backups/` S3 prefix. Partial local sets are not announced as successful. `SystemOut.backups.last_ok_at` comes from the last successful database/store backup and optional upload.

Stop the server before `python -m scripts.backup --restore <backup-name>`. Restore verifies checksums, database integrity and archive paths, restores files and atomically replaces the SQLite file. An active server's OS lock refuses the operation. Extra immutable store objects may remain; the restored database decides which objects are reachable. After restarting, check `/ready` and verify the audit chain. Local round-trip restore and live-instance refusal are automated tests; S3 has not been exercised against a live bucket.

The scheduler checks UTC once per minute and retries a failed backup during its configured hour. It does not catch up a missed day while the instance was stopped. The email queue is also in-memory; use an external durable queue before requiring guaranteed delivery across process crashes. No outbound AI, DigiLocker or real issuer integration is enabled by this change.
