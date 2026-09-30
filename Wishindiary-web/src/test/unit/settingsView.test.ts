import { flushPromises, mount } from '@vue/test-utils';
import { createPinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import SettingsView from '../../modules/settings/views/SettingsView.vue';

const api = vi.hoisted(() => ({
  getNotificationSettingsApi: vi.fn(),
  requestEmailCodeApi: vi.fn(),
  verifyEmailApi: vi.fn(),
  saveNotificationPreferencesApi: vi.fn(),
  unbindEmailApi: vi.fn(),
}));
vi.mock('../../modules/settings/api', () => api);

const state = (overrides = {}) => ({
  status: 'success',
  email: null,
  email_verified: false,
  pending_email: null,
  enabled: false,
  lead_days: 2,
  timezone: 'Asia/Shanghai',
  mail_available: true,
  last_delivery_state: null,
  ...overrides,
});
const render = () => mount(SettingsView, { global: { plugins: [createPinia()] } });

describe('email and reminder settings', () => {
  beforeEach(() => {
    Object.values(api).forEach((mock) => mock.mockReset());
    api.getNotificationSettingsApi.mockResolvedValue({ data: state() });
  });

  it('keeps reminders unavailable until email is verified and mail is configured', async () => {
    api.getNotificationSettingsApi.mockResolvedValue({ data: state({ mail_available: false }) });
    const wrapper = render();
    await flushPromises();
    expect(wrapper.text()).toContain('邮箱服务尚未启用');
    expect(wrapper.get('input[type="checkbox"]').attributes('disabled')).toBeDefined();
    expect(wrapper.get('button[type="submit"]').attributes('disabled')).toBeDefined();
    wrapper.unmount();
  });

  it('binds through a code, shows resend cooldown, and leaves reminders opt-in', async () => {
    api.getNotificationSettingsApi
      .mockResolvedValueOnce({ data: state() })
      .mockResolvedValueOnce({ data: state({ pending_email: 'alice@example.com' }) })
      .mockResolvedValueOnce({ data: state({ email: 'alice@example.com', email_verified: true }) });
    api.requestEmailCodeApi.mockResolvedValue({
      data: { status: 'success', message: '验证码已发送' },
    });
    api.verifyEmailApi.mockResolvedValue({ data: { status: 'success', message: '邮箱验证成功' } });
    const wrapper = render();
    await flushPromises();
    await wrapper.get('#binding-email').setValue('alice@example.com');
    await wrapper.findAll('form')[0]!.trigger('submit');
    await flushPromises();
    expect(api.requestEmailCodeApi).toHaveBeenCalledWith('alice@example.com');
    expect(wrapper.text()).toContain('60 秒后可重发');
    await wrapper.get('#email-code').setValue('123456');
    await wrapper.findAll('form')[1]!.trigger('submit');
    await flushPromises();
    expect(api.verifyEmailApi).toHaveBeenCalledWith('123456');
    expect(wrapper.get('input[type="checkbox"]').element).toMatchObject({
      checked: false,
      disabled: false,
    });
    wrapper.unmount();
  });

  it('saves the selected lead time and timezone for a verified account', async () => {
    api.getNotificationSettingsApi.mockResolvedValue({
      data: state({ email: 'a@example.com', email_verified: true }),
    });
    api.saveNotificationPreferencesApi.mockResolvedValue({ data: { status: 'success' } });
    const wrapper = render();
    await flushPromises();
    await wrapper.get('input[type="checkbox"]').setValue(true);
    await wrapper.get('#reminder-lead').setValue('3');
    await wrapper.get('#reminder-timezone').setValue('UTC');
    await wrapper.findAll('form').at(-1)!.trigger('submit');
    await flushPromises();
    expect(api.saveNotificationPreferencesApi).toHaveBeenCalledWith({
      enabled: true,
      lead_days: 3,
      timezone: 'UTC',
    });
    wrapper.unmount();
  });

  it('clears a load failure after retrying successfully', async () => {
    api.getNotificationSettingsApi
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce({ data: state() });
    const wrapper = render();
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('设置加载失败');
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(false);
    expect(wrapper.find('#binding-email').exists()).toBe(true);
    wrapper.unmount();
  });
});
