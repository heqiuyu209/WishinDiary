import pytest
import pymysql
from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.core import database

TEST_DB_NAME = "wishindiary_test_db"


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """测试会话开始前，自动创建测试库并刷入最新的建表语句。

    关键：把 app.core.database 的连接池切换到测试库，
    避免测试误写生产库 (wishindiary_db)。
    """
    conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        autocommit=True
    )
    with conn.cursor() as cursor:
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {TEST_DB_NAME} DEFAULT CHARACTER SET utf8mb4;")
    conn.close()

    # 刷入基础 Schema
    db_conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=TEST_DB_NAME,
        autocommit=True
    )
    with db_conn.cursor() as cursor:
        # 依次清理并重建表结构
        cursor.execute("DROP TABLE IF EXISTS prediction_logs;")
        cursor.execute("DROP TABLE IF EXISTS daily_logs;")
        cursor.execute("DROP TABLE IF EXISTS cycles;")
        cursor.execute("DROP TABLE IF EXISTS users;")

        cursor.execute("""
                       CREATE TABLE users
                       (
                           user_id         INT AUTO_INCREMENT PRIMARY KEY,
                           username        VARCHAR(50) UNIQUE NOT NULL,
                           password_hash   VARCHAR(255)       NOT NULL
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                       """)
        cursor.execute("""
                       CREATE TABLE cycles
                       (
                           cycle_id      INT AUTO_INCREMENT PRIMARY KEY,
                           user_id       INT  NOT NULL,
                           start_date    DATE NOT NULL,
                           end_date      DATE DEFAULT NULL,
                           cycle_length  INT  DEFAULT NULL,
                           bleeding_days INT  DEFAULT NULL,
                           UNIQUE KEY uk_user_start (user_id, start_date),
                           CHECK (end_date IS NULL OR end_date >= start_date),
                           CHECK (cycle_length IS NULL OR cycle_length BETWEEN 1 AND 120),
                           CHECK (bleeding_days IS NULL OR bleeding_days BETWEEN 1 AND 30),
                           FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                       """)
        cursor.execute("""
                       CREATE TABLE daily_logs
                       (
                           log_id           INT AUTO_INCREMENT PRIMARY KEY,
                           user_id          INT  NOT NULL,
                           log_date         DATE NOT NULL,
                           mood_level       INT          DEFAULT 0,
                           cramps_severity  INT          DEFAULT 0,
                           is_exercise      BOOLEAN      DEFAULT FALSE,
                           is_intercourse   BOOLEAN      DEFAULT FALSE,
                           exercise_type    VARCHAR(50)  DEFAULT NULL,
                           exercise_minutes INT          DEFAULT 0,
                           diet_tag         VARCHAR(100) DEFAULT NULL,
                           journal_text     TEXT         DEFAULT NULL,
                           UNIQUE KEY uk_user_date (user_id, log_date),
                           CHECK (mood_level BETWEEN 0 AND 3),
                           CHECK (cramps_severity BETWEEN 0 AND 3),
                           CHECK (exercise_minutes >= 0),
                           FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                       """)
        cursor.execute("""
                       CREATE TABLE prediction_logs
                       (
                           pred_id         INT AUTO_INCREMENT PRIMARY KEY,
                           user_id         INT  NOT NULL,
                           predicted_date  DATE NOT NULL,
                           actual_date     DATE DEFAULT NULL,
                           error_days      INT  DEFAULT NULL,
                           created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                           KEY idx_prediction_pending (user_id, actual_date, created_at),
                           FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
                       ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                       """)
    db_conn.close()

    # 让应用连接池指向测试库，隔离生产数据
    database.pool.close()
    database.pool = database.PooledDB(
        creator=pymysql,
        maxconnections=20,
        mincached=0,
        maxcached=5,
        blocking=True,
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=TEST_DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    yield
    # 测试结束后还原
    database.pool.close()
    database.pool = database.PooledDB(
        creator=pymysql,
        maxconnections=20,
        mincached=5,
        maxcached=10,
        blocking=True,
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


@pytest.fixture(autouse=True)
def truncate_tables():
    """每个 test 函数运行后自动清空数据，实现测试用例数据隔离"""
    yield
    db_conn = pymysql.connect(
        host=settings.DB_HOST,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=TEST_DB_NAME,
        autocommit=True
    )
    with db_conn.cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        cursor.execute("TRUNCATE TABLE prediction_logs;")
        cursor.execute("TRUNCATE TABLE daily_logs;")
        cursor.execute("TRUNCATE TABLE cycles;")
        cursor.execute("TRUNCATE TABLE users;")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
    db_conn.close()


@pytest.fixture
def client():
    """ FastApi 测试客户端 """
    return TestClient(app)


@pytest.fixture
def auth_header(client):
    """ 注册并登录测试用户，返回带有 Bearer Token 的 Header """
    user_payload = {"username": "test_user", "password": "password123"}
    client.post("/api/auth/register", json=user_payload)
    response = client.post("/api/auth/login", json=user_payload)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
