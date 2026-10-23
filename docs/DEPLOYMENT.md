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
python -m synthetic.seed      # demo only — never seed a production database with demo accounts
FRONT_DIST=$PWD/../front/dist uvicorn app.main:app --host 127.0.0.1 --port 8000 --proxy-headers
```

Put nginx (or the government data centre's load balancer) in front to terminate TLS and forward to `127.0.0.1:8000`. Run uvicorn under systemd with `Restart=always` and a dedicated non-root user that owns `DATA_DIR`.

## Option B — containers

```bash
cp .env.example .env    # fill in production values
docker compose up --build -d
# web client + API on http://localhost:8080 (put TLS in front)
docker compose exec backend python -m synthetic.seed   # demo data only
```

`backend` runs as UID 10001 with data in the `pramaan-data` volume and a health check on `/api/v1/health`. `front` is nginx serving the built client and proxying `/api` with the same security headers.

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
