-- BRUCE RAG Finish DB Schema (RFC-001 v1.1 aligned)

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS pipeline_jobs (
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trace_id VARCHAR(64) NOT NULL,
    query_text TEXT NOT NULL,
    state_vec INT2[7] NOT NULL,
    expected_routes INT[] NOT NULL,
    completed_routes INT[] NOT NULL DEFAULT '{}',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    deadline_at TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '5 seconds',
    retry_count SMALLINT NOT NULL DEFAULT 0,
    max_retries SMALLINT NOT NULL DEFAULT 3,
    last_error TEXT,
    next_retry_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT chk_status CHECK (status IN ('pending', 'ready', 'assembled', 'failed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_status_created
    ON pipeline_jobs (status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_retry
    ON pipeline_jobs (next_retry_at)
    WHERE status = 'failed' AND retry_count < max_retries;

CREATE INDEX IF NOT EXISTS idx_pipeline_jobs_query_trgm
    ON pipeline_jobs USING gin (query_text gin_trgm_ops);

CREATE TABLE IF NOT EXISTS calc_results (
    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES pipeline_jobs(job_id) ON DELETE CASCADE,
    route_id INT NOT NULL,
    route_name VARCHAR(32) NOT NULL,
    bausteine JSONB NOT NULL,
    source_seite_ids BIGINT[] NOT NULL DEFAULT '{}',
    duration_ms INT NOT NULL,
    model_version VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, route_id)
);

CREATE INDEX IF NOT EXISTS idx_calc_results_job_id
    ON calc_results (job_id);

CREATE TABLE IF NOT EXISTS final_answers (
    answer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL UNIQUE REFERENCES pipeline_jobs(job_id) ON DELETE CASCADE,
    answer_text TEXT NOT NULL,
    low_confidence_sections JSONB NOT NULL DEFAULT '[]'::JSONB,
    sources JSONB NOT NULL,
    assembly_quality_score REAL,
    timing JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trace_log (
    log_id BIGSERIAL PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL,
    stage VARCHAR(32) NOT NULL,
    duration_ms INT NOT NULL,
    gpu_device VARCHAR(16),
    model VARCHAR(64),
    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trace_log_trace_time
    ON trace_log (trace_id, logged_at DESC);

CREATE OR REPLACE FUNCTION bruce_after_calc_result()
RETURNS TRIGGER AS $$
DECLARE
    merged_routes INT[];
    expected INT[];
BEGIN
    UPDATE pipeline_jobs
    SET completed_routes = (
            SELECT ARRAY(
                SELECT DISTINCT route_id
                FROM unnest(completed_routes || NEW.route_id) AS route_id
                ORDER BY route_id
            )
        )
    WHERE job_id = NEW.job_id
    RETURNING completed_routes, expected_routes
    INTO merged_routes, expected;

    IF expected <@ merged_routes THEN
        UPDATE pipeline_jobs
        SET status = 'ready', completed_at = NOW()
        WHERE job_id = NEW.job_id AND status = 'pending';

        PERFORM pg_notify('assembly_ready', NEW.job_id::text);
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_after_calc_result ON calc_results;
CREATE TRIGGER trg_after_calc_result
AFTER INSERT ON calc_results
FOR EACH ROW EXECUTE FUNCTION bruce_after_calc_result();

COMMIT;
