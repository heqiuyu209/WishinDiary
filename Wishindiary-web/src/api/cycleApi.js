import httpClient from './httpClient';

export const getPredictionApi = () => httpClient.get('/api/prediction');
export const getStatsApi = () => httpClient.get('/api/stats');
export const getHealthReportApi = () => httpClient.get('/api/report');
export const logStartApi = (data) => httpClient.post('/api/log_start', data);
export const logEndApi = (data) => httpClient.post('/api/log_end', data);
export const saveDailyLogApi = (data) => httpClient.post('/api/daily_log', data);
export const updateCycleApi = (cycleId, data) => httpClient.put(`/api/cycles/${cycleId}`, data);
export const deleteCycleApi = (cycleId) => httpClient.delete(`/api/cycles/${cycleId}`);
