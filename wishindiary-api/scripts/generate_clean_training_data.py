"""
干净训练数据生成器 — 生成医学上健康的模拟周期数据，用于离线训练。

与旧的 generate_data.py 不同：
- 不写入数据库（不污染用户的真实周期表）
- 只生成 DataFrame，供 train.py 在真实数据不足时兜底训练
- 周期长度: 正态分布 28 ± 3 天（clip 到 21~35）
- 出血天数: 正态分布 5 ± 1.5 天（clip 到 3~7）
- 生成足够多的周期，让滑动窗口特征矩阵能形成稳定样本

用法: 由 train.py 内部调用，或独立调试用。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import random
import numpy as np
import pandas as pd
from datetime import date, timedelta

random.seed(42)
np.random.seed(42)


def generate_synthetic_cycles(n_users: int = 30, n_cycles_each: int = 10) -> pd.DataFrame:
    """生成 n_users 个用户、每个 n_cycles_each 个周期的健康周期数据。

    每个用户的周期长度围绕各自的"个人均值"波动（模拟真实个体差异），
    平均长度在 25~33 天之间随机分布。
    """
    rows = []
    for user_offset in range(n_users):
        user_id = 10_000 + user_offset  # 用一个远离真实 user_id 的段，避免混淆
        personal_mean = random.uniform(25, 33)  # 每个用户有自己的平均周期
        personal_bleeding = random.uniform(3.5, 6.5)

        # 起始日期：错开，避免所有用户同一天
        start = date(2024, 1, 1) + timedelta(days=random.randint(0, 20))

        for _ in range(n_cycles_each):
            cycle_length = int(round(random.gauss(personal_mean, 2)))
            cycle_length = max(21, min(35, cycle_length))

            bleeding_days = int(round(random.gauss(personal_bleeding, 1)))
            bleeding_days = max(3, min(7, bleeding_days))

            # 周期之间留 1 天空隙，模拟"结束次日开始下一周期"的语义
            end = start + timedelta(days=cycle_length - 1)
            next_start = end + timedelta(days=1)

            rows.append({
                "user_id": user_id,
                "start_date": start,
                "cycle_length": cycle_length,
                "bleeding_days": bleeding_days,
            })

            start = next_start

    df = pd.DataFrame(rows)
    return df


def build_synthetic_training_data(min_cycles_per_user: int = 4) -> tuple[pd.DataFrame, pd.DataFrame]:
    """生成用于训练的合成周期数据 + 空的日志表。

    min_cycles_per_user: 每个用户至少需要的周期数（保证滑动窗口可用）。
    """
    df_cycles = generate_synthetic_cycles()
    # 只保留有足够周期形成特征窗口的用户
    counts = df_cycles.groupby("user_id")["cycle_length"].transform("count")
    df_cycles = df_cycles[counts >= min_cycles_per_user].reset_index(drop=True)

    # 日志表为空即可（训练特征只依赖 cycles，日志是给未来版本用的）
    df_logs = pd.DataFrame(columns=[
        "user_id", "log_date", "mood_level", "cramps_severity",
        "is_exercise", "exercise_minutes",
    ])

    return df_cycles, df_logs


if __name__ == "__main__":
    df, _ = build_synthetic_training_data()
    print(f"生成合成训练数据: {len(df)} 条周期")
    print("cycle_length 分布:")
    print(df["cycle_length"].describe())
    print("\nbleeding_days 分布:")
    print(df["bleeding_days"].describe())
