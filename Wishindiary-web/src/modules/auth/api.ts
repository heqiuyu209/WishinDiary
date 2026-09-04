import type { AxiosResponse } from 'axios';
import httpClient from '../../shared/api/httpClient';
import type {
  LoginRequest,
  LoginResponse,
  RegisterRequest,
  RegisterResponse,
  SessionResponse,
  StatusResponse,
} from '../../types/api';

export const loginApi = (data: LoginRequest): Promise<AxiosResponse<LoginResponse>> =>
  httpClient.post('/api/v1/auth/login', data);

export const registerApi = (data: RegisterRequest): Promise<AxiosResponse<RegisterResponse>> =>
  httpClient.post('/api/v1/auth/register', data);

export const getSessionApi = (): Promise<AxiosResponse<SessionResponse>> =>
  httpClient.get('/api/v1/auth/session');

export const logoutApi = (): Promise<AxiosResponse<StatusResponse>> =>
  httpClient.post('/api/v1/auth/logout');
