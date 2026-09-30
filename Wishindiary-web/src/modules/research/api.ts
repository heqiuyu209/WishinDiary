import type { AxiosResponse } from 'axios';
import httpClient from '../../shared/api/httpClient';
import type { ResearchSummary } from '../../types/api';

export const getResearchSummaryApi = (): Promise<AxiosResponse<ResearchSummary>> =>
  httpClient.get('/api/v1/admin/research');
