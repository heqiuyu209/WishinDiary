#!/usr/bin/env bash
# 从备份文件恢复 WishinDiary MySQL 数据库。
#
# 支持两种环境（与 backup_database.sh 对应）：
#   1. Docker Compose（默认）：通过 db 容器内 mysql 导入；
#   2. 本地 MySQL：设置 BACKEND_MODE=local，并用 DB_* 环境变量提供连接信息。
#
# 用法：
#   # Docker Compose 环境
#   ./scripts/restore_database.sh ./backups/wishindiary-20260901-120000.sql.gz
#
#   # 本地 MySQL 环境
#   BACKEND_MODE=local \
#   DB_HOST=127.0.0.1 DB_PORT=3306 DB_USER=wishin_app DB_PASSWORD=xxx DB_NAME=wishindiary_db \
#   ./scripts/restore_database.sh ./backups/wishindiary-20260901-120000.sql.gz
#
# 重要安全提示：
#   - 恢复会覆盖目标库中的同名表/记录，执行前必须先停止 API 写入；
#   - 建议先备份当前数据库（backup_database.sh）再执行恢复；
#   - 恢复后应运行 `alembic upgrade head` 确保迁移版本与备份一致。

set -euo pipefail

BACKEND_MODE="${BACKEND_MODE:-docker}"
BACKUP_FILE="${1:?用法: restore_database.sh <备份文件(.sql 或 .sql.gz)>}"

if [[ ! -f "$BACKUP_FILE" ]]; then
    echo "备份文件不存在: $BACKUP_FILE" >&2
    exit 1
fi

if [[ "$BACKEND_MODE" == "docker" ]]; then
    # 先确认容器与目标库可访问
    docker compose exec -T db sh -c \
        'mysqladmin ping -h localhost -u root -p"$MYSQL_ROOT_PASSWORD"' >/dev/null
    # gzip 自动解压导入；未压缩的 .sql 直接导入
    if [[ "$BACKUP_FILE" == *.gz ]]; then
        gzip -dc "$BACKUP_FILE" | docker compose exec -T db sh -c \
            'mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"'
    else
        docker compose exec -T db sh -c \
            'mysql -u root -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < "$BACKUP_FILE"
    fi
elif [[ "$BACKEND_MODE" == "local" ]]; then
    : "${DB_HOST:=127.0.0.1}"
    : "${DB_PORT:=3306}"
    : "${DB_USER:?DB_USER is required in local mode}"
    : "${DB_PASSWORD:?DB_PASSWORD is required in local mode}"
    : "${DB_NAME:?DB_NAME is required in local mode}"
    if [[ "$BACKUP_FILE" == *.gz ]]; then
        gzip -dc "$BACKUP_FILE" | MYSQL_PWD="$DB_PASSWORD" mysql \
            -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME"
    else
        MYSQL_PWD="$DB_PASSWORD" mysql \
            -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" "$DB_NAME" < "$BACKUP_FILE"
    fi
else
    echo "未知 BACKEND_MODE: $BACKEND_MODE（可选 docker / local）" >&2
    exit 1
fi

echo "恢复完成：$BACKUP_FILE"
echo "提示：请运行 'alembic upgrade head' 确保数据库迁移版本与代码一致。"
