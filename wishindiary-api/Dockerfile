FROM python:3.12.14-slim

WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY app ./app
COPY ml ./ml
COPY alembic.ini .
COPY migrations ./migrations

# 创建非 root 运行用户
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# 启动前先执行数据库迁移（Alembic），保证表结构与迁移版本一致
# --proxy-headers --forwarded-allow-ips=172.16.0.0/12：
#   compose 网络内 frontend(Nginx) 容器通过 backend:8000 反代并透传 X-Forwarded-For，
#   为让限流/审计拿到真实客户端 IP，仅信任 Docker 私有网段（172.16.0.0/12，RFC1918），
#   切勿放宽为 *（会信任任意来源伪造 IP）。宿主直连 127.0.0.1:8000 不受影响（无 XFF 时用真实 peer）。
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=172.16.0.0/12"]
