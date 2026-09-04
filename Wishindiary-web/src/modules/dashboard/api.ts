import type { AxiosResponse } from 'axios';
import httpClient from '../../shared/api/httpClient';
import type { PredictionResponse, StatsResponse } from '../../types/api';

/** 预测接口（日历页 AI 预估横幅、看板共用） */
export const getPredictionApi = (): Promise<AxiosResponse<PredictionResponse>> =>
  httpClient.get('/api/v1/prediction');

/** 统计接口（周期列表 + 最近打卡日志） */
export const getStatsApi = (): Promise<AxiosResponse<StatsResponse>> =>
  httpClient.get('/api/v1/stats');
