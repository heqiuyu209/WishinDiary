"""Single source of truth for model feature ordering and versioning."""

FEATURE_NAMES = (
    "lag_1_length", "lag_2_length", "lag_3_length",
    "lag_1_bleeding", "lag_2_bleeding", "lag_3_bleeding",
    "roll_3_mean", "roll_3_std", "start_month",
)
MODEL_VERSION = "cycle-rf-v1"
