CREATE TABLE finding_responses (
 id TEXT PRIMARY KEY, finding_id TEXT NOT NULL REFERENCES findings(id), author_id TEXT NOT NULL REFERENCES users(id),
 text TEXT NOT NULL, document_id TEXT REFERENCES documents(id), created_at TEXT NOT NULL
);
CREATE INDEX idx_responses_finding ON finding_responses(finding_id, created_at);
CREATE INDEX idx_documents_version ON documents(application_id, doc_type, uploaded_at);
CREATE INDEX idx_applications_submitted ON applications(submitted_at);
