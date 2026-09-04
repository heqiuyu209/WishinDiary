import logging

import pymysql
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from app.routers.auth import router as auth_router
from app.routers.cycles import router as cycles_router
from app.routers.daily_logs import router as daily_logs_router
from app.routers.prediction import router as prediction_router
from app.routers.stats import router as stats_router
from app.routers.report import router as report_router
from app.routers.user_data import router as user_data_router
from app.core.config import settings
from app.core.database import get_db_connection
from app.core.csrf import CSRFSecurityMiddleware
from app.core.errors import register_exception_handlers
from app.core.logging_config import setup_logging
from app.core.sentry_client import init_sentry
from app.core.request_id import RequestIDMiddleware
from app.core.metrics import MetricsMiddleware, metrics_endpoint

logger = logging.getLogger(__name__)

# 可观测性：统一结构化日志 + 可选 Sentry（DSN 空则自动关闭）
setup_logging()
init_sentry()

app = FastAPI(title="WishinDiary API", version="2.0")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Cookie 认证的 CSRF 纵深防御：校验非安全方法的 Origin/Referer
app.add_middleware(CSRFSecurityMiddleware)

# 可观测性中间件（后添加者更外层，保证 request_id 最先执行）
app.add_middleware(MetricsMiddleware)
app.add_middleware(RequestIDMiddleware)

# 统一异常处理：所有错误收敛为 {"error": {"code", "message", "detail"}}
register_exception_handlers(app)

# 注册统一且最新的路由模块（业务接口全部挂 /api/v1 版本前缀）
app.include_router(auth_router)
app.include_router(cycles_router)  # 周期写入
app.include_router(daily_logs_router)  # 每日健康日志
app.include_router(prediction_router)  # 周期预测（特征提取 + prediction_logs 对账）
app.include_router(stats_router)  # 数据统计与仪表盘
app.include_router(report_router)
app.include_router(user_data_router)  # 健康数据导出与账号删除（数据可携带权/被遗忘权）

# 可选 Prometheus /metrics 端点（METRICS_ENABLED=true 时启用）
if settings.METRICS_ENABLED:
    app.add_api_route(
        "/metrics",
        metrics_endpoint,
        methods=["GET"],
        include_in_schema=False,
        tags=["Observability"],
    )


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
