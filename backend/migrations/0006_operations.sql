CREATE TABLE job_stage_durations (
 id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id),
 stage_code TEXT NOT NULL, seconds REAL NOT NULL CHECK(seconds >= 0)
);
CREATE INDEX idx_stage_durations_code ON job_stage_durations(stage_code);
