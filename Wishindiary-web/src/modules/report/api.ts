import type { AxiosResponse } from 'axios';
import httpClient from '../../shared/api/httpClient';
import type { ReportResponse } from '../../types/api';

export const getHealthReportApi = (): Promise<AxiosResponse<ReportResponse>> =>
  httpClient.get('/api/v1/report');
