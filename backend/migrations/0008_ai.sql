CREATE TABLE ai_calls (
 id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT REFERENCES jobs(id),
 provider TEXT NOT NULL, model TEXT NOT NULL, task TEXT NOT NULL,
 created_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'started'
);
CREATE INDEX ai_calls_day ON ai_calls(created_at);
CREATE TABLE ai_job_notes (
 job_id TEXT NOT NULL REFERENCES jobs(id), reason TEXT NOT NULL,
 PRIMARY KEY(job_id,reason)
);
CREATE TABLE ai_suggestions (
 id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL REFERENCES documents(id),
 field TEXT NOT NULL, value TEXT NOT NULL, page INTEGER, reason TEXT NOT NULL, model TEXT NOT NULL
);
CREATE TABLE ai_explanations (
 finding_id TEXT PRIMARY KEY REFERENCES findings(id), template_text TEXT NOT NULL,
 explanation TEXT NOT NULL, model TEXT NOT NULL
);
CREATE TABLE application_routing (
 application_id TEXT PRIMARY KEY REFERENCES applications(id), outcome TEXT NOT NULL,
 reasons_json TEXT NOT NULL, updated_at TEXT NOT NULL
);
