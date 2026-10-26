-- AI layer: response cache, daily usage counters, runtime state, per-document AI bookkeeping, grounded-extraction
-- suggestions, validated finding wording and job notes. Every AI-derived row is advisory; rules never read suggestions.

CREATE TABLE ai_cache (
  cache_key TEXT PRIMARY KEY,
  subject_sha256 TEXT NOT NULL,
  task TEXT NOT NULL,
  model TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  variant TEXT NOT NULL,
  response_json TEXT NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_ai_cache_subject ON ai_cache(subject_sha256, task);

CREATE TABLE ai_usage_daily (
  day TEXT PRIMARY KEY,
  requests INTEGER NOT NULL DEFAULT 0,
  pages INTEGER NOT NULL DEFAULT 0,
  cache_hits INTEGER NOT NULL DEFAULT 0,
  failures INTEGER NOT NULL DEFAULT 0,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  latency_ms INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE ai_state (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE ai_documents (
  document_id TEXT PRIMARY KEY REFERENCES documents(id),
  synthetic INTEGER,
  step_status TEXT NOT NULL CHECK (step_status IN ('RAN','SKIPPED','NOT_NEEDED')),
  skip_reason TEXT,
  provider TEXT,
  model TEXT,
  cache_hit INTEGER NOT NULL DEFAULT 0,
  classification_json TEXT,
  updated_at TEXT NOT NULL
);

CREATE TABLE ai_suggestions (
  id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES documents(id),
  application_id TEXT NOT NULL REFERENCES applications(id),
  field TEXT NOT NULL,
  value TEXT NOT NULL,
  page INTEGER,
  quote TEXT,
  reason TEXT NOT NULL CHECK (reason IN ('not_found_on_page','conflicts_with_page','low_confidence')),
  model TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CONFIRMED','DISMISSED')),
  created_at TEXT NOT NULL
);
CREATE INDEX idx_ai_suggestions_doc ON ai_suggestions(document_id);
CREATE INDEX idx_ai_suggestions_app ON ai_suggestions(application_id, status);

CREATE TABLE finding_ai_text (
  finding_id TEXT PRIMARY KEY REFERENCES findings(id),
  input_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('accepted','rejected')),
  language TEXT NOT NULL DEFAULT 'en',
  text TEXT,
  model TEXT,
  reject_reason TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE job_notes (
  id TEXT PRIMARY KEY,
  job_id TEXT NOT NULL REFERENCES jobs(id),
  level TEXT NOT NULL CHECK (level IN ('INFO')),
  text TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX idx_job_notes_job ON job_notes(job_id)
