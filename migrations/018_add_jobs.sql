CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    job_type TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    locked_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS jobs_status_available_idx ON jobs (status, available_at) WHERE status = 'queued';
CREATE INDEX IF NOT EXISTS jobs_status_failed_idx ON jobs (status) WHERE status = 'failed';
CREATE INDEX IF NOT EXISTS jobs_job_type_idx ON jobs (job_type);
