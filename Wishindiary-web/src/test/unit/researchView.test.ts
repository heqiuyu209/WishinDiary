import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ResearchView from '../../modules/research/views/ResearchView.vue';
import IntervalBreakdownTable from '../../modules/research/components/IntervalBreakdownTable.vue';
import type { ForecastCalibrationMethod } from '../../types/api';

const getSummary = vi.hoisted(() => vi.fn());
vi.mock('../../modules/research/api', () => ({ getResearchSummaryApi: getSummary }));

const fixture = () => ({
  status: 'success',
  data: {
    users: 3,
    total: 10,
    completed: 7,
    outside_range: 1,
    missing_bleeding: 2,
    users_with_ml_history: 1,
    feature_samples: 4,
    cycle_distribution: [{ days: 28, count: 3 }],
    history_distribution: [{ label: '4–7 条', count: 1 }],
  },
  evaluation: {
    available: true,
    model_version: 'test-rf',
    model_matches_report: true,
    dataset: { source: 'synthetic', real_samples: 0, synthetic_samples: 210 },
    metrics: { group_kfold: { mae: 0, baseline_mean3_mae: 1.8 } },
  },
  recommendations: ['先验证基线与完整预测流程'],
});

const forecastFixture = () => {
  const result = {
    samples: 54,
    models: {
      online_pipeline: { mae: 0, hit_rate_within_3d: 100, bias_days: 0 },
      mean3: { mae: 1.9 },
      median3: { mae: 2.1 },
      ewma: { mae: 1.8 },
    },
    intervals: { rf_personalized: { samples: 54, coverage_pct: 33.33, mean_width_days: 1.94 } },
    groups: {
      history: [{ label: '0–3 条', samples: 0, models: {} }],
      volatility: [
        { label: '高（>5 天）', samples: 12, models: { online_pipeline: { mae: 4.2 } } },
      ],
    },
  };
  return {
    available: true,
    pipeline_matches_report: true,
    cutoff: '2024-06-01',
    dataset: { source: 'synthetic', total_cycles: 300, n_users: 30 },
    protocols: {
      existing_users: result,
      unseen_users: {
        ...result,
        samples: 50,
        models: { ...result.models, online_pipeline: { mae: 1.67 } },
      },
    },
  };
};

it('CSV 没有真实日期时，时间留出明确显示不适用', async () => {
  const base = fixture();
  getSummary.mockResolvedValue({
    data: {
      ...base,
      evaluation: { ...base.evaluation, temporal_holdout_status: 'not_applicable' },
    },
  });
  const wrapper = mount(ResearchView);
  await flushPromises();
  expect(wrapper.text()).toContain('月份特征已停用');
  expect(wrapper.text()).toContain('真实日历时间留出不适用');
  const temporalRow = wrapper
    .findAll('tr')
    .find((row) => row.text().includes('时间留出 · 随机森林'));
  expect(temporalRow?.text()).toContain('不适用');
  wrapper.unmount();
});

const calibratedForecastFixture = () => {
  const forecast = forecastFixture();
  const basic: ForecastCalibrationMethod = {
    fits: [{ samples: 0, rank: 1, available: false }],
    test_samples: 0,
    unavailable_samples: 0,
    calibrated: { samples: 0 },
    comparison: { samples: 0, original: { samples: 0 }, calibrated: { samples: 0 } },
  };
  const rf: ForecastCalibrationMethod = {
    fits: [{ samples: 26, rank: 25, available: true, radius_days: 3 }],
    test_samples: 54,
    unavailable_samples: 0,
    calibrated: { samples: 54, coverage_pct: 90.74, mean_width_days: 6 },
    comparison: {
      samples: 54,
      original: { samples: 54, coverage_pct: 27.78, mean_width_days: 1.99 },
      calibrated: { samples: 54, coverage_pct: 90.74, mean_width_days: 6 },
    },
  };
  return {
    ...forecast,
    cutoff: '2024-08-18',
    calibration: {
      method: 'absolute_residual_split',
      cutoff: '2024-06-26',
      target_coverage_pct: 90,
      candidate_samples: 26,
      training_labels_available_through: '2024-06-26',
      labels_available_through: '2024-08-18',
    },
    protocols: {
      existing_users: {
        ...forecast.protocols.existing_users,
        calibration: {
          target_coverage_pct: 90,
          methods: { rf_personalized: rf, basic_stats: basic },
        },
      },
      unseen_users: {
        ...forecast.protocols.unseen_users,
        samples: 54,
        calibration: {
          target_coverage_pct: 90,
          methods: {
            rf_personalized: {
              ...rf,
              fits: [
                { samples: 20, rank: 19, available: true, radius_days: 3 },
                { samples: 7, rank: 8, available: false },
              ],
              unavailable_samples: 4,
              calibrated: { samples: 50, coverage_pct: 88, mean_width_days: 6 },
              comparison: {
                samples: 40,
                original: { samples: 40, coverage_pct: 25, mean_width_days: 2 },
                calibrated: { samples: 40, coverage_pct: 90, mean_width_days: 6 },
              },
            },
            basic_stats: { ...basic, fits: [...basic.fits, ...basic.fits] },
          },
        },
      },
    },
  };
};

describe('research administration', () => {
  beforeEach(() => getSummary.mockReset());

  it('labels synthetic metrics and preserves zero MAE', async () => {
    getSummary.mockResolvedValue({ data: fixture() });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.text()).toContain('合成数据演示');
    expect(wrapper.text()).toContain('0.00');
    expect(wrapper.text()).toContain('1.80');
    expect(wrapper.text()).toContain('先验证基线与完整预测流程');
    wrapper.unmount();
  });

  it('does not invent results when no evaluation report exists', async () => {
    getSummary.mockResolvedValue({
      data: {
        ...fixture(),
        evaluation: {
          available: false,
          message: '尚未生成离线评估报告',
        },
      },
    });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.text()).toContain('尚未生成离线评估报告');
    expect(wrapper.find('table').exists()).toBe(false);
    wrapper.unmount();
  });

  it('can retry a failed request', async () => {
    getSummary
      .mockRejectedValueOnce(new Error('network'))
      .mockResolvedValueOnce({ data: fixture() });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('请重试');
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(wrapper.text()).toContain('合成数据演示');
    wrapper.unmount();
  });

  it('compares the full pipeline and changes validation protocol and group', async () => {
    getSummary.mockResolvedValue({
      data: { ...fixture(), forecast_evaluation: forecastFixture() },
    });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.text()).toContain('完整流程前瞻回测');
    expect(wrapper.text()).toContain('共同评估样本：54 条');
    expect(wrapper.text()).toContain('33.33%');
    expect(wrapper.text()).toContain('0.00');
    expect(wrapper.text()).toContain('两种区间都未经校准');
    const unseen = wrapper.findAll('button').find((button) => button.text() === '模型未见用户')!;
    await unseen.trigger('click');
    expect(unseen.attributes('aria-pressed')).toBe('true');
    expect(wrapper.text()).toContain('共同评估样本：50 条');
    expect(wrapper.text()).toContain('1.67');
    await wrapper.get('#forecast-group').setValue('volatility');
    expect(wrapper.text()).toContain('高（>5 天）');
    expect(wrapper.text()).toContain('4.20');
    wrapper.unmount();
  });

  it('identifies stale calculation reports and protocols without samples', async () => {
    const forecast = forecastFixture();
    forecast.pipeline_matches_report = false;
    forecast.protocols.existing_users.samples = 0;
    getSummary.mockResolvedValue({ data: { ...fixture(), forecast_evaluation: forecast } });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('算法代码与回测报告不匹配');
    expect(wrapper.text()).toContain('该协议暂无可用评估样本');
    expect(wrapper.text()).not.toContain('线上完整算法');
    wrapper.unmount();
  });

  it('shows chronological boundaries and paired calibration coverage together with width', async () => {
    getSummary.mockResolvedValue({
      data: { ...fixture(), forecast_evaluation: calibratedForecastFixture() },
    });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.text()).toContain('未来测试起点 2024-08-18');
    expect(wrapper.text()).toContain('校准开始 2024-06-26');
    expect(wrapper.text()).toContain('时间校准实验');
    expect(wrapper.text()).toContain('90.74%');
    expect(wrapper.text()).toContain('27.78%');
    expect(wrapper.text()).toContain('6.00 天');
    expect(wrapper.text()).toContain('目标不代表可靠保证');
    expect(wrapper.text()).toContain('每折校准 26 条 · 1/1 折可用');
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '模型未见用户')!
      .trigger('click');
    expect(wrapper.text()).toContain('每折校准 7–20 条 · 1/2 折可用');
    expect(wrapper.text()).toContain('同一批未来样本：40 条');
    expect(wrapper.text()).toContain('88.00%');
    expect(wrapper.text()).toContain('缺少原始区间的样本不参与配对比较');
    expect(wrapper.text()).toContain('4 条测试样本因校准历史不足而无法校准');
    wrapper.unmount();
  });

  it('keeps point metrics when calibration has insufficient samples', async () => {
    const forecast = calibratedForecastFixture();
    forecast.protocols.existing_users.calibration.methods.rf_personalized = {
      fits: [{ samples: 8, rank: 9, available: false }],
      test_samples: 54,
      unavailable_samples: 54,
      calibrated: { samples: 0 },
      comparison: { samples: 0, original: { samples: 0 }, calibrated: { samples: 0 } },
    };
    getSummary.mockResolvedValue({ data: { ...fixture(), forecast_evaluation: forecast } });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.text()).toContain('共同评估样本：54 条');
    expect(wrapper.text()).toContain('线上完整算法');
    expect(wrapper.text()).toContain('校准样本不足，未生成有限区间');
    expect(wrapper.text()).toContain('54 条测试样本因校准历史不足而无法校准');
    expect(wrapper.text()).not.toContain('90.74%');
    expect(wrapper.text()).not.toContain('6.00 天');
    wrapper.unmount();
  });

  it('preserves a calibrated zero-width interval as a measured result', async () => {
    const forecast = calibratedForecastFixture();
    const rf = forecast.protocols.existing_users.calibration.methods.rf_personalized;
    rf.fits[0]!.radius_days = 0;
    rf.calibrated.mean_width_days = rf.comparison.calibrated.mean_width_days = 0;
    getSummary.mockResolvedValue({ data: { ...fixture(), forecast_evaluation: forecast } });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.text()).toContain('0.00 天');
    expect(wrapper.text()).toContain('90.74%');
    wrapper.unmount();
  });

  it('keeps missing full-pipeline reports separate from RF metrics', async () => {
    getSummary.mockResolvedValue({
      data: {
        ...fixture(),
        forecast_evaluation: { available: false, message: '尚未生成完整流程回测报告' },
      },
    });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.text()).toContain('尚未生成完整流程回测报告');
    expect(wrapper.text()).toContain('1.80');
    expect(wrapper.text()).not.toContain('共同评估样本');
    wrapper.unmount();
  });

  it('switches temporal results with protocol and keeps old reports free of invented windows', async () => {
    const forecast = calibratedForecastFixture();
    const addWindows = (
      result: typeof forecast.protocols.existing_users | typeof forecast.protocols.unseen_users,
    ) => {
      const comparisons = {
        rf_personalized: { ...result.calibration.methods.rf_personalized },
        basic_stats: { ...result.calibration.methods.basic_stats },
      };
      return {
        ...result,
        time_windows: [
          {
            start: '2024-08-18',
            end_exclusive: '2024-09-17',
            samples: result.samples,
            models: result.models,
            interval_comparison: comparisons,
          },
        ],
      };
    };
    getSummary.mockResolvedValue({
      data: {
        ...fixture(),
        forecast_evaluation: {
          ...forecast,
          time_windows: {
            window_days: 30,
            date_basis: 'forecast_anchor',
            last_candidate_date: '2024-09-10',
            end_exclusive: '2024-09-17',
          },
          protocols: {
            existing_users: addWindows(forecast.protocols.existing_users),
            unseen_users: addWindows(forecast.protocols.unseen_users),
          },
        },
      },
    });
    const wrapper = mount(ResearchView);
    await flushPromises();
    expect(wrapper.text()).toContain('后续时间窗口');
    const windows = wrapper.findAllComponents(IntervalBreakdownTable)[0]!;
    expect(windows.text()).toContain('2024-08-18');
    expect(windows.text()).toContain('90.74%');
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '模型未见用户')!
      .trigger('click');
    expect(windows.text()).toContain('88.00%');
    expect(windows.text()).toContain('4 条样本因校准历史不足');
    wrapper.unmount();

    getSummary.mockResolvedValue({
      data: { ...fixture(), forecast_evaluation: forecastFixture() },
    });
    const legacy = mount(ResearchView);
    await flushPromises();
    expect(legacy.text()).not.toContain('后续时间窗口');
    expect(legacy.findComponent(IntervalBreakdownTable).exists()).toBe(false);
    legacy.unmount();
  });
});
