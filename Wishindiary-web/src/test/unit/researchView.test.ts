import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ResearchView from '../../modules/research/views/ResearchView.vue';

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
    await wrapper.get('select').setValue('volatility');
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
});
