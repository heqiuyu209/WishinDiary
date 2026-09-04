from contextlib import contextmanager
from dbutils.pooled_db import PooledDB
import pymysql
from app.core.config import settings

# 显式导出，便于测试环境重建连接池
__all__ = ["PooledDB", "get_db_connection", "pool", "transaction"]

# 初始化连接池
pool = PooledDB(
    creator=pymysql,
    maxconnections=20,     # 连接池允许的最大连接数
    mincached=0,           # 延迟创建连接，避免导入阶段依赖数据库可用
    maxcached=10,          # 连接池中最多空闲连接数
    blocking=True,         # 连接池满时是否等待
    host=settings.DB_HOST,
    port=settings.DB_PORT,
    user=settings.DB_USER,
    password=settings.DB_PASSWORD,
    database=settings.DB_NAME,
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    connect_timeout=5,
    read_timeout=30,
    write_timeout=30,
)

def get_db_connection():
    """从连接池获取连接"""
    return pool.connection()


@contextmanager
def transaction():
    """统一数据库事务上下文。

    用法（service 层）::

        with transaction() as connection:
            with connection.cursor() as cursor:
                repository_write(cursor, ...)

    成功则自动 commit，异常则自动 rollback 并重新抛出，
    连接始终归还连接池。业务层可预期的失败通过抛出
    app.core.errors.AppError 表达，由全局异常处理器统一收敛。
    """
    connection = pool.connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
