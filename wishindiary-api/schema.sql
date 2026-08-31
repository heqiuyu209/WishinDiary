CREATE DATABASE IF NOT EXISTS wishindiary_db DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE wishindiary_db;

-- 1. 用户表
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 生理周期表（带有唯一索引防重复打卡）
CREATE TABLE IF NOT EXISTS cycles (
    cycle_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE DEFAULT NULL,
    cycle_length INT DEFAULT NULL,
    bleeding_days INT DEFAULT NULL,
    UNIQUE KEY uk_user_start (user_id, start_date),
    CHECK (end_date IS NULL OR end_date >= start_date),
    CHECK (cycle_length IS NULL OR cycle_length BETWEEN 1 AND 120),
    CHECK (bleeding_days IS NULL OR bleeding_days BETWEEN 1 AND 30),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 每日精细化健康打卡与日志表
CREATE TABLE IF NOT EXISTS daily_logs (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    log_date DATE NOT NULL,
    mood_level INT DEFAULT 0,
    cramps_severity INT DEFAULT 0,
    is_exercise BOOLEAN DEFAULT FALSE,
    is_intercourse BOOLEAN DEFAULT FALSE,
    exercise_type VARCHAR(50) DEFAULT NULL,
    exercise_minutes INT DEFAULT 0,
    diet_tag VARCHAR(100) DEFAULT NULL,
    journal_text TEXT DEFAULT NULL,
    UNIQUE KEY uk_user_date (user_id, log_date),
    CHECK (mood_level BETWEEN 0 AND 3),
    CHECK (cramps_severity BETWEEN 0 AND 3),
    CHECK (exercise_minutes >= 0),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. AI 预测日志与误差对账表
CREATE TABLE IF NOT EXISTS prediction_logs (
    pred_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    predicted_date DATE NOT NULL,
    actual_date DATE DEFAULT NULL,
    error_days INT DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_prediction_pending (user_id, actual_date, created_at),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
