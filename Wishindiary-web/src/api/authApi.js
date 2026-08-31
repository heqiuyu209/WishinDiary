import httpClient from './httpClient';

export const loginApi = (data) => httpClient.post('/api/auth/login', data);
export const registerApi = (data) => httpClient.post('/api/auth/register', data);
export const getSessionApi = () => httpClient.get('/api/auth/session');
export const logoutApi = () => httpClient.post('/api/auth/logout');
