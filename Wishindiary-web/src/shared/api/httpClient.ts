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

/** 从 AxiosError 中提取后端统一错误结构的 message 字段（容错 detail 回退）。 */
export function extractApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof AxiosError) {
    const body = error.response?.data as ApiErrorBody | undefined;
    const err = body?.error;
    if (err) {
      const message = typeof err.message === 'string' ? err.message.trim() : '';
      if (message) {
        return message;
      }
      const detail = err.detail;
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
