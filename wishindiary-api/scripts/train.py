"""
训练脚本 — 从 MySQL 拉取数据、提取特征、训练随机森林模型并保存。
同时生成可发布到 Release 的模型评估报告与训练元数据清单。
用法: python scripts/train.py  (从 wishindiary-api 目录运行)
"""
import sys
import json
import hashlib
import argparse
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# 把项目根目录加入 path，让 import 正确找到 app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
import skops.io as sio

from app.features import build_cycle_feature_matrix, load_cycle_training_data
from app.features.cycle_feature_engineering import (
    MAX_BLEEDING_DAYS,
    MAX_CYCLE_LENGTH,
    MIN_BLEEDING_DAYS,
    MIN_CYCLE_LENGTH,
)
from app.core.config import settings
from app.ml.contract import FEATURE_NAMES, MODEL_VERSION
from app.ml.validation import (
    build_group_kfold_splits,
    build_temporal_holdout_split,
    evaluate_regression_metrics,
)
from scripts.generate_clean_training_data import build_synthetic_training_data

# 真实数据不足时，用干净合成数据兜底的最低样本量
MIN_REAL_SAMPLES = 60
# 按用户分组交叉验证折数（当用户数足够时）
KFOLD_SPLITS = 5


def _collect_env_metadata() -> dict:
    """采集训练环境元数据：代码版本、依赖版本、平台信息。"""
    git_commit = ""
    try:
        git_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
    except Exception:
        git_commit = "unknown"
    try:
        import sklearn
        import numpy
        import pymysql

        dep_versions = {
            "python": platform.python_version(),
            "scikit-learn": sklearn.__version__,
            "numpy": numpy.__version__,
            "pandas": pd.__version__,
            "pymysql": pymysql.__version__,
            "skops": sio.__version__,
        }
    except Exception:
        dep_versions = {}
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": git_commit,
        "platform": platform.platform(),
        "dependencies": dep_versions,
        "model_version": MODEL_VERSION,
        "feature_contract": {"feature_names": list(FEATURE_NAMES), "n_features": len(FEATURE_NAMES)},
        "environment": settings.ENVIRONMENT,
    }


def _save_report(report: dict, model_filename: Path) -> tuple[Path, Path]:
    """把评估报告与元数据落盘为 JSON + Markdown，与模型放在同一目录。"""
    report_dir = model_filename.parent
    report_dir.mkdir(parents=True, exist_ok=True)

    json_path = report_dir / "model_evaluation_report.json"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    lines = [
        "# WishinDiary 模型评估报告",
        "",
        f"- **模型版本**: `{report['metadata'].get('model_version', 'unknown')}`",
        f"- **生成时间**: {report['metadata'].get('generated_at', 'unknown')}",
        f"- **Git Commit**: `{report['metadata'].get('git_commit', 'unknown')}`",
        f"- **样本量**: {report.get('dataset', {}).get('total_samples', 0)}",
        f"- **MODEL_SHA256**: `{report.get('model_sha256', '')}`",
        "",
        "## 1. 数据集构成",
    ]
    for key, value in report.get("dataset", {}).items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    lines.append("## 2. 留出集评估（holdout）")
    for key, value in report.get("holdout", {}).items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    lines.append("## 3. 按用户分组交叉验证（GroupKFold）")
    gk = report.get("group_kfold", {})
    lines.append(f"- **折数**: {gk.get('n_splits', 0)}")
    for key in ("mae", "rmse", "hit_rate_within_2d", "hit_rate_within_3d", "baseline_mean3_mae", "baseline_mean3_hit3"):
        if key in gk:
            label = {
                "hit_rate_within_2d": "±2 天内命中率(%)",
                "hit_rate_within_3d": "±3 天内命中率(%)",
                "baseline_mean3_mae": "基线(最近3周期均值) MAE",
                "baseline_mean3_hit3": "基线(最近3周期均值) ±3天命中率(%)",
            }.get(key, key)
            lines.append(f"- **{label}**: {gk[key]}")
    lines.append("")
    lines.append("## 3.1 与合成模型对比")
    synth_ref = report.get("synthetic_reference") or {}
    if synth_ref:
        lines.append(f"- **旧数据源**: {synth_ref.get('source', 'unknown')}（样本量 {synth_ref.get('total_samples', 'n/a')}）")
        lines.append(f"- **旧 GroupKFold MAE**: {synth_ref.get('group_kfold_mae', 'n/a')}")
        lines.append(f"- **旧 GroupKFold RMSE**: {synth_ref.get('group_kfold_rmse', 'n/a')}")
    else:
        lines.append("- 未读取到旧报告，跳过对比。")
    lines.append("")
    lines.append("## 4. 时间切分验证（temporal holdout）")
    for key, value in report.get("temporal_holdout", {}).items():
        lines.append(f"- **{key}**: {value}")
    lines.append("")
    lines.append("## 5. 特征重要性")
    for name, value in report.get("feature_importance", {}).items():
        lines.append(f"- **{name}**: {value:.4f}")
    lines.append("")
    lines.append("## 6. 免责声明")
    lines.append(report.get("disclaimer", ""))
    lines.append("")

    md_path = report_dir / "model_evaluation_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path


def load_fedcycle_csv(csv_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """读取 Fehring 2012 Marquette NFP 周期级宽表，转化为训练用纵向周期 DataFrame。

    字段映射：
      - ClientID        -> user_id
      - LengthofCycle   -> cycle_length（目标变量；绝不允许进特征，只在 build 阶段作为 target）
      - LengthofMenses  -> bleeding_days（缺失为 NaN，由 build 内 fillna(5) 统一处理）
      - start_date      -> 合成日历日期：按用户内周期序号用前一周期长度累加得到，
                           保留周期间的时序与跨月季节性（用于 start_month_sin/cos）。

    数据坑处理（与数据库数据口径保持一致）：
      - (ClientID, CycleNumber) 重复行：优先保留"非空字段最多"的行，其次取首行；
      - 空字符串 ' ' 一律经 pd.to_numeric(errors='coerce') 转 NaN；
      - Age 等 >90% 空列的近空列直接剔除，不参与特征；
      - 医学范围清洗：cycle_length 15~45、bleeding_days 1~15（同 MIN/MAX 常量）。
    """
    df = pd.read_csv(csv_path, encoding="utf-8-sig")
    n_raw = len(df)

    df = df.sort_values(["ClientID", "CycleNumber"]).reset_index(drop=True)

    # 1) 空格字符串 -> NaN（ClientID 仅去空格前后，不做数值化）
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = (
                df[col].astype(str).str.strip()
                if col == "ClientID"
                else pd.to_numeric(df[col], errors="coerce")
            )

    # 2) 去重：优先保留非空字段数最多的行，其次取首行
    dup_before = int(df.duplicated(["ClientID", "CycleNumber"]).sum())
    df["_n_nonnull"] = df.notna().sum(axis=1)
    df = (
        df.sort_values("_n_nonnull", ascending=False)
        .drop_duplicates(["ClientID", "CycleNumber"], keep="first")
        .sort_values(["ClientID", "CycleNumber"])
        .drop(columns="_n_nonnull")
        .reset_index(drop=True)
    )
    dropped_total = n_raw - len(df)

    # 3) 剔除近空列（>90% 缺失），如 Age / BMI 等在 Fehring 表中几乎全空
    na_ratio = df.isna().mean()
    near_empty = [c for c in na_ratio.index if na_ratio[c] > 0.9 and c != "ClientID"]
    df = df.drop(columns=near_empty)

    # 4) 映射为训练纵向周期表。
    #    注意：build 的 _normalize_cycle_frame 只接受数值 user_id，
    #    Fehring 的 ClientID 是非数字字符串（如 "nfp8020"），直接传入会被
    #    pd.to_numeric(errors='coerce') 变成 NaN 导致整行被 drop。
    #    因此先把 ClientID factorize 编码为数值型 user_id（保持同一用户编码一致）。
    user_codes, _ = pd.factorize(df["ClientID"].astype(str))
    cycles = pd.DataFrame(
        {
            "user_id": user_codes + 1,
            "cycle_length": pd.to_numeric(df["LengthofCycle"], errors="coerce"),
            "bleeding_days": (
                pd.to_numeric(df["LengthofMenses"], errors="coerce")
                if "LengthofMenses" in df
                else np.nan
            ),
        }
    )

    # 5) 合成 start_date：用户内按前一周期长度累加，保留时序与跨月季节性
    start_dates = []
    base = pd.Timestamp("2020-01-01")
    for _, g in cycles.groupby("user_id", sort=True):
        lengths = g["cycle_length"].to_numpy(dtype=float)
        cur = base
        for idx, length in enumerate(lengths):
            if idx > 0:
                step = 28 if np.isnan(lengths[idx - 1]) else int(round(lengths[idx - 1]))
                cur = cur + pd.Timedelta(days=step)
            start_dates.append(cur)
    cycles["start_date"] = pd.to_datetime(start_dates)

    # 6) 医学范围清洗（与数据库数据源口径一致，保持训练口径统一）
    healthy_mask = (
        cycles["cycle_length"].between(MIN_CYCLE_LENGTH, MAX_CYCLE_LENGTH)
        & (
            cycles["bleeding_days"].isna()
            | cycles["bleeding_days"].between(MIN_BLEEDING_DAYS, MAX_BLEEDING_DAYS)
        )
    )
    cycles = cycles[healthy_mask].reset_index(drop=True)

    print(
        f"[Fehring CSV] 原始行 {n_raw} -> 去重剔除 {dropped_total} 行(含重复 {dup_before}) "
        f"-> 医学清洗后 {len(cycles)} 行；用户数 {cycles['user_id'].nunique()}；"
        f"剔除近空列 {near_empty or '无'}"
    )
    return cycles, pd.DataFrame()


def train_and_evaluate(synthetic_only: bool = False, csv_path: str | None = None):
    if synthetic_only and csv_path:
        raise SystemExit("--synthetic-only 与 --csv 不能同时使用")

    print("⏳ 正在加载数据并提取特征...")
    if csv_path:
        print(f"ℹ️ 使用真实 Fehring CSV 数据训练: {csv_path}")
        raw_cycles, raw_logs = load_fedcycle_csv(csv_path)
    elif synthetic_only:
        print("ℹ️ 使用纯合成数据训练，不读取真实用户数据库")
        raw_cycles, raw_logs = build_synthetic_training_data()
    else:
        print("ℹ️ 从数据库加载数据训练")
        raw_cycles, raw_logs = load_cycle_training_data()
    X_real, y_real, meta_real = build_cycle_feature_matrix(raw_cycles, raw_logs)

    x_parts = []
    y_parts = []
    meta_parts = []
    if X_real is not None and not X_real.empty:
        x_parts.append(X_real)
        y_parts.append(y_real)
        meta_parts.append(meta_real)

    # 真实样本不足时，用干净合成数据补足（保证模型稳定且对编辑有响应）
    # —— CSV 真实数据模式除外：按用户要求纯真实数据训练，禁用合成兜底
    real_n = 0 if X_real is None else len(X_real)
    if real_n < MIN_REAL_SAMPLES:
        if csv_path:
            print(
                f"⚠️ 真实 CSV 样本仅 {real_n} 个（阈值 {MIN_REAL_SAMPLES}），"
                "CSV 模式禁用合成兜底，继续使用真实数据训练"
            )
        else:
            print(f"⚠️ 真实样本仅 {real_n} 个（阈值 {MIN_REAL_SAMPLES}），使用干净合成数据兜底训练...")
            synth_cycles, synth_logs = build_synthetic_training_data()
            X_synth, y_synth, meta_synth = build_cycle_feature_matrix(synth_cycles, synth_logs)
            x_parts.append(X_synth)
            y_parts.append(y_synth)
            meta_parts.append(meta_synth)

    X = pd.concat(x_parts, ignore_index=True) if x_parts else pd.DataFrame(columns=FEATURE_NAMES)
    y = pd.concat(y_parts, ignore_index=True) if y_parts else pd.Series(dtype=float)
    feature_matrix = pd.concat(meta_parts, ignore_index=True) if meta_parts else pd.DataFrame()

    if X is None or X.empty:
        print("❌ 错误：特征矩阵为空，请确保数据源中有足够的数据！")
        return

    print(f"✅ 成功加载特征数据：{len(X)} 个有效预测样本。")

    groups = feature_matrix["user_id"] if "user_id" in feature_matrix else None
    if groups is not None and groups.nunique() >= 2:
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
        train_idx, test_idx = next(splitter.split(X, y, groups=groups))
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        print("🧪 使用按用户分组的验证切分，避免同一用户的周期记录同时出现在训练集和测试集。")
    else:
        # 单用户数据也必须按时间切分，避免相邻周期泄漏到验证集。
        order = feature_matrix.sort_values("start_date").index.to_numpy()
        cut = max(1, int(len(order) * 0.8))
        train_idx, test_idx = order[:cut], order[cut:]
        if len(test_idx) == 0:
            test_idx = train_idx[-1:]
            train_idx = train_idx[:-1]
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
        print("⚠️ 用户数不足，使用按时间切分。")

    print("🧠 正在训练随机森林回归模型...")
    model = RandomForestRegressor(n_estimators=200, random_state=42, max_depth=8)
    model.fit(X_train, y_train)

    predictions = model.predict(X_test)

    mae = mean_absolute_error(y_test, predictions)
    rmse = root_mean_squared_error(y_test, predictions)

    print("\n" + "=" * 30)
    print("📊 模型评估结果：")
    print(f"平均绝对误差 (MAE): {mae:.2f} 天")
    print(f"均方根误差 (RMSE): {rmse:.2f} 天")
    print("=" * 30 + "\n")

    print("💡 特征重要性分析（影响预测的核心因素）：")
    feature_importances = pd.Series(model.feature_importances_, index=X.columns)
    print(feature_importances.sort_values(ascending=False))

    model_filename = Path(settings.model_abs_path)
    model_filename = model_filename.with_suffix(".skops")
    model_filename.parent.mkdir(parents=True, exist_ok=True)
    # 保存最终模型时，使用全部可用样本重新拟合，保证线上推理吃到完整知识面。
    final_model = RandomForestRegressor(n_estimators=200, random_state=42, max_depth=8)
    final_model.fit(X, y)
    sio.dump(final_model, model_filename)
    digest = hashlib.sha256(model_filename.read_bytes()).hexdigest()
    print(f"\n💾 模型已保存至：{model_filename}")
    print(f"MODEL_SHA256={digest}")

    # ---------- 生成评估报告与训练元数据 ----------
    metadata = _collect_env_metadata()
    if csv_path:
        data_source = "fedcycle_csv"
        data_notes = (
            "真实 Fehring 2012 Marquette NFP 数据集；按 ClientID 分组交叉验证，"
            "去重规则=非空字段最多优先、其次取首行；(ClientID,CycleNumber) 重复行已剔除；"
            "空格字符串转 NaN；Age 等近空列剔除；LengthofCycle 仅作为目标变量，绝不进特征。"
        )
    elif synthetic_only:
        data_source = "synthetic"
        data_notes = "纯合成生成数据（结构同真实数据），用于流水线回归与离线无库环境。"
    else:
        data_source = "mysql"
        data_notes = "读取生产 MySQL 的 users cycles 历史数据。"
    report = {
        "metadata": metadata,
        "dataset": {
            "source": data_source,
            "note": data_notes,
            "total_samples": int(len(X)),
            "real_samples": int(real_n),
            "synthetic_samples": int(len(X) - real_n),
            "n_users": int(groups.nunique()) if groups is not None else 1,
        },
        "holdout": {
            "test_samples": int(len(y_test)),
            "mae": round(float(mae), 4),
            "rmse": round(float(rmse), 4),
            "hit_rate_within_2d": round(float(np.mean(np.abs(predictions - y_test) <= 2) * 100), 2),
            "hit_rate_within_3d": round(float(np.mean(np.abs(predictions - y_test) <= 3) * 100), 2),
        },
        "model_sha256": digest,
        "feature_importance": {
            name: round(float(v), 4) for name, v in feature_importances.sort_values(ascending=False).items()
        },
        "disclaimer": (
            "本模型输出仅供参考，不能用于诊断、治疗、避孕或紧急医疗判断。"
            "实际周期受个体差异、压力、作息等多种因素影响。"
        ),
    }

    # 按用户分组交叉验证（需要至少 2 个不同用户）
    if groups is not None and groups.nunique() >= 2:
        try:
            gk_metrics = []
            all_y, all_pred, all_te = [], [], []
            for tr_idx, te_idx in build_group_kfold_splits(X, groups, n_splits=KFOLD_SPLITS):
                _model = RandomForestRegressor(n_estimators=100, random_state=42, max_depth=8)
                _model.fit(X.iloc[tr_idx], y.iloc[tr_idx])
                _pred = _model.predict(X.iloc[te_idx])
                gk_metrics.append(evaluate_regression_metrics(y.iloc[te_idx], _pred))
                all_y.append(y.iloc[te_idx].to_numpy())
                all_pred.append(_pred)
                all_te.append(te_idx)

            all_y = np.concatenate(all_y)
            all_pred = np.concatenate(all_pred)
            te_all = np.concatenate(all_te)
            err_abs = np.abs(all_pred - all_y)

            # 规则法基线：直接用"最近 3 个周期均值"(roll_3_mean) 预测，对比 RF 相对简单规则是否稳健
            baseline_pred = X["roll_3_mean"].to_numpy()[te_all]
            base_err_abs = np.abs(baseline_pred - all_y)

            report["group_kfold"] = {
                "n_splits": len(gk_metrics),
                "mae": round(float(sum(m["mae"] for m in gk_metrics) / len(gk_metrics)), 4),
                "rmse": round(float(sum(m["rmse"] for m in gk_metrics) / len(gk_metrics)), 4),
                "hit_rate_within_2d": round(float(np.mean(err_abs <= 2) * 100), 2),
                "hit_rate_within_3d": round(float(np.mean(err_abs <= 3) * 100), 2),
                "baseline_mean3_mae": round(float(base_err_abs.mean()), 4),
                "baseline_mean3_hit3": round(float(np.mean(base_err_abs <= 3) * 100), 2),
            }
        except Exception as exc:
            print(f"⚠️ 交叉验证失败：{exc}")
            report["group_kfold"] = {"n_splits": 0, "error": str(exc)}

    # 时间切分验证（全部样本按 start_date 排序）
    try:
        tr_idx, te_idx = build_temporal_holdout_split(feature_matrix, test_fraction=0.2)
        if len(te_idx) > 0:
            _model = RandomForestRegressor(n_estimators=100, random_state=42, max_depth=8)
            _model.fit(X.iloc[tr_idx], y.iloc[tr_idx])
            _pred = _model.predict(X.iloc[te_idx])
            report["temporal_holdout"] = {
                "test_samples": int(len(te_idx)),
                "mae": round(float(mean_absolute_error(y.iloc[te_idx], _pred)), 4),
                "rmse": round(float(root_mean_squared_error(y.iloc[te_idx], _pred)), 4),
            }
    except Exception as exc:
        print(f"⚠️ 时间切分验证失败：{exc}")
        report["temporal_holdout"] = {"error": str(exc)}

    # 与旧模型（合成模型）评估对比：在报告被本次覆盖前读取旧 JSON 指标
    try:
        old_json = model_filename.parent / "model_evaluation_report.json"
        if old_json.exists():
            old_report = json.loads(old_json.read_text(encoding="utf-8"))
            old_ds = old_report.get("dataset", {})
            old_gk = old_report.get("group_kfold", {})
            report["synthetic_reference"] = {
                "source": old_ds.get("source", "unknown") or "unknown",
                "total_samples": old_ds.get("total_samples"),
                "group_kfold_mae": old_gk.get("mae"),
                "group_kfold_rmse": old_gk.get("rmse"),
            }
    except Exception as exc:
        print(f"⚠️ 旧报告对比信息读取失败：{exc}")

    json_path, md_path = _save_report(report, model_filename)
    print("\n📋 模型评估报告已生成：")
    print(f"   JSON: {json_path}")
    print(f"   MD  : {md_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the cycle prediction model")
    parser.add_argument(
        "--synthetic-only",
        action="store_true",
        help="Train without connecting to the user database",
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=None,
        help="Train from a local Fehring-style cycle CSV (ClientID/CycleNumber/LengthofCycle/...). "
        "Mutually exclusive with --synthetic-only.",
    )
    args = parser.parse_args()
    train_and_evaluate(synthetic_only=args.synthetic_only, csv_path=args.csv)
