"""Feature engineering helpers for cycle model training."""

import pandas as pd
import pymysql
from datetime import date, datetime

from app.core.config import settings

def _connect_db():
    return pymysql.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
        database=settings.DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=5,
        read_timeout=30,
        write_timeout=30,
    )


# 医学上合理的周期长度与经期天数范围（超出即视为脏数据，训练时过滤）
#   - 周期长度: 正常 21~35 天，临床可接受放宽到 15~45 天
#   - 出血天数: 正常 3~7 天，放宽到 1~15 天
#   这样训练时天然剔除 0 / 60+ 天这类异常标记或测试垃圾。
MIN_CYCLE_LENGTH = 15
MAX_CYCLE_LENGTH = 45
MIN_BLEEDING_DAYS = 1
MAX_BLEEDING_DAYS = 15


def _read_sql_dataframe(connection, query: str, params: tuple = ()) -> pd.DataFrame:
    """Read a MySQL query through the cursor without pandas' DBAPI warning.

    Pandas 2.x may infer MySQL integer columns as Arrow strings when reading a
    raw pooled DBAPI connection. Fetching rows first keeps the data contract
    explicit and makes the numeric/date coercion below deterministic.
    """
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        columns = [column[0] for column in cursor.description or ()]
    return pd.DataFrame(rows, columns=columns)


def _normalize_cycle_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize MySQL values before comparisons and feature calculations."""
    if frame.empty:
        return frame.copy()

    normalized = frame.copy()
    for column in ("cycle_id", "user_id", "cycle_length", "bleeding_days"):
        if column in normalized.columns:
            normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    if "start_date" in normalized.columns:
        normalized["start_date"] = pd.to_datetime(normalized["start_date"], errors="coerce")
    if "end_date" in normalized.columns:
        normalized["end_date"] = pd.to_datetime(normalized["end_date"], errors="coerce")
    return normalized


def _is_healthy_cycle(row):
    """判断一条周期记录是否是健康的、可用于训练的数据。"""
    cycle_length = row.get("cycle_length")
    bleeding_days = row.get("bleeding_days")

    if cycle_length is None or pd.isna(cycle_length):
        return False
    if not (MIN_CYCLE_LENGTH <= cycle_length <= MAX_CYCLE_LENGTH):
        return False

    # 出血天数为空可接受（部分记录缺失），但若有值则必须落在合理范围
    if bleeding_days is not None and not pd.isna(bleeding_days):
        if not (MIN_BLEEDING_DAYS <= bleeding_days <= MAX_BLEEDING_DAYS):
            return False

    return True


def load_cycle_training_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    """从数据库拉取原始周期数据并转化为 Pandas DataFrame（含医学范围清洗）。"""
    connection = _connect_db()
    try:
        cycles_query = """
            SELECT cycle_id, user_id, start_date, cycle_length, bleeding_days
            FROM cycles
            WHERE cycle_length IS NOT NULL
            ORDER BY user_id, start_date ASC
        """
        df_cycles = _read_sql_dataframe(connection, cycles_query)
        df_cycles = _normalize_cycle_frame(df_cycles)
        df_logs = pd.DataFrame()
    finally:
        connection.close()

    # 医学范围清洗：剔除 0 天 / 70 天这类异常标记或测试垃圾
    if not df_cycles.empty:
        healthy_mask = (
            df_cycles["cycle_length"].between(MIN_CYCLE_LENGTH, MAX_CYCLE_LENGTH)
            & (
                df_cycles["bleeding_days"].isna()
                | df_cycles["bleeding_days"].between(MIN_BLEEDING_DAYS, MAX_BLEEDING_DAYS)
            )
        )
        df_cycles = df_cycles[healthy_mask].reset_index(drop=True)

    return df_cycles, df_logs


def build_cycle_feature_matrix(
    df_cycles: pd.DataFrame,
    df_logs: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    核心特征工程函数。
    把纵向的周期序列，转化为带有"滑动窗口"特征的矩阵。
    """
    df_cycles = _normalize_cycle_frame(df_cycles)
    df_cycles = df_cycles.sort_values(by=["user_id", "start_date"]).reset_index(drop=True).copy()
    df_cycles["bleeding_days"] = df_cycles["bleeding_days"].fillna(5)

    # 目标变量 Y
    df_cycles["target_length"] = df_cycles["cycle_length"]

    # 历史周期长度滑动窗口 (Lag Features)
    for idx in range(1, 4):
        df_cycles[f"lag_{idx}_length"] = df_cycles.groupby("user_id")["cycle_length"].shift(idx)

    # 历史出血天数滑动窗口
    for idx in range(1, 4):
        df_cycles[f"lag_{idx}_bleeding"] = df_cycles.groupby("user_id")["bleeding_days"].shift(idx)

    # 过去 3 个周期的聚合特征 (均值和波动率)
    grouped = df_cycles.groupby("user_id", sort=False)
    df_cycles["roll_3_mean"] = grouped["cycle_length"].transform(
        lambda values: values.shift(1).rolling(3, min_periods=3).mean()
    )
    df_cycles["roll_3_std"] = grouped["cycle_length"].transform(
        lambda values: values.shift(1).rolling(3, min_periods=3).std()
    )

    # 时间特征
    df_cycles["start_date"] = pd.to_datetime(df_cycles["start_date"])
    df_cycles["start_month"] = df_cycles["start_date"].dt.month

    features = [
        "lag_1_length", "lag_2_length", "lag_3_length",
        "lag_1_bleeding", "lag_2_bleeding", "lag_3_bleeding",
        "roll_3_mean", "roll_3_std", "start_month",
    ]

    feature_matrix = df_cycles.dropna(subset=features + ["target_length"]).reset_index(drop=True)

    X = feature_matrix[features]
    y = feature_matrix["target_length"]

    return X, y, feature_matrix


def get_latest_features_for_user(user_id: int) -> tuple[dict[str, float | int], date]:
    """为 API 服务：提取某个用户最新的一次预测特征。

    设计要点：
    - 完整周期（cycle_length 非空）用于构造滑动窗口特征；
    - 预测基准日期取"用户最新标记的开始日期"（无论该周期是否已结束），
      避免最新一次标记被过滤掉导致预测日期不更新。
    """
    connection = _connect_db()

    try:
        # 完整周期：只读取形成窗口所需的周期数据
        cycles_query = """
            SELECT cycle_id, user_id, start_date, cycle_length, bleeding_days
            FROM cycles
            WHERE cycle_length IS NOT NULL AND user_id = %s
            ORDER BY start_date DESC
            LIMIT 50
        """
        df_cycles = _read_sql_dataframe(connection, cycles_query, params=(user_id,))
        df_cycles = _normalize_cycle_frame(df_cycles)
        latest_start_query = """
            SELECT start_date FROM cycles
            WHERE user_id = %s
            ORDER BY start_date DESC LIMIT 1
        """
        with connection.cursor() as cursor:
            cursor.execute(latest_start_query, (user_id,))
            latest_start_row = cursor.fetchone()
    finally:
        connection.close()

    df_logs = pd.DataFrame()

    if not df_cycles.empty:
        df_cycles = df_cycles.loc[
            df_cycles["cycle_length"].between(MIN_CYCLE_LENGTH, MAX_CYCLE_LENGTH)
            & (
                df_cycles["bleeding_days"].isna()
                | df_cycles["bleeding_days"].between(MIN_BLEEDING_DAYS, MAX_BLEEDING_DAYS)
            )
        ].sort_values("start_date").tail(4).reset_index(drop=True)

    if len(df_cycles) < 4:
        raise ValueError("数据不足：需要至少4个完整周期才能进行机器学习预测")

    _, _, full_matrix = build_cycle_feature_matrix(df_cycles, df_logs)

    # 滑动窗口特征需要至少 4 个周期才能形成 1 行有效样本
    # (rolling(3) + lag_3 导致前 3 行被 drop)
    if full_matrix.empty:
        raise ValueError("数据不足：需要至少4个完整周期才能形成有效的机器学习特征窗口")

    latest_row = full_matrix.iloc[-1]

    features = {
        "lag_1_length": float(latest_row["lag_1_length"]),
        "lag_2_length": float(latest_row["lag_2_length"]),
        "lag_3_length": float(latest_row["lag_3_length"]),
        "lag_1_bleeding": float(latest_row["lag_1_bleeding"]),
        "lag_2_bleeding": float(latest_row["lag_2_bleeding"]),
        "lag_3_bleeding": float(latest_row["lag_3_bleeding"]),
        "roll_3_mean": float(latest_row["roll_3_mean"]),
        "roll_3_std": float(latest_row["roll_3_std"]),
        "start_month": int(latest_row["start_month"]),
    }

    # 预测基准：优先用最新标记的开始日期
    if latest_start_row is not None:
        last_start_date = latest_start_row["start_date"]
    else:
        last_start_date = latest_row["start_date"]

    # Keep the public inference contract stable across MySQL drivers.
    if hasattr(last_start_date, "to_pydatetime"):
        last_start_date = last_start_date.to_pydatetime().date()
    elif isinstance(last_start_date, datetime):
        last_start_date = last_start_date.date()
    elif isinstance(last_start_date, str):
        last_start_date = pd.to_datetime(last_start_date, errors="raise").date()

    return features, last_start_date
