import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import IntervalBreakdownTable from '../../modules/research/components/IntervalBreakdownTable.vue';
import type { ForecastBreakdownRow, ForecastIntervalComparison } from '../../types/api';

const empty = (samples = 0): ForecastIntervalComparison => ({
  test_samples: samples,
  unavailable_samples: samples,
  calibrated: { samples: 0 },
  comparison: { samples: 0, original: { samples: 0 }, calibrated: { samples: 0 } },
});

const row = (): ForecastBreakdownRow => ({
  label: '2024-09-01 至 2024-10-01（不含）',
  samples: 10,
  models: { online_pipeline: { mae: 0 }, mean3: { mae: 1.2 } },
  interval_comparison: {
    rf_personalized: {
      test_samples: 6,
      unavailable_samples: 2,
      calibrated: { samples: 4, coverage_pct: 75, mean_width_days: 6 },
      comparison: {
        samples: 3,
        original: { samples: 3, coverage_pct: 66.67, mean_width_days: 2 },
        calibrated: { samples: 3, coverage_pct: 100, mean_width_days: 6 },
      },
    },
    basic_stats: empty(4),
  },
});

describe('interval breakdown table', () => {
  it('keeps paired and all-calibrated denominators separate and changes paths', async () => {
    const wrapper = mount(IntervalBreakdownTable, {
      props: { rows: [row()], selectorLabel: '分窗区间路径' },
    });
    expect(wrapper.text()).toContain('66.67%');
    expect(wrapper.text()).toContain('100.00%');
    expect(wrapper.text()).toContain('75.00%');
    expect(wrapper.text()).toContain('6.00 天');
    expect(wrapper.text()).toContain('0.00');
    expect(wrapper.text()).toContain('2 条样本因校准历史不足');
    expect(wrapper.text()).toContain('全部可校准 4 条');
    await wrapper.get('select').setValue('basic_stats');
    expect(wrapper.text()).toContain('4 条样本因校准历史不足');
    expect(wrapper.text()).toContain('暂无配对区间样本');
    expect(wrapper.text()).not.toContain('66.67%');
    expect(wrapper.text()).not.toContain('75.00%');
    wrapper.unmount();
  });

  it('does not invent zero metrics for an empty time window', () => {
    const wrapper = mount(IntervalBreakdownTable, {
      props: {
        selectorLabel: '分窗区间路径',
        rows: [
          {
            label: '空窗',
            samples: 0,
            models: {},
            interval_comparison: { rf_personalized: empty(), basic_stats: empty() },
          },
        ],
      },
    });
    expect(wrapper.text()).toContain('该路径暂无样本');
    expect(wrapper.text()).toContain('暂无结果');
    expect(wrapper.text()).not.toContain('0.00%');
    wrapper.unmount();
  });

  it('preserves measured zero-width intervals and hides point columns for group comparison', () => {
    const measured = row();
    const rf = measured.interval_comparison!.rf_personalized;
    rf.calibrated.mean_width_days = rf.comparison.calibrated.mean_width_days = 0;
    const wrapper = mount(IntervalBreakdownTable, {
      props: { rows: [measured], selectorLabel: '分组区间路径', includePoint: false },
    });
    expect(wrapper.text()).toContain('0.00 天');
    expect(wrapper.text()).toContain('100.00%');
    expect(wrapper.text()).not.toContain('完整算法 MAE');
    wrapper.unmount();
  });
});
