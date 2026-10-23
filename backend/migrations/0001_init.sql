-- PRAMAAN initial schema. Applied by app/db.py migration runner.

CREATE TABLE institutions (
  id TEXT PRIMARY KEY,
  aicte_permanent_id TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  state TEXT NOT NULL,
  trust_name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('INSTITUTION','OFFICER','ADMIN','AUDITOR')),
  institution_id TEXT REFERENCES institutions(id),
  password_hash TEXT NOT NULL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL,
  CHECK ((role = 'INSTITUTION') = (institution_id IS NOT NULL))
);

-- Simulated AICTE institutional records (stand-in for an authorized interface).
CREATE TABLE aicte_records (
  institution_id TEXT PRIMARY KEY REFERENCES institutions(id),
  approved_intake INTEGER NOT NULL,
  last_eoa_year TEXT NOT NULL,
  programmes_json TEXT NOT NULL,
  simulated INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE issuers (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  public_key_b64 TEXT NOT NULL,
  registry_available INTEGER NOT NULL DEFAULT 1,
  simulated INTEGER NOT NULL DEFAULT 1
);

-- Simulated issuer registry, looked up by certificate reference number.
CREATE TABLE issuer_registry (
  ref_no TEXT PRIMARY KEY,
  issuer_id TEXT NOT NULL REFERENCES issuers(id),
  doc_type TEXT NOT NULL,
  fields_json TEXT NOT NULL
);

CREATE TABLE rule_pack_versions (
  id TEXT PRIMARY KEY,
  pack TEXT NOT NULL,
  version TEXT NOT NULL,
  content_yaml TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PROPOSED','ACTIVE','RETIRED')),
  change_note TEXT NOT NULL DEFAULT '',
  proposed_by TEXT REFERENCES users(id),
  activated_by TEXT REFERENCES users(id),
  created_at TEXT NOT NULL,
  activated_at TEXT,
  UNIQUE (pack, version)
);

CREATE TABLE applications (
  id TEXT PRIMARY KEY,
  institution_id TEXT NOT NULL REFERENCES institutions(id),
  category TEXT NOT NULL,
  academic_year TEXT NOT NULL,
  status TEXT NOT NULL,
  created_by TEXT NOT NULL REFERENCES users(id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  submitted_at TEXT
);
CREATE INDEX idx_applications_institution ON applications(institution_id);

CREATE TABLE documents (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  doc_type TEXT NOT NULL,
  detected_type TEXT,
  original_name TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  mime TEXT NOT NULL,
  pages INTEGER NOT NULL,
  has_text_layer INTEGER NOT NULL DEFAULT 0,
  phash TEXT,
  uploaded_by TEXT NOT NULL REFERENCES users(id),
  uploaded_at TEXT NOT NULL,
  superseded_by TEXT REFERENCES documents(id),
  processing_state TEXT NOT NULL DEFAULT 'QUEUED' CHECK (processing_state IN ('QUEUED','PROCESSING','DONE','FAILED')),
  verification_status TEXT,
  extraction_json TEXT
);
CREATE INDEX idx_documents_application ON documents(application_id);
CREATE INDEX idx_documents_sha ON documents(sha256);

CREATE TABLE claims (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  application_id TEXT NOT NULL REFERENCES applications(id),
  field TEXT NOT NULL,
  value_raw TEXT NOT NULL,
  value_norm TEXT,
  value_type TEXT NOT NULL,
  page INTEGER NOT NULL,
  x0 REAL NOT NULL, y0 REAL NOT NULL, x1 REAL NOT NULL, y1 REAL NOT NULL,
  page_width REAL NOT NULL, page_height REAL NOT NULL,
  extractor TEXT NOT NULL,
  confidence REAL NOT NULL
);
CREATE INDEX idx_claims_document ON claims(document_id);

CREATE TABLE verifications (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  application_id TEXT NOT NULL REFERENCES applications(id),
  tier INTEGER NOT NULL,
  channel TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('VERIFIED','MISMATCH_DETECTED','EXPIRED','VERIFICATION_PENDING','SOURCE_UNAVAILABLE','MANUAL_REVIEW_REQUIRED')),
  simulated INTEGER NOT NULL,
  request_ref TEXT,
  response_hash TEXT,
  detail_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_verifications_document ON verifications(document_id);

CREATE TABLE integrity_signals (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  kind TEXT NOT NULL,
  detail_json TEXT NOT NULL,
  page INTEGER,
  bbox_json TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE validation_runs (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  rule_pack_version_id TEXT NOT NULL REFERENCES rule_pack_versions(id),
  trigger TEXT NOT NULL,
  affected_rules_json TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  summary_json TEXT
);

CREATE TABLE rule_results (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES validation_runs(id),
  application_id TEXT NOT NULL REFERENCES applications(id),
  rule_id TEXT NOT NULL,
  outcome TEXT NOT NULL CHECK (outcome IN ('PASS','FAIL','NOT_EVALUABLE','NOT_APPLICABLE')),
  proof_json TEXT NOT NULL
);
CREATE INDEX idx_rule_results_app ON rule_results(application_id);

CREATE TABLE findings (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  run_id TEXT NOT NULL REFERENCES validation_runs(id),
  fingerprint TEXT NOT NULL,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('RULE','INTEGRITY','DUPLICATE','VERIFICATION')),
  rule_id TEXT,
  title TEXT NOT NULL,
  severity TEXT NOT NULL CHECK (severity IN ('DEFICIENCY','REVIEW','INFO')),
  state TEXT NOT NULL CHECK (state IN ('OPEN','CONFIRMED','DISMISSED','ESCALATED','CLARIFICATION_REQUESTED','RESOLVED')),
  explanation TEXT NOT NULL,
  remedy TEXT NOT NULL,
  fix_doc_type TEXT,
  action_owner TEXT NOT NULL CHECK (action_owner IN ('INSTITUTION','OFFICER')),
  proof_json TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  advisory INTEGER NOT NULL DEFAULT 1 CHECK (advisory = 1),
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by_run TEXT
);
CREATE INDEX idx_findings_app ON findings(application_id, state);

CREATE TABLE reviews (
  id TEXT PRIMARY KEY,
  finding_id TEXT NOT NULL REFERENCES findings(id),
  reviewer_id TEXT NOT NULL REFERENCES users(id),
  decision TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  document_id TEXT REFERENCES documents(id),
  kind TEXT NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('QUEUED','RUNNING','DONE','FAILED')),
  stage TEXT NOT NULL,
  progress INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE audit_events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor_id TEXT,
  actor_role TEXT,
  action TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  application_id TEXT,
  payload_json TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL
);
CREATE INDEX idx_audit_app ON audit_events(application_id);
