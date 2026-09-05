import axios, { AxiosError, type AxiosInstance } from 'axios';
import type { ApiErrorBody } from '../../types/api';

/**
 * 统一 HTTP 客户端。
 *
 * 认证通过后端 HttpOnly Cookie 完成（withCredentials），浏览器端不持久化任何
 * access token。401 仅在非 session 探活路径上触发全局登出事件，避免匿名访问
 * 被记录成两次失败的 session 请求。
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 10000,
  withCredentials: true,
});

apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorBody>) => {
    const isSessionProbe = error.config?.url?.endsWith('/api/v1/auth/session') ?? false;
    if (error.response?.status === 401 && !isSessionProbe) {
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
