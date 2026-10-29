import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import LifestyleResearchPanel from '../../modules/research/components/LifestyleResearchPanel.vue';
import type { LifestyleEvaluation, LifestyleProtocol } from '../../types/api';

const methods = ['base', 'sleep', 'sleep_stress', 'sleep_stress_exercise'];
const metrics = Object.fromEntries(
  methods.flatMap((group) =>
    ['direct', 'shrinkage'].map((mode) => [
      `${group}_${mode}`,
      {
        samples: 10,
        mae: mode === 'direct' ? 1.25 : 2.5,
        hit_rate_within_2d: 80,
        delta_mae_vs_base: 0,
        interval_samples: 0,
        interval_unavailable_samples: 10,
      },
    ]),
  ),
);
const protocol: LifestyleProtocol = {
  samples: 10,
  candidate_samples: 10,
  skipped_empty_folds: 0,
  excluded_unseen_cases: 0,
  metrics,
  coverage_groups: { none: metrics, sparse: {}, covered: {} },
};
const evaluation: LifestyleEvaluation = {
  available: true,
  feature_version: 'cycle-lifestyle-research-v1',
  dataset: { source: 'synthetic', n_users: 3 },
  target_coverage_pct: 90,
  pipeline_matches_report: false,
  stages: {
    '0': { target: 'cycle_length_days', protocols: { unseen_users: protocol } },
    '7': {
      target: 'remaining_wait_days',
      protocols: { unseen_users: { ...protocol, samples: 0 } },
    },
  },
};

describe('LifestyleResearchPanel', () => {
  it('显示合成限制、失配、校准不足和收缩对照', async () => {
    const wrapper = mount(LifestyleResearchPanel, { props: { evaluation } });
    expect(wrapper.text()).toContain('不能代表真实预测准确率');
    expect(wrapper.text()).toContain('报告与当前算法代码不匹配');
    expect(wrapper.text()).toContain('1.25');
    expect(wrapper.text()).toContain('不可用（0/10）');
    await wrapper.findAll('select')[2]!.setValue('shrinkage');
    expect(wrapper.text()).toContain('2.50');
    await wrapper.findAll('select')[0]!.setValue('7');
    expect(wrapper.text()).toContain('未打卡不等于尚未开始');
    expect(wrapper.text()).toContain('暂无可用共同测试样本');
  });
  it('没有报告时保留真实填写量与旧值说明', () => {
    const wrapper = mount(LifestyleResearchPanel, {
      props: {
        coverage: {
          total: 3,
          legacy: 1,
          recorded: 2,
          sleep: 1,
          stress: 0,
          exercise: 2,
          intensity: 1,
        },
      },
    });
    expect(wrapper.text()).toContain('新版日志 2 条');
    expect(wrapper.text()).toContain('压力已填写 0/2');
    expect(wrapper.text()).toContain('尚未生成生活因素离线对照报告');
  });
  it('shows paired uncertainty and labels the fixed comparison without hiding insufficient users', () => {
    const withIntervals: LifestyleEvaluation = {
      ...evaluation,
      primary_comparison: {
        stage: '0',
        protocol: 'unseen_users',
        method: 'sleep_stress_exercise_direct',
        baseline: 'base_direct',
      },
      stages: {
        '0': {
          target: 'cycle_length_days',
          protocols: {
            unseen_users: {
              ...protocol,
              metrics: {
                ...metrics,
                sleep_direct: {
                  ...metrics.sleep_direct!,
                  delta_mae_ci95: { available: false, n_users: 3, samples: 10, min_users: 10 },
                },
                sleep_stress_exercise_direct: {
                  ...metrics.sleep_stress_exercise_direct!,
                  delta_mae_ci95: {
                    available: true,
                    n_users: 12,
                    samples: 24,
                    min_users: 10,
                    lower: -0.75,
                    upper: 0.25,
                  },
                },
              },
            },
          },
        },
      },
    };
    const wrapper = mount(LifestyleResearchPanel, { props: { evaluation: withIntervals } });
    expect(wrapper.text()).toContain('用户不足（3/10）');
    expect(wrapper.text()).toContain('[-0.75, 0.25]');
    expect(wrapper.text()).toContain('固定主对照');
    expect(wrapper.text()).toContain('未做多重比较校正');
  });
});
