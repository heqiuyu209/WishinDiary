import type { AxiosResponse } from 'axios';
import httpClient from '../../shared/api/httpClient';
import type {
  NotificationPreferences,
  NotificationSettings,
  StatusResponse,
} from '../../types/api';

export const getNotificationSettingsApi = (): Promise<AxiosResponse<NotificationSettings>> =>
  httpClient.get('/api/v1/notifications/settings');
export const requestEmailCodeApi = (email: string): Promise<AxiosResponse<StatusResponse>> =>
  httpClient.post('/api/v1/notifications/email/request', { email });
export const verifyEmailApi = (code: string): Promise<AxiosResponse<StatusResponse>> =>
  httpClient.post('/api/v1/notifications/email/verify', { code });
export const saveNotificationPreferencesApi = (
  data: NotificationPreferences,
): Promise<AxiosResponse<StatusResponse>> => httpClient.put('/api/v1/notifications/settings', data);
export const unbindEmailApi = (): Promise<AxiosResponse<StatusResponse>> =>
  httpClient.delete('/api/v1/notifications/email');
