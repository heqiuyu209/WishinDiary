import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import PersonalHistoryPanel from '../../modules/research/components/PersonalHistoryPanel.vue';
import TrackingProbabilityPanel from '../../modules/research/components/TrackingProbabilityPanel.vue';
import type { LifestyleProtocol, TrackingProbabilityEvaluation } from '../../types/api';

const metrics = {
  base_direct: { samples: 12, mae: 2.5 },
  base_adaptive: { samples: 12, mae: 1.25, interval_samples: 10, coverage_pct: 90 },
  decay3: { samples: 12, mae: 1.5 },
};
const protocol: LifestyleProtocol = {
  samples: 12,
  candidate_samples: 12,
  skipped_empty_folds: 0,
  excluded_unseen_cases: 0,
  metrics,
  coverage_groups: {},
  history_groups: { short: metrics, medium: {}, long: {} },
  variability_groups: { low: {}, high: metrics },
  fits: [
    {
      training_samples: 15,
      calibration_samples: 10,
      adaptive_blend: {
        base: {
          available: false,
          training_samples: 8,
          validation_samples: 6,
          validation_users: 2,
          learned_groups: 0,
          global_model_weight: 0.5,
        },
      },
    },
  ],
};
const tracking: TrackingProbabilityEvaluation = {
  available: true,
  version: 'closed-gap-tracking-v1',
  protocols: {
    unseen_users: {
      candidate_samples: 15,
      reviewed_samples: 12,
      unreviewed_samples: 3,
      skipped_reviewed_samples: 0,
      fits: [
        {
          available: true,
          training_samples: 50,
          training_users: 5,
          training_missed: 10,
          calibration_samples: 10,
          probability_calibrated: false,
        },
      ],
      scores: {
        samples: 12,
        missed_reviews: 3,
        brier: 0.02,
        baseline_brier: 0.2,
        delta_brier: -0.18,
        delta_brier_ci95: {
          available: true,
          n_users: 12,
          samples: 12,
          min_users: 10,
          lower: -0.25,
          upper: -0.1,
        },
        reliability_bins: [
          { lower: 0, upper: 0.2, samples: 9, mean_probability: 0.1, observed_review_rate: 0 },
          {
            lower: 0.2,
            upper: 0.4,
            samples: 0,
            mean_probability: null,
            observed_review_rate: null,
          },
          {
            lower: 0.4,
            upper: 0.6,
            samples: 0,
            mean_probability: null,
            observed_review_rate: null,
          },
          {
            lower: 0.6,
            upper: 0.8,
            samples: 0,
            mean_probability: null,
            observed_review_rate: null,
          },
          { lower: 0.8, upper: 1, samples: 3, mean_probability: 0.9, observed_review_rate: 1 },
        ],
      },
    },
    existing_users: {
      candidate_samples: 5,
      reviewed_samples: 2,
      unreviewed_samples: 3,
      skipped_reviewed_samples: 2,
      fits: [],
      scores: { samples: 0 },
    },
  },
};

describe('PersonalHistoryPanel', () => {
  it('shows sparse gate fallback and changes between history and variability cohorts', async () => {
    const wrapper = mount(PersonalHistoryPanel, { props: { protocol, stage: '21' } });
    expect(wrapper.text()).toContain('0/1 个训练折学习到权重');
    expect(wrapper.text()).toContain('回退到固定 0.5');
    expect(wrapper.text()).toContain('3–5 次历史');
    expect(wrapper.text()).toContain('学习融合 MAE：1.25');
    expect(wrapper.text()).toContain('及时确认尚未开始');
    await wrapper.find('select').setValue('variability');
    expect(wrapper.text()).toContain('近期波动 >2 天');
    expect(wrapper.text()).not.toContain('3–5 次历史');
  });
  it('keeps missing reports explicit', () => {
    const wrapper = mount(PersonalHistoryPanel, { props: { stage: '0' } });
    expect(wrapper.text()).toContain('暂无个人历史分组报告');
    expect(wrapper.text()).not.toContain('0/0 个训练折');
  });
});

describe('TrackingProbabilityPanel', () => {
  it('distinguishes probability loss, uncalibrated folds and empty reliability bins', () => {
    const wrapper = mount(TrackingProbabilityPanel, { props: { evaluation: tracking } });
    expect(wrapper.text()).toContain('模型 Brier：0.0200');
    expect(wrapper.text()).toContain('[-0.2500, -0.1000]');
    expect(wrapper.text()).toContain('未经独立校准的模型分数');
    expect(wrapper.text()).toContain('未核对/未知 3 条');
    expect(wrapper.text()).toContain('不可用');
    expect(wrapper.text()).toContain('核对人群存在选择偏差');
  });
  it('does not turn sparse reviewed data into zero error', async () => {
    const wrapper = mount(TrackingProbabilityPanel, { props: { evaluation: tracking } });
    await wrapper.find('select').setValue('existing_users');
    expect(wrapper.text()).toContain('暂无可用漏记概率评估');
    expect(wrapper.text()).toContain('未核对不等于没有漏记');
    expect(wrapper.text()).not.toContain('模型 Brier');
  });
});
