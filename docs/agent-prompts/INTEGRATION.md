ROLE
You are the integration lead for PRAMAAN, our Smart India Hackathon 2026 project for SIH26261 (AICTE application validation, document authentication and regulatory compliance verification). The backend (backend/, contracts/) and the frontend (front/) were worked on by separate agents. Your job is to make them one product: one contract, one running stack, one test pipeline and accurate docs. Fix integration defects; do not add features.

READ FIRST
README.md, docs/ARCHITECTURE.md, docs/API_CONTRACT.md, docs/TEST_PLAN.md, docs/SECURITY.md, docs/DEPLOYMENT.md, docs/DEMO_GUIDE.md, docs/agent-prompts/BACKEND.md and FRONTEND.md, both agents' reports (ask me for them if they are not in the repo) and the git history of both workstreams.

1. CONTRACT
- Regenerate it: cd backend && python -m scripts.gen_contract. If the output differs from what is committed, commit it and explain the diff.
- Check every api("<operationId>") call and every response field the frontend reads against contracts/api.gen.ts. List the mismatches and fix each one on the side that is wrong. If the backend renamed something, either restore the name or update the frontend in the same commit.
- Remove any frontend mock that a real endpoint now covers, and make the production build fail if a mock flag is switched on.
- Confirm these enums are identical on both sides: application status, the six verification statuses (VERIFIED, MISMATCH_DETECTED, EXPIRED, VERIFICATION_PENDING, SOURCE_UNAVAILABLE, MANUAL_REVIEW_REQUIRED), rule outcomes, finding states and review decisions.

2. FULL STACK
- `docker compose up --build` must start postgres, redis, minio, the backend, the worker and the frontend from a clean clone with only .env filled in. Remove every undocumented manual step.
- Seed inside the stack, then run the Playwright suite against the stack, not against dev servers.
- Put a local TLS terminator in front (Caddy with an internal certificate, or mkcert with nginx) so APP_ENV=production and COOKIE_SECURE=true are exercised. Check that sign-in works, the cookie is Secure, HttpOnly and SameSite=Strict, HSTS is sent and CORS is not open.
- Check that /api/v1/ready returns 503 when postgres, redis, storage or OCR is down, and that the UI shows a clear message instead of a blank page.

3. END-TO-END ACCEPTANCE (all in the compose stack; keep evidence: test output, traces, screenshots)
 1. Institution signs in.
 2. Creates an application.
 3. Uploads all six demo documents from backend/var/demo_files and sees real progress.
 4. Extracted values show with their page and box positions.
 5. Findings appear with proof chains.
 6. A cross-document conflict shows both values and AICTE records as the tie-break.
 7. Rules apply per category (no change in intake vs intake increase).
 8. Across the seeded applications the verification ladder shows VERIFIED, MISMATCH_DETECTED, EXPIRED and SOURCE_UNAVAILABLE, with simulated sources labelled.
 9. An officer records a decision with a reason; the institution replies to a clarification request.
10. The audit trail shows each step, the chain verifies, and a direct database edit is detected.
11. Unauthorized access is rejected: another institution's application (404), an auditor recording a review (403), a missing CSRF header (403), no session (401).
12. Failure and recovery: stop the worker during an upload and restart it, and the job finishes; stop postgres, the UI shows the outage, restart it, and the app recovers.
Also confirm: uploading the renewed fire NOC re-runs only the rules that read it and resolves exactly one finding; the benchmark still reports 26/26 planted faults and the same hard-negative result (if the numbers change, explain why).

4. CI (.github/workflows/ci.yml)
Jobs: backend (postgres and redis service containers; unit, API and migration tests); contract drift check; frontend (typecheck, lint, unit tests, build); end-to-end (compose stack plus Playwright, uploading traces and screenshots on failure); security (pip-audit, npm audit --omit=dev at high severity, gitleaks, and a security-header check against the running stack). All jobs must be green to merge.

5. SAFEGUARD AUDIT (read the code; do not assume)
- Search both codebases for approve, reject, forged, fake and fraud in anything shown to users or returned by the API. There must be none.
- findings.advisory cannot be false at the database level.
- No outbound network calls except configured integrations (check for requests, httpx and fetch to external hosts).
- Simulated results are labelled in API responses and everywhere they appear in the UI.
- No committed secrets; .env.example has placeholders only; demo credentials are generated, not hard-coded.
- No endpoint lets an institution user see another institution's evidence, including duplicate findings and page images.

6. DOCS
Make README.md, docs/DEPLOYMENT.md, docs/TEST_PLAN.md and docs/DEMO_GUIDE.md match what actually runs: commands, ports, environment variables, test counts and screenshots. Update the "What is implemented" table honestly. Keep the technology table on Slide 3 of docs/SIH_6_SLIDES.md in line with the real stack.

RULES
- Never report a check as passing unless you ran it. Add a dated summary of the real output to docs/TEST_PLAN.md.
- Do not weaken a test, safeguard or security setting to get a green build. If something cannot be fixed, record it as a known defect with the reason.
- Do not change rule logic, thresholds or clause references.

FINAL REPORT
What you integrated; the contract diff; the acceptance checklist with pass or fail and evidence for each item; CI status; security findings; known defects; and what still needs AICTE authorization or real credentials (DigiLocker, issuer APIs, the AICTE portal and sign-on, verified Handbook clauses).
