import httpClient from '../../shared/api/httpClient';
import type { StatusResponse } from '../../types/api';

export type AgeBand = 'under18' | '18_24' | '25_34' | '35_44' | '45_plus';
export interface ResearchBackground {
  age_band: AgeBand | null;
  pregnancy: boolean | null;
  breastfeeding: boolean | null;
  hormonal_contraception: boolean | null;
  diagnosed_pcos: boolean | null;
  diagnosed_thyroid: boolean | null;
}
export interface ParticipationState extends StatusResponse {
  policy: { version: string; title: string; statements: string[] };
  participating: boolean;
  decision_at: string | null;
  background: { fields: ResearchBackground; known_at: string | null };
}
export const getParticipationApi = () =>
  httpClient.get<ParticipationState>('/api/v1/research/participation');
export const decideParticipationApi = (request: {
  participate: boolean;
  policy_version?: string;
  adult_confirmed?: boolean;
}) => httpClient.put<StatusResponse>('/api/v1/research/participation', request);
export const saveResearchBackgroundApi = (fields: ResearchBackground) =>
  httpClient.put<StatusResponse>('/api/v1/research/background', fields);
