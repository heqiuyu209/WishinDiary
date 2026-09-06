import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import LoginView from '../../modules/auth/views/LoginView.vue';
import { getSessionApi, loginApi, registerApi } from '../../modules/auth/api';
import { useAuthStore } from '../../modules/auth/store';
import { formatDate } from '../../shared/utils/date';

const { push } = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }));
vi.mock('../../modules/auth/api', () => ({
  loginApi: vi.fn(),
  registerApi: vi.fn(),
  getSessionApi: vi.fn(),
}));

describe('登录与注册', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setActivePinia(createPinia());
  });

  it.each([
    ['ab', 'password123', '账号需要 3–50 个字符'],
    ['中文账号', 'password123', '账号只能包含英文字母'],
    ['alice', 'short', '密码至少需要 8 个字符'],
    ['alice', '密'.repeat(25), '密码过长'],
  ])('注册校验 %s，不发送无效请求', async (username, password, expected) => {
    const wrapper = mount(LoginView);
    await wrapper.find('button[type="button"]').trigger('click');
    expect(wrapper.get('#username-hint').text()).toContain('3–50');
    expect(wrapper.get('#password-hint').text()).toContain('至少 8');
    await wrapper.get('#username').setValue(username);
    await wrapper.get('#password').setValue(password);
    await wrapper.get('form').trigger('submit');
    expect(wrapper.get('[role="alert"]').text()).toContain(expected);
    expect(registerApi).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('会话未建立时留在登录页并解释原因', async () => {
    vi.mocked(loginApi).mockResolvedValue({ data: { status: 'success' } } as never);
    vi.mocked(getSessionApi).mockRejectedValue(new Error('Cookie missing'));
    const wrapper = mount(LoginView);
    await wrapper.get('#username').setValue('alice');
    await wrapper.get('#password').setValue('password123');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(wrapper.get('[role="alert"]').text()).toContain('登录会话未能建立');
    expect(useAuthStore().isLoggedIn).toBe(false);
    expect(push).not.toHaveBeenCalled();
    wrapper.unmount();
  });

  it('用服务端会话确认登录，并兼容旧账号的短密码', async () => {
    vi.mocked(loginApi).mockResolvedValue({ data: { status: 'success' } } as never);
    vi.mocked(getSessionApi).mockResolvedValue({ data: { username: 'legacy' } } as never);
    const wrapper = mount(LoginView);
    await wrapper.get('#username').setValue('legacy');
    await wrapper.get('#password').setValue('short');
    await wrapper.get('form').trigger('submit');
    await flushPromises();
    expect(useAuthStore().currentUsername).toBe('legacy');
    expect(push).toHaveBeenCalledWith('/calendar');
    wrapper.unmount();
  });

  describe('注册补录最近经期日期', () => {
    const switchToRegister = async (wrapper: ReturnType<typeof mount>) => {
      await wrapper.find('button[type="button"]').trigger('click');
    };
    const fillDate = async (wrapper: ReturnType<typeof mount>, id: string, dateStr: string) => {
      await wrapper.get(`#${id}`).setValue(dateStr);
    };

    it('展开补录并填写 2 个日期，升序去重后随注册请求发送', async () => {
      vi.mocked(registerApi).mockResolvedValue({
        data: { status: 'success', period_dates_recorded: 2 },
      } as never);
      const wrapper = mount(LoginView);
      await switchToRegister(wrapper);
      await wrapper.get('#username').setValue('alice');
      await wrapper.get('#password').setValue('password123');

      await wrapper.get('#backfill-toggle').trigger('click');
      // 填入乱序 + 重复一条，验证前端升序去重
      const later = formatDate(new Date(Date.now() - 28 * 864e5));
      const earlier = formatDate(new Date(Date.now() - 56 * 864e5));
      await fillDate(wrapper, 'backfill-date-0', later);
      await fillDate(wrapper, 'backfill-date-1', earlier);
      await wrapper.get('#backfill-add').trigger('click');
      await fillDate(wrapper, 'backfill-date-2', earlier);

      await wrapper.get('form').trigger('submit');
      await flushPromises();
      expect(registerApi).toHaveBeenCalledTimes(1);
      const payload = vi.mocked(registerApi).mock.calls[0][0];
      expect(payload).toMatchObject({
        username: 'alice',
        password: 'password123',
        period_start_dates: [earlier, later],
      });
      expect(wrapper.text()).toContain('注册成功');
      wrapper.unmount();
    });

    it('仅填写 1 个日期时前端拦截，不发送请求', async () => {
      const wrapper = mount(LoginView);
      await switchToRegister(wrapper);
      await wrapper.get('#username').setValue('alice');
      await wrapper.get('#password').setValue('password123');
      await wrapper.get('#backfill-toggle').trigger('click');
      await fillDate(wrapper, 'backfill-date-0', formatDate(new Date(Date.now() - 28 * 864e5)));

      await wrapper.get('form').trigger('submit');
      expect(wrapper.get('[role="alert"]').text()).toContain('至少需要 2 个');
      expect(registerApi).not.toHaveBeenCalled();
      wrapper.unmount();
    });

    it('未展开补录时注册请求不含 period_start_dates', async () => {
      vi.mocked(registerApi).mockResolvedValue({ data: { status: 'success' } } as never);
      const wrapper = mount(LoginView);
      await switchToRegister(wrapper);
      await wrapper.get('#username').setValue('alice');
      await wrapper.get('#password').setValue('password123');
      await wrapper.get('form').trigger('submit');
      await flushPromises();
      const payload = vi.mocked(registerApi).mock.calls[0][0];
      expect(payload).not.toHaveProperty('period_start_dates');
      expect(registerApi).toHaveBeenCalledTimes(1);
      wrapper.unmount();
    });
  });
});
