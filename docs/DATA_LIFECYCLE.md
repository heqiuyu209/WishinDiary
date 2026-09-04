# 健康数据生命周期管理

本文档定义 WishinDiary 中用户健康数据的**导出、删除、保留期限**与**备份恢复**
策略，涵盖健康数据的导出、删除、保留期限和备份恢复。

## 1. 数据范围

每个用户可能产生的数据包括：

| 表 | 内容 |
| --- | --- |
| `users` | 用户名、密码哈希、注册时间 |
| `cycles` | 经期周期（开始/结束日期、周期长度、流血天数） |
| `daily_logs` | 每日健康日志（情绪、痛经、运动、饮食、日记正文） |
| `prediction_logs` | AI 预测记录及实际对账误差 |

以上数据均通过外键 `user_id` 关联，`ON DELETE CASCADE` 兜底级联。

## 2. 数据导出（可携带权）

接口：`GET /api/v1/user/export`

- 认证：需要登录（HttpOnly Cookie）。
- 返回：JSON，包含 `user`、`cycles`、`daily_logs`、`prediction_logs` 全部数据，
  以及导出时间 `exported_at`。
- 用途：用户个人备份、迁移到其他服务、留存证据。
- 行为审计：每次导出都会写入审计日志 `user.export`。

示例：

```bash
curl -b cookies.txt http://127.0.0.1:8000/api/v1/user/export > my-data.json
```

## 3. 用户数据删除（被遗忘权）

接口：`DELETE /api/v1/user/me`

- 认证：需要登录（HttpOnly Cookie）。
- 行为：在**单个事务**内按依赖顺序显式删除
  `prediction_logs` → `daily_logs` → `cycles` → `users`，
  并依靠外键 `ON DELETE CASCADE` 兜底，保证不残留孤儿数据。
- 不可恢复：删除是物理删除，执行前请提示用户确认。
- 行为审计：写入审计日志 `user.delete`。

## 4. 保留期限配置

环境变量 `DATA_RETENTION_DAYS`（`app/core/config.py`）：

- `0`（默认）：无限期保留，不自动清理。
- `N > 0`：仅保留最近 N 天的数据，更早的
  `cycles` / `daily_logs` / `prediction_logs` 可由脚本清理。

清理脚本：`wishindiary-api/scripts/cleanup_expired_data.py`

```bash
# 预览将删除的行数（不修改数据）
python scripts/cleanup_expired_data.py
# 真正删除并输出摘要
python scripts/cleanup_expired_data.py --apply
# 覆盖 DATA_RETENTION_DAYS 运行
python scripts/cleanup_expired_data.py --days 365 --apply
```

建议用系统定时任务定期执行：

- Linux crontab（每天凌晨 3 点）：

  ```cron
  0 3 * * * cd /opt/wishindiary/wishindiary-api && .venv/bin/python scripts/cleanup_expired_data.py --apply
  ```

- Windows 计划任务：在「任务计划程序」中创建每日任务，
  程序为 `.venv\Scripts\python.exe`，参数为
  `scripts\cleanup_expired_data.py --apply`，起始位置为 `wishindiary-api`。

## 5. 备份与恢复

脚本（支持 Docker Compose 与本地 MySQL）：

- `wishindiary-api/scripts/backup_database.sh`
- `wishindiary-api/scripts/restore_database.sh`

备份内容为完整逻辑备份（`mysqldump --single-transaction --routines --triggers`），
gzip 压缩后输出到 `./backups/wishindiary-<时间戳>.sql.gz`。

```bash
# Docker Compose 环境
./wishindiary-api/scripts/backup_database.sh
# 恢复
./wishindiary-api/scripts/restore_database.sh ./backups/wishindiary-20260901-120000.sql.gz

# 本地 MySQL 环境
BACKEND_MODE=local DB_HOST=127.0.0.1 DB_PORT=3306 \
DB_USER=wishin_app DB_PASSWORD=<你的数据库密码> DB_NAME=wishindiary_db \
./wishindiary-api/scripts/backup_database.sh
```

### 备份安全要求

- 备份文件包含敏感健康数据，**禁止提交 Git**，建议写入独立加密存储
  （如加密磁盘、对象存储私有桶 + 服务端加密）。
- 文件权限使用 `umask 077` 收紧（脚本已内置）。
- 恢复会覆盖目标库，必须先停止 API 写入并确认目标实例。
- 定期做**恢复演练**（备份的价值在于能恢复，而非能生成备份）。

### 迁移与回滚（Alembic）

数据库结构由 Alembic 管理（`wishindiary-api/migrations/`）：

```bash
cd wishindiary-api
alembic upgrade head      # 升级到最新
alembic downgrade <版本号> # 回滚到指定版本
alembic history           # 查看版本线
```

Docker 部署时后端容器启动前会自动执行 `alembic upgrade head`。

## 6. 推荐的最佳实践

1. 生产环境设置 `DATA_RETENTION_DAYS` 并配置每日清理定时任务。
2. 每日自动备份 + 每周复制到异地/对象存储 + 每月恢复演练。
3. 删除用户前先提示用户导出数据。
4. 保持 `alembic_version` 与代码一致：升级前备份，回滚后立即做数据校验。
