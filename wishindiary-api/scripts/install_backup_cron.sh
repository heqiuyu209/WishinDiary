#!/usr/bin/env bash
# 安装自动化数据库备份 cron 任务（每 2:30 AM 执行一次，Docker Compose 环境）。
#
# 用法：
#   ./scripts/install_backup_cron.sh               # 写入当前用户 crontab（追加）
#   ./scripts/install_backup_cron.sh --preview     # 仅预览将写入的 cron 行，不修改
#
# 说明：
#   - 备份由 scripts/backup_database.sh 完成，输出到 wishindiary-api/backups/。
#   - 备份目录建议挂载到持久化存储（NFS / 对象存储同步），并保留足够天数。
#   - 若希望保留 N 天备份，可搭配下面的清理 cron 行（取消注释）。
#   - 非 systemd 环境（本机无 cron）可用计划任务/容器实现，见 docs/BACKUP_DR.md。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_SCRIPT="$PROJECT_DIR/scripts/backup_database.sh"
LOG_FILE="$PROJECT_DIR/backups/backup.log"

if [[ "${1:-}" == "--preview" ]]; then
    echo "将写入以下 cron 行（每日 02:30）："
    echo "  30 2 * * * cd $PROJECT_DIR && $BACKUP_SCRIPT 2>>$LOG_FILE"
    echo "  # 每日自动清理 30 天前的备份（可选，取消注释启用）:"
    echo "  # 40 2 * * * find $PROJECT_DIR/backups -name 'wishindiary-*.sql.gz' -mtime +30 -delete"
    exit 0
fi

# 备份目录与日志目录
mkdir -p "$PROJECT_DIR/backups"

CRON_LINE="30 2 * * * cd $PROJECT_DIR && $BACKUP_SCRIPT 2>>$LOG_FILE"

if crontab -l >/dev/null 2>&1; then
    EXISTING="$(crontab -l)"
else
    EXISTING=""
fi

if printf '%s\n' "$EXISTING" | grep -Fq "$BACKUP_SCRIPT"; then
    echo "已存在 backup_database.sh 的 cron 任务，跳过。"
    exit 0
fi

(printf '%s\n' "$EXISTING"; printf '%s\n' "$CRON_LINE") | crontab -
echo "已安装自动化备份 cron：每日 02:30 执行。"
crontab -l
