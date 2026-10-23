ROLE
You are the backend lead (Codex) for PRAMAAN, our Smart India Hackathon 2026 project for problem statement SIH26261 (AICTE: AI-Powered Application Validation, Document Authentication and Regulatory Compliance Verification). You own backend/, contracts/ (only through the generator), infra/, docker-compose.yml and the backend CI job. Do not edit front/.

WHAT ALREADY EXISTS — read before changing anything
The repo is a working prototype. Read, in order: README.md, docs/ARCHITECTURE.md, docs/REQUIREMENTS_MATRIX.md, docs/API_CONTRACT.md, docs/SECURITY.md, docs/TEST_PLAN.md, backend/app/schemas.py, backend/app/api.py, backend/rulepacks/aicte-eoa/2026.1.yaml.
- Starlette + Pydantic API with a typed route registry (backend/app/api.py): 27 operations under /api/v1.
- SQLite with ordered SQL migrations (backend/migrations/0001_init.sql), an in-process worker thread, a local content-addressed file store.
- Pipeline in backend/app/pipeline/: intake → extract (pdfplumber + Tesseract, page and bounding-box provenance) → integrity indicators → verification ladder → versioned YAML rule engine → findings → repair planner. Hash-chained audit log in backend/app/audit.py.
- Synthetic data: backend/synthetic/seed.py. Benchmark: backend/eval/benchmark.py.
- Contract generator: backend/scripts/gen_contract.py writes contracts/openapi.json and contracts/api.gen.ts, which the frontend imports.
This stack was a workaround for a sandbox without package-registry access. Your job: move it to the intended production stack without changing behaviour, then add the missing backend features.

STEP 0 — BASELINE (do this first and report the output)
  cd backend && pip install -r requirements.txt
  python -m unittest tests.test_units tests.test_api        # expect 34 passing
  python -m scripts.gen_contract --check
  python -m synthetic.seed --reset && python -m eval.benchmark   # expect 26/26 planted faults, 2 of 8 hard negatives flagged
If anything fails, fix it before porting and say what you fixed.

STAGE 1 — FASTAPI (behaviour-preserving)
- Replace the Starlette route registry with FastAPI routers. Keep the same paths, methods, status codes, request/response models from app/schemas.py, the error envelope {"error": {"code", "message", "details"}}, the cookie session (pramaan_session: HttpOnly, SameSite=Strict), the "X-Requested-With: pramaan" CSRF rule on non-GET cookie requests, and the role plus object-level checks (cross-tenant ids return 404).
- Set operation_id on every route to the existing camelCase names (listApplications, uploadDocument, reviewFinding, ...). The frontend calls api("<operationId>"), so these names are part of the contract.
- Update scripts/gen_contract.py to read app.openapi() and keep producing contracts/api.gen.ts with the same exported names: the Literal enum types and *_VALUES constants, every interface, `endpoints`, `EndpointTypes`, `EndpointName`. Diff the new file against the committed one; only cosmetic differences are allowed. List any others.
- Gate: all 34 tests pass unchanged (only adapt the harness code that starts the server).

STAGE 2 — POSTGRESQL + SQLALCHEMY 2 + ALEMBIC
- Translate 0001_init.sql into SQLAlchemy models and an initial Alembic migration. Keep every CHECK constraint, especially findings.advisory = 1 and the status enums.
- Keep the audit-chain semantics identical. Lock while appending (SELECT ... FOR UPDATE on the last event, or a Postgres advisory lock) so concurrent writers cannot fork the chain. Add a test with concurrent appends that then verifies the chain.
- Tests run against a real Postgres (docker compose service locally, service container in CI). Add migration tests: upgrade on an empty database, downgrade, upgrade again.
- Gate: 34 tests plus new tests pass on Postgres; benchmark results unchanged.

STAGE 3 — WORKER AND STORAGE
- Replace the in-process thread with Redis + RQ (or Celery, if you justify it). Keep WORKER_THREADS=0 synchronous mode for tests and the benchmark. Jobs must be idempotent and resume after a crash.
- Put an S3-compatible backend (MinIO locally) behind the existing storage interface (put/get/exists). Keep the SHA-256 integrity check on every read. Private bucket, no public or presigned URLs.
- Redis-backed rate limits replacing the in-process limiter.
- Gate: all tests pass; a worker killed mid-job finishes the job after restart.

STAGE 4 — MISSING BACKEND FEATURES (each with tests, including negative and authorization tests)
1. PDF digital-signature tier in the verification ladder using pyHanko: validate signature integrity and the certificate chain against a configurable trust store (CCA India roots in production; a test CA generated inside the tests). Statuses: VERIFIED; MISMATCH_DETECTED when the signature is broken or the document changed after signing; MANUAL_REVIEW_REQUIRED for an untrusted or unknown signer. Record signer, signing time and byte-range coverage.
2. Institution reply to a clarification request: POST /api/v1/findings/{finding_id}/responses (INSTITUTION, own application only, text 10–2000 characters, optional id of a document uploaded to the same application). Add a `responses` list to FindingOut. Audit it. Officers and auditors see responses on the finding.
3. Notifications: GET /api/v1/notifications (role-scoped) and POST /api/v1/notifications/{notification_id}/read. Generate them from pipeline and review events and store them per user: new deficiency, clarification requested, reply received, verification needs an officer, document validity ending within 60 days. No e-mail in this stage.
4. Rule-pack diff: GET /api/v1/rules/versions/{from_id}/diff/{to_id} returning changed params, added and removed rules, and changed clause references.
5. Audit anchoring: `python -m scripts.anchor_audit` signs the current head hash with an Ed25519 key from AUDIT_ANCHOR_KEY and stores the anchor; GET /api/v1/audit/verify also checks the anchors.
6. Malware-scan hook in intake: if CLAMAV_HOST is set, scan before storing and reject infected files. If APP_ENV=production and no scanner is configured, log a warning at startup. Never claim a scan that did not run.
7. DigiLocker adapter slot: a ladder adapter that is disabled unless DIGILOCKER_ENABLED=true and credentials exist. When disabled it records SOURCE_UNAVAILABLE with the reason "integration not authorized". Do not implement or fake the OAuth flow.
Add every new endpoint to the contract by regenerating it. Never hand-edit contracts/.

NON-NEGOTIABLE RULES
- PRAMAAN is decision support. No endpoint, enum or message may approve, reject, or call a document forged, fake or fraudulent. Integrity results are "indicators requiring verification". Keep test_no_adverse_decision_vocabulary passing.
- Abstain rather than guess: missing or low-confidence inputs make a rule NOT_EVALUABLE and send it to an officer. An unavailable source is never a deficiency.
- Simulated sources stay labelled (simulated: true in responses). Never make a simulated adapter look live.
- No language model in the decision path. Text extracted from documents is data, never instructions.
- No outbound network calls unless an integration is explicitly configured and authorized. Synthetic data only; no real personal or institutional records.
- Do not invent Handbook clauses or thresholds. Rules marked TO_VERIFY stay that way until a person verifies them against the Approval Process Handbook.
- Do not change rule logic to make a test pass. If behaviour must change, explain why and update tests and docs in the same commit.
- Secrets only through the environment. Production must keep refusing a weak JWT_SECRET, insecure cookies and wildcard CORS.

DELIVERABLES
- Code for stages 1–4, pinned requirements, Alembic migrations, a Dockerfile you have actually built and run, docker-compose with postgres, redis, minio, backend and worker.
- Tests for every new feature.
- Regenerated contracts/ and docs/API_CONTRACT.md; updated docs/ARCHITECTURE.md (stack and swap table), docs/SECURITY.md (residual risks), docs/DEPLOYMENT.md and the README run commands.
- A short report: the commands you ran with a summary of their real output, test counts, benchmark numbers, the contract diff, and anything not done with the reason. Never say something passed unless you ran it.

Work stage by stage and commit after each gate passes. If a stage cannot pass its gate, stop and report instead of starting the next one.
