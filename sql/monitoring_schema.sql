
CREATE SCHEMA IF NOT EXISTS monitoring;

-- 1. ETL execution history
CREATE TABLE IF NOT EXISTS monitoring.etl_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_name VARCHAR(150) NOT NULL,
    start_time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP,
    duration_seconds NUMERIC(12, 3),
    status VARCHAR(20) NOT NULL DEFAULT 'RUNNING'
        CHECK (status IN ('RUNNING', 'SUCCESS', 'FAILED', 'PARTIAL')),
    source_name VARCHAR(255),
    extracted_records BIGINT DEFAULT 0,
    loaded_records BIGINT DEFAULT 0,
    rejected_records BIGINT DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Data quality check results
CREATE TABLE IF NOT EXISTS monitoring.data_quality_results (
    result_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL
        REFERENCES monitoring.etl_runs(run_id) ON DELETE CASCADE,
    category VARCHAR(50) NOT NULL,
    check_name VARCHAR(200) NOT NULL,
    table_name VARCHAR(150),
    column_name VARCHAR(150),
    total_records BIGINT DEFAULT 0,
    failed_records BIGINT DEFAULT 0,
    quality_score NUMERIC(6, 2),
    status VARCHAR(20) NOT NULL,
    details TEXT,
    checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. ETL error history
CREATE TABLE IF NOT EXISTS monitoring.etl_errors (
    error_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL
        REFERENCES monitoring.etl_runs(run_id) ON DELETE CASCADE,
    error_type VARCHAR(150),
    error_message TEXT NOT NULL,
    source_file VARCHAR(500),
    occurred_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for dashboard queries
CREATE INDEX IF NOT EXISTS idx_etl_runs_start_time
ON monitoring.etl_runs(start_time);

CREATE INDEX IF NOT EXISTS idx_etl_runs_status
ON monitoring.etl_runs(status);

CREATE INDEX IF NOT EXISTS idx_quality_results_run_id
ON monitoring.data_quality_results(run_id);

CREATE INDEX IF NOT EXISTS idx_quality_results_status
ON monitoring.data_quality_results(status);

CREATE INDEX IF NOT EXISTS idx_etl_errors_run_id
ON monitoring.etl_errors(run_id);
