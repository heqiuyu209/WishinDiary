import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

vi.mock('../../modules/auth/api', () => ({
  getSessionApi: vi.fn(),
}));

import { getSessionApi } from '../../modules/auth/api';
import { useAuthStore } from '../../modules/auth/store';

const getSessionApiMock = vi.mocked(getSessionApi);

describe('useAuthStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    getSessionApiMock.mockReset();
  });

  it('login 写入用户名并进入登录态', () => {
    const store = useAuthStore();
    expect(store.isLoggedIn).toBe(false);

    store.login('alice');
    expect(store.isLoggedIn).toBe(true);
    expect(store.currentUsername).toBe('alice');
  });

  it('login 可附带 email 资料', () => {
    const store = useAuthStore();
    store.login('alice', { email: 'alice@example.com' });
    expect(store.currentEmail).toBe('alice@example.com');
  });

  it('logout 清空状态', () => {
    const store = useAuthStore();
    store.login('alice', { email: 'a@b.c' });
    store.logout();
    expect(store.isLoggedIn).toBe(false);
    expect(store.currentUsername).toBe('');
    expect(store.currentEmail).toBe('');
  });

  it('已登录时 refreshSession 直接返回 true 且不请求后端', async () => {
    const store = useAuthStore();
    store.login('alice');

    const result = await store.refreshSession();
    expect(result).toBe(true);
    expect(getSessionApiMock).not.toHaveBeenCalled();
  });

  it('未登录时 refreshSession 调 session 接口成功则登录', async () => {
    getSessionApiMock.mockResolvedValue({
      data: { status: 'success', username: 'bob' },
    } as never);

    const store = useAuthStore();
    const result = await store.refreshSession();
    expect(result).toBe(true);
    expect(store.isLoggedIn).toBe(true);
    expect(store.currentUsername).toBe('bob');
  });

  it('session 接口失败时 refreshSession 返回 false 并保持登出', async () => {
    getSessionApiMock.mockRejectedValue(new Error('401'));

    const store = useAuthStore();
    const result = await store.refreshSession();
    expect(result).toBe(false);
    expect(store.isLoggedIn).toBe(false);
  });
});
