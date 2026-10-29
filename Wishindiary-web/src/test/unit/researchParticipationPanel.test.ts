import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ResearchParticipationPanel from '../../modules/research/components/ResearchParticipationPanel.vue';

const api = vi.hoisted(() => ({
  getParticipationApi: vi.fn(),
  decideParticipationApi: vi.fn(),
  saveResearchBackgroundApi: vi.fn(),
}));
vi.mock('../../modules/research/participationApi', () => api);
const fields = {
  age_band: null,
  pregnancy: null,
  breastfeeding: null,
  hormonal_contraception: null,
  diagnosed_pcos: null,
  diagnosed_thyroid: null,
};
const state = (participating = false) => ({
  status: 'success',
  participating,
  policy: { version: 'research-v1', title: '自愿参加周期预测研究', statements: ['参加完全自愿'] },
  background: { fields, known_at: null },
  decision_at: null,
});
describe('independent research participation', () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => mock.mockReset());
    api.getParticipationApi.mockResolvedValue({ data: state() });
  });
  it('requires two explicit confirmations and can withdraw without deleting records', async () => {
    const wrapper = mount(ResearchParticipationPanel);
    await flushPromises();
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined();
    await wrapper.get('#research-adult').setValue(true);
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined();
    await wrapper.get('#research-accepted').setValue(true);
    api.decideParticipationApi.mockResolvedValue({
      data: { status: 'success', message: '已自愿参加研究' },
    });
    api.getParticipationApi.mockResolvedValue({ data: state(true) });
    await wrapper.findAll('form')[0]!.trigger('submit');
    await flushPromises();
    expect(api.decideParticipationApi).toHaveBeenCalledWith({
      participate: true,
      policy_version: 'research-v1',
      adult_confirmed: true,
    });
    expect(wrapper.text()).toContain('撤回研究授权');
    api.getParticipationApi.mockResolvedValue({ data: state() });
    await wrapper
      .findAll('button')
      .find((button) => button.text() === '撤回研究授权')!
      .trigger('click');
    await flushPromises();
    expect(api.decideParticipationApi).toHaveBeenLastCalledWith({ participate: false });
    expect(wrapper.get('#research-adult').element).toMatchObject({ checked: false });
  });
  it('preserves unknown and explicit no as different values in the full background snapshot', async () => {
    const wrapper = mount(ResearchParticipationPanel);
    await flushPromises();
    await wrapper.get('#research-pregnancy').setValue('false');
    api.saveResearchBackgroundApi.mockResolvedValue({ data: { status: 'success' } });
    await wrapper.findAll('form').at(-1)!.trigger('submit');
    await flushPromises();
    expect(api.saveResearchBackgroundApi).toHaveBeenCalledWith({ ...fields, pregnancy: false });
  });
  it('recovers a failed load and blocks underage enrollment', async () => {
    api.getParticipationApi.mockRejectedValueOnce(new Error('offline'));
    const wrapper = mount(ResearchParticipationPanel);
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('加载失败');
    await wrapper.get('button').trigger('click');
    await flushPromises();
    await wrapper.get('#research-age').setValue('under18');
    await wrapper.get('#research-adult').setValue(true);
    await wrapper.get('#research-accepted').setValue(true);
    await wrapper.findAll('form')[0]!.trigger('submit');
    expect(api.decideParticipationApi).not.toHaveBeenCalled();
  });
});
