"""
训练脚本 — 从 MySQL 拉取数据、提取特征、训练随机森林模型并保存。
用法: python scripts/train.py  (从 wishindiary-api 目录运行)
"""
import sys
import hashlib
import argparse
from pathlib import Path

# 把项目根目录加入 path，让 import 正确找到 app.*
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
from sklearn.model_selection import GroupShuffleSplit
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error
import skops.io as sio

from app.features import build_cycle_feature_matrix, load_cycle_training_data
from app.core.config import settings
from app.ml.contract import FEATURE_NAMES
from scripts.generate_clean_training_data import build_synthetic_training_data

# 真实数据不足时，用干净合成数据兜底的最低样本量
MIN_REAL_SAMPLES = 60


def train_and_evaluate(synthetic_only: bool = False):
    print("⏳ 正在从数据库加载数据并提取特征...")
    if synthetic_only:
        print("ℹ️ 使用纯合成数据训练，不读取真实用户数据库")
        raw_cycles, raw_logs = build_synthetic_training_data()
    else:
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
    real_n = 0 if X_real is None else len(X_real)
    if real_n < MIN_REAL_SAMPLES:
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
        print("❌ 错误：特征矩阵为空，请确保数据库中有足够的数据！")
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train the cycle prediction model")
    parser.add_argument(
        "--synthetic-only",
        action="store_true",
        help="Train without connecting to the user database",
    )
    train_and_evaluate(synthetic_only=parser.parse_args().synthetic_only)
