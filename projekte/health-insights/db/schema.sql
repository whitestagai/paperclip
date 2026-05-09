-- Health Insights Phase 1 schema
-- Database: health (created separately via createdb)
-- Schema: paperclip_health

CREATE SCHEMA IF NOT EXISTS paperclip_health;
SET search_path TO paperclip_health;

-- Raw samples: each Apple Health datum, JSONB for flexibility
CREATE TABLE IF NOT EXISTS health_samples (
  id BIGSERIAL PRIMARY KEY,
  metric VARCHAR(64) NOT NULL,
  source VARCHAR(64),
  start_ts TIMESTAMPTZ NOT NULL,
  end_ts TIMESTAMPTZ,
  value DOUBLE PRECISION,
  unit VARCHAR(32),
  raw JSONB,
  ingested_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE (metric, source, start_ts)
);
CREATE INDEX IF NOT EXISTS idx_samples_metric_start
  ON health_samples (metric, start_ts DESC);
CREATE INDEX IF NOT EXISTS idx_samples_start_brin
  ON health_samples USING BRIN (start_ts);

-- Daily aggregates: pre-computed per (date, metric)
CREATE TABLE IF NOT EXISTS health_daily (
  date DATE NOT NULL,
  metric VARCHAR(64) NOT NULL,
  min DOUBLE PRECISION,
  max DOUBLE PRECISION,
  avg DOUBLE PRECISION,
  sum DOUBLE PRECISION,
  count INTEGER,
  computed_at TIMESTAMPTZ DEFAULT NOW(),
  PRIMARY KEY (date, metric)
);

-- Workouts: separate because of structure
CREATE TABLE IF NOT EXISTS health_workouts (
  id BIGSERIAL PRIMARY KEY,
  start_ts TIMESTAMPTZ NOT NULL,
  end_ts TIMESTAMPTZ NOT NULL,
  type VARCHAR(64),
  duration_sec INTEGER,
  active_energy_kcal DOUBLE PRECISION,
  distance_m DOUBLE PRECISION,
  avg_hr DOUBLE PRECISION,
  raw JSONB,
  UNIQUE (start_ts, type)
);
CREATE INDEX IF NOT EXISTS idx_workouts_start
  ON health_workouts (start_ts DESC);

-- Ingest run marker (used by Paperclip routine in Phase 2 to gate briefings)
CREATE TABLE IF NOT EXISTS health_ingest_runs (
  date DATE PRIMARY KEY,
  status VARCHAR(16) NOT NULL,
  files_processed INTEGER DEFAULT 0,
  samples_written INTEGER DEFAULT 0,
  finished_at TIMESTAMPTZ DEFAULT NOW()
);
