"""P1：预测推理 service 单测（纯逻辑，不依赖真实模型文件）。

覆盖目标（对齐 pytest --cov 缺口的 cycle_prediction_service）：
- 无模型基线预测（回退到 roll_3_mean）
- 医学边界修正（21–45 天 guardrail）
- 生产环境模型缺失时拒绝基线预测
- last_start_date 支持 str / date 两种入参
- 非法特征输入返回 None（不抛 500）
- 有模型分支（假 estimator）：走 pandas 推理 + 置信区间

与 test_services.py 不同，本文件直接 patch CyclePredictionService._load_model，
聚焦 predict/置信区间逻辑本身。
"""

from datetime import date


from app.core.config import settings
from app.ml.contract import FEATURE_NAMES
from app.services.cycle_prediction_service import CyclePredictionService


def _features(**overrides) -> dict:
    feats = {name: 0.0 for name in FEATURE_NAMES}
    feats.update(overrides)
    return feats


def _no_model(monkeypatch) -> CyclePredictionService:
    monkeypatch.setattr(
        CyclePredictionService, "_load_model", lambda self: None
    )
    return CyclePredictionService()


class TestBaselinePrediction:
    def test_uses_roll_3_mean_as_baseline(self, monkeypatch):
        svc = _no_model(monkeypatch)
        out = svc.predict(_features(roll_3_mean=29.0), "2026-01-01")
        assert out is not None
        assert out["predicted_cycle_length"] == 29
        assert out["raw_predicted_cycle_length"] == 29
        assert out["last_period_start"] == "2026-01-01"
        assert out["next_period_start"] == "2026-01-30"
        assert out["confidence_interval"] is None
        assert "医学正常范围" in out["medical_guardrail_note"]
        assert out["model_version"]
        assert "10维" in out["features_info"]

    def test_accepts_date_object_as_last_start(self, monkeypatch):
        svc = _no_model(monkeypatch)
        out = svc.predict(_features(roll_3_mean=28.0), date(2026, 5, 1))
        assert out["last_period_start"] == "2026-05-01"
        assert out["next_period_start"] == "2026-05-29"

    def test_clamps_out_of_range_value_to_guardrail(self, monkeypatch):
        svc = _no_model(monkeypatch)
        too_long = svc.predict(_features(roll_3_mean=60.0), "2026-01-01")
        assert too_long["predicted_cycle_length"] == 45
        assert too_long["raw_predicted_cycle_length"] == 60
        assert "按医学边界修正" in too_long["medical_guardrail_note"]

        too_short = svc.predict(_features(roll_3_mean=5.0), "2026-01-01")
        assert too_short["predicted_cycle_length"] == 21

    def test_rejects_invalid_features(self, monkeypatch):
        svc = _no_model(monkeypatch)
        bad_missing_key = {k: 0.0 for k in FEATURE_NAMES[:-1]}
        assert svc.predict(bad_missing_key, "2026-01-01") is None
        bad_non_numeric = _features(roll_3_mean="abc")
        assert svc.predict(bad_non_numeric, "2026-01-01") is None

    def test_production_without_model_returns_none(self, monkeypatch):
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        svc = _no_model(monkeypatch)
        assert svc.predict(_features(roll_3_mean=29.0), "2026-01-01") is None


class _FakeModel:
    """最少实现的假随机森林：predict 返回单一长度，estimators_ 供置信区间。"""

    def __init__(self, pred_length=30.0, trees=(28.0, 30.0, 32.0)):
        self._pred = pred_length
        self._trees = list(trees)

    @property
    def estimators_(self):
        class _T:
            def __init__(self, value):
                self._value = value

            def predict(self, df):
                return [self._value]

        return [_T(v) for v in self._trees]

    def predict(self, df):
        return [self._pred]


class TestModelBackedPrediction:
    def test_predict_uses_model_and_returns_confidence_interval(self, monkeypatch):
        monkeypatch.setattr(
            CyclePredictionService, "_load_model", lambda self: _FakeModel(30.0)
        )
        svc = CyclePredictionService()
        from app.core.config import settings as s

        monkeypatch.setattr(s, "ENVIRONMENT", "development")
        out = svc.predict(_features(roll_3_mean=29.0), "2026-01-01")
        assert out["predicted_cycle_length"] == 30
        ci = out["confidence_interval"]
        assert ci is not None
        assert ci["note"]
        assert ci["low"] <= ci["high"]

    def test_confidence_interval_none_without_estimators(self, monkeypatch):
        monkeypatch.setattr(
            CyclePredictionService,
            "_load_model",
            lambda self: _fake_without_estimators(),
        )
        svc = CyclePredictionService()
        out = svc.predict(_features(roll_3_mean=29.0), "2026-01-01")
        assert out["confidence_interval"] is None


def _fake_without_estimators():
    class _M:
        def predict(self, df):
            return [30.0]

    return _M()


class TestBayesianShrinkage:
    """P0-2 贝叶斯收缩个性化：final = w*global + (1-w)*user_mean，w=1/(1+n/4)。"""

    def test_shrinkage_blends_global_and_user_mean(self, monkeypatch):
        # 无模型基线：roll_3_mean 充当全局输出 30；n=4 → w=0.5 → 0.5*30+0.5*26=28
        svc = _no_model(monkeypatch)
        out = svc.predict(
            _features(roll_3_mean=30.0),
            "2026-01-01",
            n_complete_cycles=4,
            user_mean=26.0,
        )
        assert out["predicted_cycle_length"] == 28
        # raw_predicted_cycle_length 保持全局模型原始输出语义（不掺收缩）
        assert out["raw_predicted_cycle_length"] == 30

    def test_shrinkage_weights_and_k(self, monkeypatch):
        svc = _no_model(monkeypatch)
        # 内部权重函数：K=4 时 n=4 → w=0.5；n=12 → w=0.25
        assert CyclePredictionService.SHRINKAGE_K == 4.0
        w4, m4 = svc._compute_shrinkage(4, 26.0)
        assert abs(w4 - 0.5) < 1e-9 and m4 == 26.0
        w12, _ = svc._compute_shrinkage(12, 26.0)
        assert abs(w12 - 0.25) < 1e-9

    def test_shrinkage_saturates_to_user_mean_with_many_cycles(self, monkeypatch):
        # n 足够大（w→0）时输出贴近个人均值；n=400 → w≈0.0099 → 约 26.04 → round 26
        svc = _no_model(monkeypatch)
        out = svc.predict(
            _features(roll_3_mean=40.0),
            "2026-01-01",
            n_complete_cycles=400,
            user_mean=26.0,
        )
        assert out["predicted_cycle_length"] == 26

    def test_no_shrinkage_when_history_missing(self, monkeypatch):
        # n<1 → 回退纯全局预测（w=1），不被无关 user_mean 拉偏
        svc = _no_model(monkeypatch)
        out = svc.predict(
            _features(roll_3_mean=30.0),
            "2026-01-01",
            n_complete_cycles=0,
            user_mean=20.0,
        )
        assert out["predicted_cycle_length"] == 30
        # 默认参数（None/None）向后兼容：不收缩
        out2 = svc.predict(_features(roll_3_mean=30.0), "2026-01-01")
        assert out2["predicted_cycle_length"] == 30

    def test_shrinkage_clamps_after_blending(self, monkeypatch):
        # 收缩后 0.5*(60)+0.5*(10)=35 落在范围内；极端情况下仍受 21-45 guardrail 兜底
        svc = _no_model(monkeypatch)
        out = svc.predict(
            _features(roll_3_mean=60.0),
            "2026-01-01",
            n_complete_cycles=4,
            user_mean=10.0,
        )
        assert out["predicted_cycle_length"] == 35

        # 收缩后仍越界：0.5*100+0.5*10 = 55 → 被 clamp 到 45
        out_clamped = svc.predict(
            _features(roll_3_mean=100.0),
            "2026-01-01",
            n_complete_cycles=4,
            user_mean=10.0,
        )
        assert out_clamped["predicted_cycle_length"] == 45
        assert "按医学边界修正" in out_clamped["medical_guardrail_note"]

    def test_shrinkage_applies_to_confidence_interval(self, monkeypatch):
        # 模型输出30/树(28,30,32)，n=4 → w=0.5，user_mean=26：
        # 收缩后树(27,28,29) → CI low=27 high=29；note 声明已收缩
        monkeypatch.setattr(
            CyclePredictionService,
            "_load_model",
            lambda self: _FakeModel(30.0, trees=(28.0, 30.0, 32.0)),
        )
        svc = CyclePredictionService()
        out = svc.predict(
            _features(roll_3_mean=29.0),
            "2026-01-01",
            n_complete_cycles=4,
            user_mean=26.0,
        )
        assert out["predicted_cycle_length"] == 28  # 0.5*30+0.5*26
        ci = out["confidence_interval"]
        assert ci is not None
        # 树集收缩后 [27,28,29]，numpy 分位默认线性插值：
        #   5% → 27.1，95% → 28.9
        assert ci["low"] == 27.1 and ci["high"] == 28.9
        assert "已按个人历史收缩" in ci["note"]

    def test_no_shrinkage_leaves_ci_unshrunk(self, monkeypatch):
        monkeypatch.setattr(
            CyclePredictionService,
            "_load_model",
            lambda self: _FakeModel(30.0, trees=(28.0, 30.0, 32.0)),
        )
        svc = CyclePredictionService()
        out = svc.predict(_features(roll_3_mean=29.0), "2026-01-01")
        ci = out["confidence_interval"]
        # 未收缩：树集 [28,30,32] 线性插值 5% → 28.2，95% → 31.8
        assert ci["low"] == 28.2 and ci["high"] == 31.8
        assert "已按个人历史收缩" not in ci["note"]
