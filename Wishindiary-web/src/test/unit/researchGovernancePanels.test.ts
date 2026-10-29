import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import ResearchQualityPanel from '../../modules/research/components/ResearchQualityPanel.vue';
import ResearchExperimentsPanel from '../../modules/research/components/ResearchExperimentsPanel.vue';

describe('research governance summaries', () => {
  it('keeps an empty denominator distinct from zero coverage and labels operational data', () => {
    const wrapper = mount(ResearchQualityPanel, {
      props: {
        quality: {
          available: true,
          participants: 1,
          calendar_days: 0,
          observed_days: 0,
          coverage_pct: null,
        },
      },
    });
    expect(wrapper.text()).toContain('暂无分母');
    expect(wrapper.text()).toContain('全站运营计数不等于');
  });
  it('separates retrospective exploration from prospective plans and blocks revoked result summaries', () => {
    const wrapper = mount(ResearchExperimentsPanel, {
      props: {
        experiments: [
          {
            run_id: 'a'.repeat(32),
            status: 'complete',
            kind: 'retrospective_exploration',
            source: 'synthetic',
            n_users: 12,
            eligible_cases: 100,
          },
          { run_id: 'b'.repeat(32), status: 'authorization_changed', kind: 'prospective_plan' },
        ],
      },
    });
    expect(wrapper.text()).toContain('回顾性探索');
    expect(wrapper.text()).toContain('结果停止使用');
    expect(wrapper.text()).toContain('合成演示');
    expect(wrapper.text()).toContain('不证明数据未被看过');
  });
});
