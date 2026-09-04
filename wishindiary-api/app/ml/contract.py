"""Single source of truth for model feature ordering and versioning."""

# 注意：start_month 已被 sin/cos 循环编码替换为两个特征（P0-1），
# 旧 9 特征模型（含 start_month 整数）无法通过维度/顺序校验，需重训至 cycle-rf-v2。
FEATURE_NAMES = (
    "lag_1_length", "lag_2_length", "lag_3_length",
    "lag_1_bleeding", "lag_2_bleeding", "lag_3_bleeding",
    "roll_3_mean", "roll_3_std",
    "start_month_sin", "start_month_cos",
)
MODEL_VERSION = "cycle-rf-v2"
