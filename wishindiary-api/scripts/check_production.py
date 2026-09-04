#!/usr/bin/env python3
"""生产部署前检查脚本（Pre-deployment check）。

在 docker compose up 或发布前运行，校验关键环境变量与部署前置条件，
发现 FAIL 项时以非零退出码快速失败，防止带病上线。

用法（在 wishindiary-api 目录下）：
    python scripts/check_production.py
    # 指定环境文件（默认自动读取项目根 .env）
    python scripts/check_production.py --env .env.production

判定级别：
    PASS   满足要求
    FAIL   必须修复，否则退出码非 0
    WARN   建议关注，不阻塞发布
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEAK_PASSWORDS = {"", "123456", "root", "password", "mysql"}


def load_env(env_file: Path | None) -> dict[str, str]:
    """合并 os.environ 与 .env 文件（.env 优先级低，仅填充缺失项）。"""
    data = dict(os.environ)
    if env_file and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key and key not in data:
                data[key] = value
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="WishinDiary 生产部署前检查")
    parser.add_argument(
        "--env",
        default=str(PROJECT_ROOT / ".env"),
        help="环境文件路径（默认项目根 .env）",
    )
    args = parser.parse_args()

    env = load_env(Path(args.env))
    results: list[tuple[str, str, str]] = []

    def check(level: str, item: str, message: str) -> None:
        results.append((level, item, message))

    # ---- 运行环境 ----
    env_name = env.get("ENVIRONMENT", "development")
    check(
        "WARN" if env_name != "production" else "PASS",
        "ENVIRONMENT",
        f"当前值={env_name}（生产部署请设为 production）",
    )

    # ---- 密钥与密码 ----
    secret = env.get("SECRET_KEY", "")
    if len(secret) >= 32 and secret not in {""}:
        check("PASS", "SECRET_KEY", f"长度 {len(secret)} 字符（>=32）")
    elif env_name == "production":
        check("FAIL", "SECRET_KEY", "生产环境 SECRET_KEY 必须 >= 32 字符且随机")
    else:
        check("WARN", "SECRET_KEY", "未设置或过短，仅限本地开发使用")

    db_pass = env.get("DB_PASSWORD", "")
    if env_name == "production" and db_pass in WEAK_PASSWORDS:
        check("FAIL", "DB_PASSWORD", "生产环境数据库密码过弱或为空")
    elif db_pass:
        check("PASS", "DB_PASSWORD", "已设置数据库密码")
    else:
        check("WARN", "DB_PASSWORD", "数据库密码为空，仅限本地开发")

    # ---- 数据库 ----
    db_host = env.get("DB_HOST", "127.0.0.1")
    if db_host in {"127.0.0.1", "localhost"} and env_name == "production":
        check("WARN", "DB_HOST", "生产环境数据库建议与 API 分离（非 127.0.0.1）")
    else:
        check("PASS", "DB_HOST", f"DB_HOST={db_host}")

    # ---- 可观测性 ----
    log_format = env.get("LOG_FORMAT", "json")
    check(
        "PASS" if log_format in {"json", "text"} else "FAIL",
        "LOG_FORMAT",
        f"当前值={log_format}（生产推荐 json 结构化日志）",
    )
    log_level = env.get("LOG_LEVEL", "INFO").upper()
    if log_level in {"DEBUG", "INFO", "WARNING", "WARN", "ERROR", "CRITICAL"}:
        check("PASS", "LOG_LEVEL", f"LOG_LEVEL={log_level}")
    else:
        check("FAIL", "LOG_LEVEL", f"非法日志级别：{log_level}")

    if env.get("METRICS_ENABLED", "").lower() == "true":
        check("PASS", "METRICS_ENABLED", "已启用 /metrics 指标端点")
    else:
        check(
            "WARN",
            "METRICS_ENABLED",
            "未启用 /metrics（仍会输出结构化日志指标，可按需开启）",
        )

    if env.get("SENTRY_DSN"):
        check("PASS", "SENTRY_DSN", "已配置 Sentry 上报（生产建议开启）")
    else:
        check(
            "WARN",
            "SENTRY_DSN",
            "未配置 SENTRY_DSN，错误不上报 Sentry（可接受，但建议生产开启）",
        )

    # ---- 模型文件与哈希 ----
    model_path = Path(env.get("MODEL_PATH", str(PROJECT_ROOT / "ml" / "menstrual_rf_model.skops")))
    if model_path.exists():
        check("PASS", "MODEL_PATH", f"模型文件存在：{model_path}")
        sha = env.get("MODEL_SHA256", "")
        if sha:
            actual = hashlib.sha256(model_path.read_bytes()).hexdigest()
            if actual.lower() == sha.lower():
                check("PASS", "MODEL_SHA256", "模型哈希与配置一致")
            else:
                check("FAIL", "MODEL_SHA256", f"哈希不一致：配置={sha}，实际={actual}")
        else:
            check("FAIL", "MODEL_SHA256", "生产环境必须配置 MODEL_SHA256 并保证与模型一致")
    else:
        check("FAIL", "MODEL_PATH", f"模型文件缺失：{model_path}")

    # ---- 数据保留与 CORS ----
    retention = env.get("DATA_RETENTION_DAYS", "0")
    try:
        retention_ok = int(retention) >= 0
    except ValueError:
        retention_ok = False
    check(
        "PASS" if retention_ok else "FAIL",
        "DATA_RETENTION_DAYS",
        f"当前值={retention}（0=无限期保留，>0=定期清理）",
    )

    cors = env.get("CORS_ORIGINS", "")
    check(
        "FAIL" if "*" in cors else "PASS",
        "CORS_ORIGINS",
        "CORS 含通配符 *，生产环境禁止" if "*" in cors else f"CORS={cors or '(默认)'}",
    )

    # ---- 汇总 ----
    print("\n========== WishinDiary 部署前检查报告 ==========")
    for level, item, message in results:
        print(f"  [{level:>4}] {item:<18} {message}")
    print("=================================================")

    fails = [r for r in results if r[0] == "FAIL"]
    warns = [r for r in results if r[0] == "WARN"]
    print(f"\n结果：PASS {len(results) - len(fails) - len(warns)} / "
          f"WARN {len(warns)} / FAIL {len(fails)}")
    if fails:
        print("存在 FAIL 项，请修复后再部署。")
        return 1
    print("全部必须项通过，可以部署。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
