-- BRUCE RAG Knowledge DB Schema (RFC-001 v1.1 aligned)
-- PostgreSQL >= 15, pgvector >= 0.7.0

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Canonical library registry. IDs are fixed by routing ranges in the RFC.
CREATE TABLE IF NOT EXISTS bibliotheken (
    bib_id INT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    language VARCHAR(10) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Primary content table partitioned by bibliothek_id for planner pruning.
CREATE TABLE IF NOT EXISTS seiten (
    bib_id INT NOT NULL REFERENCES bibliotheken(bib_id),
    seite_id BIGINT GENERATED ALWAYS AS IDENTITY,
    title VARCHAR(512) NOT NULL,
    content TEXT NOT NULL,
    full_path VARCHAR(1024),
    imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (bib_id, seite_id)
) PARTITION BY RANGE (bib_id);

CREATE TABLE IF NOT EXISTS seiten_p01 PARTITION OF seiten
    FOR VALUES FROM (1) TO (1000);
CREATE TABLE IF NOT EXISTS seiten_p02 PARTITION OF seiten
    FOR VALUES FROM (1000) TO (2000);
CREATE TABLE IF NOT EXISTS seiten_p03 PARTITION OF seiten
    FOR VALUES FROM (2000) TO (3000);
CREATE TABLE IF NOT EXISTS seiten_p04 PARTITION OF seiten
    FOR VALUES FROM (3000) TO (4000);
CREATE TABLE IF NOT EXISTS seiten_p05 PARTITION OF seiten
    FOR VALUES FROM (4000) TO (5000);
CREATE TABLE IF NOT EXISTS seiten_p06 PARTITION OF seiten
    FOR VALUES FROM (5000) TO (6000);
CREATE TABLE IF NOT EXISTS seiten_p99 PARTITION OF seiten
    FOR VALUES FROM (9000) TO (10000);
CREATE TABLE IF NOT EXISTS seiten_p_misc PARTITION OF seiten DEFAULT;

CREATE TABLE IF NOT EXISTS vektoren (
    vektor_id BIGSERIAL PRIMARY KEY,
    bib_id INT NOT NULL,
    seite_id BIGINT NOT NULL,
    dims INT2[] NOT NULL,
    checksum INT8 NOT NULL UNIQUE,
    embedding_model VARCHAR(64) NOT NULL DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
    embedding_dim SMALLINT NOT NULL DEFAULT 64,
    cascade_level SMALLINT NOT NULL DEFAULT 0,
    cube_x SMALLINT,
    cube_y SMALLINT,
    cube_z SMALLINT,
    cube_w SMALLINT,
    cube_u SMALLINT,
    cube_v SMALLINT,
    cube_t SMALLINT,
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_vektoren_seiten
        FOREIGN KEY (bib_id, seite_id)
        REFERENCES seiten (bib_id, seite_id)
        ON DELETE CASCADE,
    CONSTRAINT chk_dims_len CHECK (array_length(dims, 1) = 64)
);

-- HNSW int2 opclass is available only on newer pgvector builds.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_opclass
        WHERE opcname = 'int2_cosine_ops'
    ) THEN
        EXECUTE '
            CREATE INDEX IF NOT EXISTS idx_vektoren_hnsw
            ON vektoren USING hnsw (dims int2_cosine_ops)
            WITH (m = 16, ef_construction = 128)
        ';
    ELSE
        RAISE NOTICE 'int2_cosine_ops not available, skipping idx_vektoren_hnsw in MVP';
    END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_vektoren_bib_cascade
    ON vektoren (bib_id, cascade_level);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id BIGSERIAL PRIMARY KEY,
    bib_id INT NOT NULL,
    seite_id BIGINT NOT NULL,
    chunk_index INT NOT NULL,
    text TEXT NOT NULL,
    vektor_id BIGINT REFERENCES vektoren(vektor_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (bib_id, seite_id, chunk_index),
    CONSTRAINT fk_chunks_seiten
        FOREIGN KEY (bib_id, seite_id)
        REFERENCES seiten (bib_id, seite_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_chunks_lookup
    ON chunks (bib_id, seite_id, chunk_index);

CREATE TABLE IF NOT EXISTS whitelist (
    whitelist_id BIGSERIAL PRIMARY KEY,
    pattern TEXT NOT NULL UNIQUE,
    match_type VARCHAR(10) NOT NULL DEFAULT 'exact',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_match_type CHECK (match_type IN ('exact', 'prefix', 'regex'))
);

CREATE TABLE IF NOT EXISTS routing_versions (
    version_id BIGSERIAL PRIMARY KEY,
    version_tag VARCHAR(32) NOT NULL UNIQUE,
    config_json JSONB NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    deployed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deployed_by VARCHAR(64) NOT NULL DEFAULT 'system',
    checksum INT8 GENERATED ALWAYS AS (hashtext(config_json::text)::INT8) STORED
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_routing_one_active
    ON routing_versions (is_active)
    WHERE is_active = TRUE;

CREATE OR REPLACE FUNCTION notify_routing_updated()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'routing_updated',
        json_build_object(
            'version_tag', NEW.version_tag,
            'is_active', NEW.is_active,
            'deployed_at', NEW.deployed_at
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_routing_updated ON routing_versions;
CREATE TRIGGER trg_routing_updated
AFTER INSERT OR UPDATE ON routing_versions
FOR EACH ROW EXECUTE FUNCTION notify_routing_updated();

CREATE OR REPLACE FUNCTION notify_whitelist_changed()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('whitelist_changed', '');
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_whitelist_changed ON whitelist;
CREATE TRIGGER trg_whitelist_changed
AFTER INSERT OR UPDATE OR DELETE ON whitelist
FOR EACH ROW EXECUTE FUNCTION notify_whitelist_changed();

-- Canonical seed libraries used by routing ranges.
INSERT INTO bibliotheken (bib_id, name, language)
VALUES
    (1, 'CODE', 'multi'),
    (1000, 'DOCS-DE', 'de'),
    (2000, 'BRUCE', 'multi'),
    (3000, 'DOCS-EN', 'en'),
    (4000, 'MATH', 'multi')
ON CONFLICT (bib_id) DO NOTHING;

-- Default whitelist bootstrap token. API treats this as allow-all in dev mode.
INSERT INTO whitelist (pattern, match_type)
VALUES ('__ALLOW_ALL__', 'exact')
ON CONFLICT (pattern) DO NOTHING;

-- Active MVP routing config (single BRUCE calc route + assembler fallback).
INSERT INTO routing_versions (version_tag, config_json, is_active, deployed_by)
VALUES (
    'v1.1-mvp',
    jsonb_build_object(
        'version', 1,
        'fallback_endpoint', 'http://assembler:8000',
        'ipc', jsonb_build_object(
            'max_pending_jobs', 50,
            'backpressure_http_status', 503
        ),
        'routes', jsonb_build_array(
            jsonb_build_object(
                'route_id', 3,
                'name', 'BRUCE',
                'endpoint', 'http://calc_bruce:8003',
                'bibliothek_id_range', jsonb_build_array(2000, 2999),
                'priority', 1,
                'confidence_threshold', 0.70,
                'timeout_ms', 1800,
                'max_retries', 1,
                'retry_backoff_ms', 100,
                'fail_fast_ms', 1400,
                'tags', jsonb_build_array('bruce', 'router', 'pipeline', 'state', 'assembler')
            ),
            jsonb_build_object(
                'route_id', 2,
                'name', 'DOCS_DE',
                'endpoint', 'http://calc_docs_de:8002',
                'bibliothek_id_range', jsonb_build_array(1000, 1999),
                'priority', 2,
                'confidence_threshold', 0.68,
                'timeout_ms', 1800,
                'max_retries', 1,
                'retry_backoff_ms', 100,
                'fail_fast_ms', 900,
                'tags', jsonb_build_array('docs', 'dokumentation', 'guide', 'startup')
            )
        )
    ),
    TRUE,
    'bootstrap'
)
ON CONFLICT (version_tag) DO UPDATE
SET
    config_json = EXCLUDED.config_json,
    is_active = EXCLUDED.is_active,
    deployed_at = NOW(),
    deployed_by = EXCLUDED.deployed_by;

COMMIT;
