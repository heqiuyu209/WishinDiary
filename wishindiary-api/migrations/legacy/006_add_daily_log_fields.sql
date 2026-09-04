-- =====================================================================
-- 006: daily_logs 表新增三类自记录字段（睡眠/熬夜、用药记录、症状明细）
-- 项目：WishinDiary
-- 说明：本地 MySQL 为只读库，本文件由用户手动执行（禁止自动 DDL）。
--       与 migrations/legacy/schema.sql 中 daily_logs 定义保持同步。
-- 执行方式（示例）：
--   mysql -u<user> -p <db_name> < migrations/legacy/006_add_daily_log_fields.sql
-- 幂等性：本文件为一次性 ALTER；若重复执行会因列已存在而报错，属预期。
-- =====================================================================

ALTER TABLE daily_logs
    ADD COLUMN sleep_duration_minutes INT NOT NULL DEFAULT 0
        COMMENT '睡眠时长（分钟），0=未记录，取值范围 0~1440',
    ADD COLUMN sleep_quality INT NOT NULL DEFAULT 0
        COMMENT '睡眠质量：0=未填/很差 1=差 2=一般 3=好',
    ADD COLUMN is_late_night TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '是否熬夜：0=否 1=是',
    ADD COLUMN is_medication TINYINT(1) NOT NULL DEFAULT 0
        COMMENT '是否用药：0=否 1=是',
    ADD COLUMN medication_note VARCHAR(100) NULL
        COMMENT '用药说明（≤100字），未用药时可为空',
    ADD COLUMN symptom_levels JSON NOT NULL DEFAULT (JSON_OBJECT(
        'headache', 0,
        'bloat', 0,
        'breast_tenderness', 0,
        'fatigue', 0
    )) COMMENT '症状明细 JSON：键固定为 headache/bloat/breast_tenderness/fatigue，'
                '各取值 0=无 1=轻 2=中 3=重（应用层校验，DB 仅兜底 JSON_VALID）';

-- 取值域约束：睡眠时长 0~1440、睡眠质量 0~3（与既有 chk_daily_mood 等命名风格一致）
ALTER TABLE daily_logs
    ADD CONSTRAINT chk_daily_sleep_duration CHECK (sleep_duration_minutes BETWEEN 0 AND 1440),
    ADD CONSTRAINT chk_daily_sleep_quality CHECK (sleep_quality BETWEEN 0 AND 3),
    ADD CONSTRAINT chk_daily_symptom_levels CHECK (JSON_VALID(symptom_levels));

-- 回滚（如需撤销本迁移，手动执行以下语句）：
-- ALTER TABLE daily_logs
--     DROP CONSTRAINT chk_daily_symptom_levels,
--     DROP CONSTRAINT chk_daily_sleep_quality,
--     DROP CONSTRAINT chk_daily_sleep_duration;
-- ALTER TABLE daily_logs
--     DROP COLUMN symptom_levels,
--     DROP COLUMN medication_note,
--     DROP COLUMN is_medication,
--     DROP COLUMN is_late_night,
--     DROP COLUMN sleep_quality,
--     DROP COLUMN sleep_duration_minutes;
