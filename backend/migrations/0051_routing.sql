-- Routing recommendations: one row per computation, with the reasons and the automated actions taken.
-- A recommendation is advisory. It never changes the application's derived status.

CREATE TABLE routing_recommendations (
  id TEXT PRIMARY KEY,
  application_id TEXT NOT NULL REFERENCES applications(id),
  run_id TEXT REFERENCES validation_runs(id),
  outcome TEXT NOT NULL CHECK (outcome IN ('READY_FOR_SCRUTINY','CORRECTIONS_REQUIRED','OFFICER_REVIEW_REQUIRED')),
  reasons_json TEXT NOT NULL,
  actions_json TEXT NOT NULL,
  ai_used INTEGER NOT NULL DEFAULT 0,
  policy_version TEXT NOT NULL,
  state_key TEXT NOT NULL,
  queue_flag TEXT,
  computed_at TEXT NOT NULL
);
CREATE INDEX idx_routing_app ON routing_recommendations(application_id, computed_at)
