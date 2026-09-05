# WishinDiary 数据库备份与恢复演练（DR）

> 覆盖自动化数据库备份与定期恢复演练。
> 备份脚本 `wishindiary-api/scripts/backup_database.sh`、恢复脚本
> `wishindiary-api/scripts/restore_database.sh` 已存在；本文说明如何
> 自动化、如何做恢复演练，以及灾难恢复（DR）预案。

## 1. 备份内容与策略

- 备份物：MySQL 全库（`mysqldump --single-transaction --routines --triggers`），
  输出为 gzip 压缩的 `.sql.gz`，默认落盘 `wishindiary-api/backups/`。
- 覆盖范围：周期记录、每日健康日志、预测记录、用户账号等**全部**业务数据。
- 敏感说明：备份含健康数据，**禁止提交 Git**，建议使用加密存储（见 §4）。
- 备份脚本支持两种模式：
  - `BACKEND_MODE=docker`（默认）：`docker compose exec db mysqldump`；
  - `BACKEND_MODE=local`：直接连本地 MySQL（`DB_HOST/DB_PORT/DB_USER/DB_PASSWORD/DB_NAME`）。

```bash
# 手动备份（Compose 环境）
./wishindiary-api/scripts/backup_database.sh
# 手动备份（本地 MySQL 环境）
BACKEND_MODE=local DB_HOST=127.0.0.1 DB_PORT=3306 DB_USER=wishin_app DB_PASSWORD=<你的数据库密码> DB_NAME=wishindiary_db \
  ./wishindiary-api/scripts/backup_database.sh
```

## 2. 自动化备份

### 方案 A：Linux cron（推荐单机）

```bash
./wishindiary-api/scripts/install_backup_cron.sh          # 安装（每日 02:30）
./wishindiary-api/scripts/install_backup_cron.sh --preview  # 仅预览不修改
```

脚本会向当前用户 crontab 追加：

```
30 2 * * * cd /path/to/WishinDiary/wishindiary-api && ./scripts/backup_database.sh 2>>backups/backup.log
```

验证：`crontab -l`；次日检查 `backups/` 下是否出现新 `.sql.gz`，`backups/backup.log`
无报错。可选：追加清理 30 天前备份的 cron 行（脚本预览中有注释示例）。

### 方案 B：docker-compose 定时容器（无宿主 cron 环境）

可增加一个一次性 `backup` 服务（示例片段）：

```yaml
  backup:
    image: alpine:3.20.3
    entrypoint: ["/bin/sh", "-c"]
    command:
      - |
        apk add --no-cache mysql-client >/dev/null
        while true; do
          ts=$$(date +%Y%m%d-%H%M%S)
          mysqldump -h db -u root -p"$$MYSQL_ROOT_PASSWORD" --single-transaction --routines --triggers "$$MYSQL_DATABASE" \
            | gzip > /backups/wishindiary-$$ts.sql.gz
          sleep 86400
        done
    volumes:
      - ./backups:/backups      # 挂宿主机目录可写挂载，容器将备份写入该目录持久化
    depends_on:
      - db
```

> 说明：项目根已提供 `scripts/backup_database.sh`，Linux 环境优先用方案 A；
> 方案 B 适合 Windows / 无 cron 场景，也可改用云计划任务（Windows Task Scheduler /
> 云厂商定时函数）调用 backup_database.sh。

### 方案 C：云托管数据库（可选增强）

使用托管 MySQL（RDS/Cloud SQL）时启用其自动快照 + 加密 + 跨可用区备份，
本地备份脚本仅作兜底。生产环境建议使用托管数据库，并利用其高可用与加密备份能力。

## 3. 恢复演练（定期验证备份可用性）

恢复会**覆盖目标库同名表/记录**，演练请使用**独立的演练库/实例**，避免污染生产。

### 3.1 演练步骤（每月至少一次，建议月初）

1. **准备演练环境**：克隆或临时搭建 MySQL 实例（可用容器）：

```bash
docker run --rm -d --name wishindiary-dr \
  -e MYSQL_ROOT_PASSWORD=dr_pass -e MYSQL_DATABASE=wishindiary_db \
  -p 3307:3306 mysql:8.0.46
```

2. **执行恢复**（本地模式指向演练实例）：

```bash
BACKEND_MODE=local DB_HOST=127.0.0.1 DB_PORT=3307 DB_USER=root DB_PASSWORD=dr_pass DB_NAME=wishindiary_db \
  ./wishindiary-api/scripts/restore_database.sh ./backups/wishindiary-<时间戳>.sql.gz
```

3. **校验数据完整性**：对比生产与演练库的行数/最新记录，例如：

```bash
mysql -h127.0.0.1 -P3307 -uroot -pdr_pass wishindiary_db -e \
  "SELECT COUNT(*) AS users FROM users; SELECT COUNT(*) AS cycles FROM cycles;"
```

同时确认关键表（users / cycles / daily_logs / prediction_logs）非空且数值合理。
4. **结构一致性**：在演练库运行 `alembic upgrade head` 后再次健康检查；
   若备份早于当前迁移版本，演练日志需记录"需要回滚/升级迁移"这一步骤。
5. **记录演练结果**：填写演练记录表（见 §3.2），关闭演练容器。

### 3.2 演练记录表模板

| 项 | 内容 |
| --- | --- |
| 演练日期 | YYYY-MM-DD |
| 使用备份文件 | backups/wishindiary-YYYYMMDD-HHMMSS.sql.gz |
| 备份生成时间 | YYYY-MM-DD HH:MM |
| 恢复耗时 | xx 分钟 |
| 数据校验结果 | 通过 / 失败（差异明细） |
| 迁移版本处理 | 无需 / 已 upgrade 到目标版本 |
| 负责人 | 姓名 |
| 结论 | 演练成功 / 需改进（问题清单） |

建议把演练记录放入 `docs/dr-exercises/`（模板：`docs/dr-exercises/2026-09-01.md`）。

## 4. 灾难恢复（DR）预案

### 4.1 目标（RPO / RTO）

- **RPO（最大可容忍数据丢失）**：1 天（每日备份粒度）；关键期可缩短备份间隔。
- **RTO（最大可容忍停机）**：2 小时内恢复服务（含环境重建 + 恢复演练熟练度）。

### 4.2 恢复流程（生产故障时）

```bash
# 1) 停止 API 写入，避免恢复期间数据错乱
docker compose stop backend

# 2) 用最近可用备份恢复（先确认目标实例无生产流量）
./wishindiary-api/scripts/restore_database.sh ./backups/wishindiary-<最近时间戳>.sql.gz

# 3) 迁移结构到当前代码版本
cd wishindiary-api && .venv/bin/python -m alembic upgrade head

# 4) 启动服务并做健康检查
docker compose start backend
curl --fail http://127.0.0.1:8000/api/health

# 5) 抽检关键数据与登录，确认业务可用
```

### 4.3 备份存储与安全

- 备份含敏感健康数据，必须：目录权限 `700/600`、避免公网共享、建议异地/对象存储
  加密归档到异地/对象存储（可选实施）。
- 生产配置 `DATA_RETENTION_DAYS` 决定库内数据保留；备份保留策略建议
  **至少 30 天**（按合规需要调整），并启用"保留最近 N 份 + 每月一份归档"。
- 演练与正式恢复均应在**独立实例**上先验证，再对生产执行。

## 5. 关联文档

- 部署：docs/DEPLOYMENT.md（含手动备份/恢复命令）
- 可观测性：docs/OBSERVABILITY.md
- 数据生命周期/合规：docs/DATA_LIFECYCLE.md
- 发布前检查：docs/RELEASE_CHECKLIST.md
