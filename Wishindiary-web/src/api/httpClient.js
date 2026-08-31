import axios from 'axios';

const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000',
  timeout: 10000,
  withCredentials: true
});

// Authentication is carried by the HttpOnly cookie set by the API. The API
// still accepts Bearer tokens for non-browser clients, but the web app never
// stores access tokens in browser storage.
// 捕捉 401 权限失效
apiClient.interceptors.response.use(
  response => response,
  error => {
    // 如果后端返回 401 (未授权/Token过期/伪造)
    if (error.response?.status === 401 && !error.config?.url?.endsWith('/api/auth/session')) {
      window.dispatchEvent(new Event('wishindiary:session-expired'));
    }
    return Promise.reject(error);
  }
);

export default apiClient;
