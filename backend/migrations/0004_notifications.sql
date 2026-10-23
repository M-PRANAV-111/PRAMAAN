CREATE TABLE notifications (
 id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL,
 title TEXT NOT NULL, body TEXT NOT NULL, link TEXT NOT NULL, application_id TEXT REFERENCES applications(id),
 finding_id TEXT REFERENCES findings(id), created_at TEXT NOT NULL, read_at TEXT
);
CREATE INDEX idx_notifications_unread ON notifications(user_id, read_at, created_at);
