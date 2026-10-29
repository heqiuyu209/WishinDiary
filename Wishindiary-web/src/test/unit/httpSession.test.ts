import { flushPromises } from '@vue/test-utils';
import { AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

function unauthorized(config: InternalAxiosRequestConfig) {
  return new AxiosError('Unauthorized', 'ERR_BAD_REQUEST', config, undefined, {
    status: 401,
    statusText: 'Unauthorized',
    headers: {},
    config,
    data: {},
  });
}

function success(config: InternalAxiosRequestConfig) {
  return { config, data: { status: 'success' }, status: 200, statusText: 'OK', headers: {} };
}

describe('cookie session renewal', () => {
  beforeEach(() => vi.resetModules());

  it('shares one refresh for concurrent expired requests', async () => {
    const { default: client } = await import('../../shared/api/httpClient');
    let finishRefresh!: () => void;
    const gate = new Promise<void>((resolve) => {
      finishRefresh = resolve;
    });
    let refreshes = 0;
    const attempts = new Map<string, number>();
    client.defaults.adapter = async (config) => {
      if (config.url === '/api/v1/auth/refresh') {
        refreshes += 1;
        await gate;
        return success(config);
      }
      const count = (attempts.get(config.url!) ?? 0) + 1;
      attempts.set(config.url!, count);
      if (count === 1) throw unauthorized(config);
      return success(config);
    };
    const requests = Promise.all([client.get('/one'), client.get('/two')]);
    await flushPromises();
    expect(refreshes).toBe(1);
    finishRefresh();
    expect((await requests).map((r) => r.status)).toEqual([200, 200]);
    expect([...attempts.values()]).toEqual([2, 2]);
  });

  it('reuses the renewed session when an earlier 401 arrives late', async () => {
    const { default: client } = await import('../../shared/api/httpClient');
    let releaseLate!: () => void;
    const late = new Promise<void>((resolve) => {
      releaseLate = resolve;
    });
    const attempts = new Map<string, number>();
    let refreshes = 0;
    client.defaults.adapter = async (config) => {
      if (config.url === '/api/v1/auth/refresh') {
        refreshes += 1;
        return success(config);
      }
      const count = (attempts.get(config.url!) ?? 0) + 1;
      attempts.set(config.url!, count);
      if (count === 1) {
        if (config.url === '/late') await late;
        throw unauthorized(config);
      }
      return success(config);
    };
    const delayed = client.get('/late');
    await client.get('/fast');
    releaseLate();
    expect((await delayed).status).toBe(200);
    expect(refreshes).toBe(1);
  });

  it('retries only once and emits one expiry event if the retry fails', async () => {
    const { default: client } = await import('../../shared/api/httpClient');
    const expired = vi.fn();
    window.addEventListener('wishindiary:session-expired', expired);
    let requests = 0;
    let refreshes = 0;
    client.defaults.adapter = async (config) => {
      if (config.url === '/api/v1/auth/refresh') {
        refreshes += 1;
        return success(config);
      }
      requests += 1;
      throw unauthorized(config);
    };
    await expect(client.get('/protected')).rejects.toMatchObject({ response: { status: 401 } });
    expect(requests).toBe(2);
    expect(refreshes).toBe(1);
    expect(expired).toHaveBeenCalledOnce();
    window.removeEventListener('wishindiary:session-expired', expired);
  });

  it('does not refresh failed login credentials', async () => {
    const { default: client } = await import('../../shared/api/httpClient');
    const urls: string[] = [];
    client.defaults.adapter = async (config) => {
      urls.push(config.url!);
      throw unauthorized(config);
    };
    await expect(client.post('/api/v1/auth/login')).rejects.toMatchObject({
      response: { status: 401 },
    });
    expect(urls).toEqual(['/api/v1/auth/login']);
  });

  it('fails a session probe without a global logout loop when refresh is rejected', async () => {
    const { default: client } = await import('../../shared/api/httpClient');
    const expired = vi.fn();
    window.addEventListener('wishindiary:session-expired', expired);
    const urls: string[] = [];
    client.defaults.adapter = async (config) => {
      urls.push(config.url!);
      throw unauthorized(config);
    };
    await expect(client.get('/api/v1/auth/session')).rejects.toMatchObject({
      response: { status: 401 },
    });
    expect(urls).toEqual(['/api/v1/auth/session', '/api/v1/auth/refresh']);
    expect(expired).not.toHaveBeenCalled();
    window.removeEventListener('wishindiary:session-expired', expired);
  });
});
