-- Apply once to existing databases created before the hardened schema.sql.
-- Review the current schema before running in production.
ALTER TABLE cycles
    ADD CONSTRAINT chk_cycles_length CHECK (cycle_length IS NULL OR cycle_length BETWEEN 1 AND 120),
    ADD CONSTRAINT chk_cycles_bleeding CHECK (bleeding_days IS NULL OR bleeding_days BETWEEN 1 AND 30);

CREATE INDEX idx_prediction_pending
    ON prediction_logs (user_id, actual_date, created_at);
