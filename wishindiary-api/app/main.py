import logging

import pymysql
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from app.routers.auth import router as auth_router
from app.routers.cycles import router as cycles_router
from app.routers.stats import router as stats_router
from app.routers.report import router as report_router
from app.core.config import settings
from app.core.database import get_db_connection

logger = logging.getLogger(__name__)

app = FastAPI(title="WishinDiary API", version="2.0")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# 注册统一且最新的路由模块
app.include_router(auth_router)
app.include_router(cycles_router)   # 周期写入、特征提取与 prediction_logs 对账
app.include_router(stats_router)    # 包含数据统计与仪表盘
app.include_router(report_router)

@app.get("/api/health")
def health_check():
    connection = None
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 AS healthy")
            cursor.fetchone()
    except pymysql.MySQLError:
        logger.exception("Health check database connection failed")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API 已启动，但数据库连接失败，请检查 wishindiary-api/.env",
        )
    finally:
        if connection is not None:
            connection.close()
    return {
        "status": "ok",
        "database": "connected",
        "message": "WishinDiary API is ready",
    }
