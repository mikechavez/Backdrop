import { apiClient } from './client';
import type { Narrative, NarrativesResponse } from '../types';

export interface PaginatedNarrativesResponse {
  narratives: Narrative[];
  total_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export interface PaginatedArticlesResponse {
  articles: Array<{
    title: string;
    url: string;
    source: string;
    published_at: string;
  }>;
  total_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

export const narrativesAPI = {
  getNarratives: async (params?: { limit?: number; offset?: number }): Promise<PaginatedNarrativesResponse> => {
    return apiClient.get<PaginatedNarrativesResponse>('/api/v1/narratives/active', {
      limit: params?.limit ?? 10,
      offset: params?.offset ?? 0,
    });
  },

  getNarrativeById: async (id: string | number): Promise<Narrative> => {
    return apiClient.get<Narrative>(`/api/v1/narratives/${id}`);
  },

  getArchivedNarratives: async (limit: number = 50, days: number = 30): Promise<NarrativesResponse> => {
    return apiClient.get<NarrativesResponse>(`/api/v1/narratives/archived?limit=${limit}&days=${days}`);
  },

  getResurrectedNarratives: async (limit: number = 20, days: number = 7): Promise<NarrativesResponse> => {
    return apiClient.get<NarrativesResponse>(`/api/v1/narratives/resurrections?limit=${limit}&days=${days}`);
  },

  getArticlesPaginated: async (
    narrativeId: string | number,
    offset: number = 0,
    limit: number = 20
  ): Promise<PaginatedArticlesResponse> => {
    return apiClient.get<PaginatedArticlesResponse>(
      `/api/v1/narratives/${narrativeId}/articles?offset=${offset}&limit=${limit}`
    );
  },
};
