#!/usr/bin/env bash
# 备份 WishinDiary MySQL 数据库。
#
# 支持两种环境：
#   1. Docker Compose（默认）：通过 db 容器内 mysqldump 导出；
#   2. 本地 MySQL：设置 BACKEND_MODE=local，并用 DB_* 环境变量提供连接信息。
#
# 用法：
#   # Docker Compose 环境（自动读取 compose 中的 DB_NAME/DB_ROOT_PASSWORD）
#   ./scripts/backup_database.sh [输出路径]
#
#   # 本地 MySQL 环境
#   BACKEND_MODE=local \
#   DB_HOST=127.0.0.1 DB_PORT=3306 DB_USER=wishin_app DB_PASSWORD=xxx DB_NAME=wishindiary_db \
#   ./scripts/backup_database.sh [输出路径]
#
# 输出默认到 ./backups/wishindiary-YYYYMMDD-HHMMSS.sql.gz（gzip 压缩）。
# 备份包含敏感健康数据：请勿提交 Git，建议使用加密存储。

set -euo pipefail

BACKEND_MODE="${BACKEND_MODE:-docker}"

# 输出路径解析
OUTPUT_PATH="${1:-}"
if [[ -z "$OUTPUT_PATH" ]]; then
    BACKUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/backups"
    mkdir -p "$BACKUP_DIR"
    OUTPUT_PATH="$BACKUP_DIR/wishindiary-$(date +%Y%m%d-%H%M%S).sql.gz"
else
    mkdir -p "$(dirname "$OUTPUT_PATH")"
fi

if [[ "$BACKEND_MODE" == "docker" ]]; then
    # Docker Compose：容器内 mysqldump，压缩后写到宿主机
    umask 077
    docker compose exec -T db sh -c \
        'mysqldump -u root -p"$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers "$MYSQL_DATABASE"' \
        | gzip > "$OUTPUT_PATH"
elif [[ "$BACKEND_MODE" == "local" ]]; then
    : "${DB_HOST:=127.0.0.1}"
    : "${DB_PORT:=3306}"
    : "${DB_USER:?DB_USER is required in local mode}"
    : "${DB_PASSWORD:?DB_PASSWORD is required in local mode}"
    : "${DB_NAME:?DB_NAME is required in local mode}"
    umask 077
    MYSQL_PWD="$DB_PASSWORD" mysqldump \
        -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" \
        --single-transaction --routines --triggers "$DB_NAME" \
        | gzip > "$OUTPUT_PATH"
else
    echo "未知 BACKEND_MODE: $BACKEND_MODE（可选 docker / local）" >&2
    exit 1
fi

echo "备份完成：$OUTPUT_PATH"
ls -lh "$OUTPUT_PATH"
