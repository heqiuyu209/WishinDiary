import type { AxiosResponse } from 'axios';
import httpClient from '../../shared/api/httpClient';
import type {
  CycleOperationResponse,
  CycleUpdateRequest,
  DailyLogReadResponse,
  DailyLogRequest,
  DailyLogResponse,
  LogEndRequest,
  LogStartRequest,
} from '../../types/api';

export const logStartApi = (
  data: LogStartRequest,
): Promise<AxiosResponse<CycleOperationResponse>> => httpClient.post('/api/v1/log_start', data);

export const logEndApi = (data: LogEndRequest): Promise<AxiosResponse<CycleOperationResponse>> =>
  httpClient.post('/api/v1/log_end', data);

export const saveDailyLogApi = (data: DailyLogRequest): Promise<AxiosResponse<DailyLogResponse>> =>
  httpClient.post('/api/v1/daily_log', data);

export const getDailyLogApi = (
  date: string,
): Promise<AxiosResponse<DailyLogReadResponse>> =>
  httpClient.get('/api/v1/daily_log', { params: { date } });

export const updateDailyLogApi = (data: DailyLogRequest): Promise<AxiosResponse<DailyLogResponse>> =>
  httpClient.put('/api/v1/daily_log', data);

export const deleteDailyLogApi = (
  date: string,
): Promise<AxiosResponse<DailyLogResponse>> =>
  httpClient.delete('/api/v1/daily_log', { params: { date } });

export const updateCycleApi = (
  cycleId: number,
  data: CycleUpdateRequest,
): Promise<AxiosResponse<CycleOperationResponse>> =>
  httpClient.put(`/api/v1/cycles/${cycleId}`, data);

export const deleteCycleApi = (cycleId: number): Promise<AxiosResponse<CycleOperationResponse>> =>
  httpClient.delete(`/api/v1/cycles/${cycleId}`);
