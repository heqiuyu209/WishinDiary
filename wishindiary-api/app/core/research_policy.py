"""Versioned, independent research participation; application use is separate."""
POLICY_VERSION = "research-v1"
POLICY = {
    "version": POLICY_VERSION,
    "title": "自愿参加周期预测研究",
    "statements": [
        "参加完全自愿；不参加或撤回不影响日记、周期记录和提醒功能。",
        "我确认已满 18 岁，并授权已有及参加期间的周期日期、结构化睡眠、压力、运动、用药标记和自愿医学背景用于离线预测研究。",
        "邮箱、用户名、同房、日记和用药说明不进入研究数据；管理端只展示汇总结果。",
        "新的研究预测样本从本次加入之后开始；之前已授权的历史记录只用于已知历史特征。",
        "我可以随时撤回。撤回后停止使用我的研究样本，并阻止本系统继续使用或展示旧授权快照的结果。",
        "撤回不会删除个人记录；仓库外备份或已交付的汇总结果需研究负责人另行处理。参加不代表已证明预测效果或医学结论。",
    ],
}
BACKGROUND_FIELDS = ("age_band", "pregnancy", "breastfeeding", "hormonal_contraception",
                     "diagnosed_pcos", "diagnosed_thyroid")
BACKGROUND_FLAGS = BACKGROUND_FIELDS[1:]

