ALTER TABLE jobs ADD COLUMN stage_code TEXT;
ALTER TABLE jobs ADD COLUMN error_message TEXT;
ALTER TABLE jobs ADD COLUMN attempts INTEGER NOT NULL DEFAULT 0;
CREATE TABLE idempotency_keys (
 key TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id), application_id TEXT NOT NULL REFERENCES applications(id),
 response_json TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(key, user_id, application_id)
);
CREATE INDEX idx_idempotency_created ON idempotency_keys(created_at);
