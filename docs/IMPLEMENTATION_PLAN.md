# Implementation plan and task division

## How this build was produced
The master prompt called for Codex (backend and integration) and Antigravity (frontend) working in parallel. Neither was available in this session, so **one agent executed both workstreams sequentially under one architecture**: contract first (`backend/app/schemas.py` → `contracts/`), then backend, then the web client against the generated contract, then end-to-end verification. No parallel coordination took place.

Package registries were unreachable from the build workspace, which set the stack (see [ARCHITECTURE §2](ARCHITECTURE.md#2-constraints-that-shaped-this-build)).

## Phases and status

| Phase | Deliverable | Status |
|---|---|---|
| 1 | Six-slide SIH content with verified references | Done — `docs/SIH_6_SLIDES.md` |
| 2 | Requirements traceability from the five proposals | Done — `docs/REQUIREMENTS_MATRIX.md` |
| 3 | Architecture, contract, plan | Done |
| 4 | README and supporting docs | Done |
| 5 | Backend vertical slice + intelligence + governance | Done, 34 tests passing |
| 6 | Web client | Done, type-checked, built |
| 7 | Integration (generated typed client, single origin) | Done, browser walkthrough passing |
| 8 | Security hardening, Docker, CI | Done in code; Docker not built here |
| 9 | Verification and delivery report | Done — `docs/TEST_PLAN.md` |

## Next work, in priority order

| # | Task | Owner (suggested) | Why first |
|---|---|---|---|
| 1 | Confirm SIH26261 wording and deadline on the SIH portal; fill Team ID and name on Slide 1 | Team lead | Submission blocker |
| 2 | Read APH 2024-25 to 2026-27 (EoA chapters and Chapter VI norms) and replace every `TO_VERIFY` clause and threshold | Rules & domain | Rules are only as good as their citations |
| 3 | Build Docker images once; fix anything that differs from the local run | Integration | Deployment claims depend on it |
| 4 | Run `npm install` and `npm run typecheck` with real `@types/react` | Frontend | Replaces the offline type shim |
| 5 | Collect a handful of *public* EoA letters (layout only) and add template variants; measure extraction on them | Document pipeline | First evidence beyond synthetic data |
| 6 | pyHanko signature validation with CCA trust roots as a ladder tier | Verification | Real cryptographic checks for signed PDFs |
| 7 | Alerts, rule-pack diff view, institution notifications | Frontend + backend | P2 items from the matrix |
| 8 | PostgreSQL + Redis worker; S3 storage | Integration | Only when moving beyond a single server |

## Team task division (six members)

| Workstream | Owns | First deliverable |
|---|---|---|
| Rules & domain research | `backend/rulepacks/`, rule tests | Verified clauses for all 17 rules |
| Document pipeline | `backend/app/pipeline/extract.py`, `doctypes.py`, `integrity.py` | Templates for real EoA letter layouts |
| Verification & audit | `verification.py`, `audit.py`, pyHanko tier | Signature tier with tests |
| Frontend & UX | `front/` | Real-types type-check, accessibility pass |
| Data, benchmark & demo | `synthetic/`, `eval/`, `docs/DEMO_GUIDE.md` | More fault types and harder look-alikes |
| Integration & security | `api.py`, `contracts/`, Docker, CI, `docs/SECURITY.md` | Docker build and CI green |

**Rules for working together:** the contract is changed only in `schemas.py` and regenerated (`python -m scripts.gen_contract`); CI fails on drift. Frontend code never invents endpoints — it calls `api("<operationId>")`. Merge only with tests passing.
