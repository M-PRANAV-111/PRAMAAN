# Deployment — 27 October 2026

PRAMAAN runs on free tiers with the project's synthetic demo data. Use synthetic documents only.

| | |
|---|---|
| Public link | https://pramaan-sih.netlify.app |
| Backend (API, SQLite, OCR) | https://pramaan-api-qdbt.onrender.com |
| Netlify site | `pramaan-sih`, site id `26866ab0-b162-49d8-87ed-34146e75e68e`, account `m-pranav-111`, Free plan |
| Render service | `pramaan-api`, service id `srv-dbg5jnsipgvc73ejcjp0`, free instance, Singapore |
| Code | branch `integration/e2e`, commit `923df90` (the branch had not been merged into `main` on this date) |

The names `pramaan` and `praman` were already taken on Netlify by other sites, so the site is `pramaan-sih`.

## How it fits together

Netlify serves the built frontend (`front/dist`) and proxies `/api/*` to Render ([netlify.toml](../../netlify.toml)).
The browser sees a single address, so the `SameSite=Strict` session cookie works. `netlify.toml` also serves
`/sw.js`, `/manifest.webmanifest` and `/apple-touch-icon.png` from `assets/` and sets the security headers on the
page, the same way the backend does when it serves the frontend itself.

Render builds `backend/Dockerfile` (root directory `backend`). Its start command seeds the demo data and then
starts the API:

```
/bin/sh -c python -m synthetic.seed; exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips '*'
```

Render passes everything after `-c` as one argument and keeps quote characters. Do not wrap the script in double
quotes: the first deploy failed that way (`/bin/sh: 1: python -m synthetic.seed; …: not found`).

Render environment: `APP_ENV=development` (production mode refuses demo accounts), `COOKIE_SECURE=true`,
`SHOW_DEMO_ACCOUNTS=true`, `PORT=8000`, `LOGIN_RATE_PER_MINUTE=30`. `JWT_SECRET` was generated locally and sent only
to Render; it is not recorded anywhere. `SEED_DEMO_PASSWORD` holds the shared demo password and is not recorded here.

## Checks run on 27 October 2026

Against Render directly:

| Check | Result |
|---|---|
| `GET /api/v1/health` | 200 `{"status":"ok"}` |
| `GET /api/v1/ready` | 200; database, rule pack (2026.1), storage, OCR all ok |
| `GET /api/v1/meta` | 200; `demo_accounts` true, `ai` false |
| Sign in with each seeded account | 9 of 9 returned 200 |

Through https://pramaan-sih.netlify.app:

| Check | Result |
|---|---|
| `GET /` | 200, the PRAMAAN start page |
| `GET /api/v1/health`, `GET /api/v1/meta` | 200; `demo_accounts` true (proxy works) |
| Sign in as `nodal@deccan.synthetic.in` | 200, `Set-Cookie: pramaan_session` (`HttpOnly; Path=/; SameSite=strict; Secure`) |
| `GET /api/v1/auth/me`, same session | 200, Deccan Institute of Technology (Synthetic), role INSTITUTION |
| Sign in as `officer@aicte.synthetic.in`, `GET /api/v1/applications` | 200, 4 applications |
| Create an application, upload `D_Affidavit_2026-27.pdf` | 201, then 202; job went QUEUED → RUNNING → DONE |
| `/sw.js`, `/apple-touch-icon.png`, unknown `/api/` route | 200 JavaScript, 200 PNG, backend 404 JSON |

Before deploying: frontend build and typecheck passed; backend tests `Ran 228 tests`, `OK (skipped=3)`.

## Free-tier behaviour

- The Render service sleeps after 15 idle minutes. The first request after that takes about a minute, and Netlify
  may return an error while the service wakes; reload once it is up.
- Data (database and uploads) resets on every sleep, restart or deploy, and the demo data is seeded again on start.
- To keep it awake during a demo, add a free uptime monitor on
  `https://pramaan-api-qdbt.onrender.com/api/v1/health` every 5 minutes.
- The manifest is served as `application/octet-stream` (the backend uses `application/manifest+json`).

## Redeploying

- **Backend:** Render does not deploy on push. The service uses the public repository URL, and Render only
  auto-deploys from a connected Git provider. Use Manual Deploy → Deploy latest commit in the Render dashboard, or
  `POST /v1/services/srv-dbg5jnsipgvc73ejcjp0/deploys`. After `integration/e2e` is merged, change the service's
  branch to `main`.
- **Frontend:** from the repository root, run
  `npx netlify-cli deploy --prod --dir front/dist --site 26866ab0-b162-49d8-87ed-34146e75e68e`
  (the CLI runs the build from `netlify.toml` first).
