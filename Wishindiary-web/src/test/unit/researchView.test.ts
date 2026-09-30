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
});
