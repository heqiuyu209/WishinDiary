import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from 'axios';
import type { ApiErrorBody } from '../../types/api';

/**
 * 统一 HTTP 客户端。
 *
 * 认证通过后端 HttpOnly Cookie 完成（withCredentials），浏览器端不持久化任何
 * access token。会话过期后共享一次刷新请求，并只重试原请求一次。
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 10000,
  withCredentials: true,
});

type SessionConfig = InternalAxiosRequestConfig & {
  _wishAuthRetried?: boolean;
  _wishAuthGeneration?: number;
};
let authGeneration = 0;
let refreshPromise: Promise<unknown> | null = null;
apiClient.interceptors.request.use((config) => {
  (config as SessionConfig)._wishAuthGeneration = authGeneration;
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError<ApiErrorBody>) => {
    const config = error.config as SessionConfig | undefined;
    const isAuthAction = /\/auth\/(login|register|logout|refresh)$/.test(config?.url ?? '');
    const isSessionProbe = error.config?.url?.endsWith('/api/v1/auth/session') ?? false;
    if (error.response?.status === 401 && config && !isAuthAction && !config._wishAuthRetried) {
      config._wishAuthRetried = true;
      try {
        // A delayed 401 may belong to the cookie before a completed refresh.
        if ((config._wishAuthGeneration ?? 0) >= authGeneration) {
          if (!refreshPromise) {
            refreshPromise = apiClient
              .post('/api/v1/auth/refresh')
              .then((response) => {
                authGeneration += 1;
                return response;
              })
              .finally(() => {
                refreshPromise = null;
              });
          }
          await refreshPromise;
        }
        return apiClient.request(config);
      } catch {
        // The original request remains the caller's failure; credentials are
        // never stored in browser storage or returned by this client.
      }
    }
    if (error.response?.status === 401 && !isSessionProbe && !isAuthAction) {
      window.dispatchEvent(new Event('wishindiary:session-expired'));
    }
    return Promise.reject(error);
  },
);

function validationMessage(item: unknown): string {
  if (!item || typeof item !== 'object') return '输入格式无效';
  const issue = item as {
    loc?: unknown[];
    type?: string;
    msg?: string;
    ctx?: Record<string, unknown>;
  };
  const field = issue.loc?.at(-1);
  const label = field === 'username' ? '账号' : field === 'password' ? '密码' : '';
  if (label) {
    if (issue.type === 'missing') return `请输入${label}`;
    if (issue.type === 'string_too_short')
      return `${label}至少需要 ${issue.ctx?.min_length} 个字符`;
    if (issue.type === 'string_too_long') return `${label}最多允许 ${issue.ctx?.max_length} 个字符`;
    if (field === 'username' && issue.type === 'string_pattern_mismatch') {
      return '账号只能包含英文字母、数字、下划线（_）、点（.）和短横线（-）';
    }
  }
  return issue.msg ? `${label ? `${label}：` : ''}${issue.msg}` : '输入格式无效';
}

/** 422 优先显示字段错误，其余响应保留后端业务提示。 */
export function extractApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof AxiosError) {
    const body = error.response?.data as ApiErrorBody | undefined;
    const err = body?.error;
    if (err) {
      const detail = err.detail;
      if (error.response?.status === 422 && Array.isArray(detail) && detail.length) {
        return detail.map(validationMessage).join('；');
      }
      const message = typeof err.message === 'string' ? err.message.trim() : '';
      if (message) {
        return message;
      }
      if (Array.isArray(detail)) {
        return detail
          .map((item) =>
            item && typeof item === 'object' && 'msg' in item
              ? String((item as { msg: string }).msg)
              : '输入格式无效',
          )
          .join('；');
      }
      if (typeof detail === 'string' && detail.trim()) {
        return detail;
      }
    }
  }
  return fallback;
}

export default apiClient;
