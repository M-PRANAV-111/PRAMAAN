ALTER TABLE users ADD COLUMN email_verified INTEGER NOT NULL DEFAULT 1;
ALTER TABLE users ADD COLUMN phone TEXT;
ALTER TABLE users ADD COLUMN last_login_at TEXT;
ALTER TABLE institutions ADD COLUMN status TEXT NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE institutions ADD COLUMN contact_email TEXT;
ALTER TABLE institutions ADD COLUMN address TEXT;
CREATE UNIQUE INDEX idx_users_email_lower ON users(lower(email));
CREATE UNIQUE INDEX idx_institutions_pid_lower ON institutions(lower(aicte_permanent_id));
CREATE TABLE sessions (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
 last_seen_at TEXT NOT NULL, expires_at TEXT NOT NULL, revoked_at TEXT, user_agent TEXT NOT NULL, ip_hint TEXT NOT NULL
);
CREATE INDEX idx_sessions_user ON sessions(user_id, revoked_at, expires_at);
CREATE TABLE one_time_tokens (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 purpose TEXT NOT NULL CHECK (purpose IN ('VERIFY_EMAIL','RESET_PASSWORD','INVITATION')),
 token_hash TEXT NOT NULL UNIQUE, expires_at TEXT NOT NULL, used_at TEXT, created_at TEXT NOT NULL
);
CREATE TABLE registrations (
 id TEXT PRIMARY KEY, institution_id TEXT NOT NULL REFERENCES institutions(id), user_id TEXT NOT NULL REFERENCES users(id),
 status TEXT NOT NULL CHECK (status IN ('PENDING','ACCEPTED','DECLINED')), reason TEXT,
 decided_by TEXT REFERENCES users(id), decided_at TEXT, created_at TEXT NOT NULL
);
CREATE INDEX idx_registrations_status ON registrations(status, created_at);
