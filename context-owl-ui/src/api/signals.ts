import { apiClient } from './client';
import type { Signal, SignalFilters } from '../types';

export interface PaginatedSignalsResponse {
  count: number;
  total_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
  signals: Signal[];
  cached: boolean;
  computed_at: string;
  filters: {
    min_score: number;
    entity_type: string | null;
    timeframe: string;
  };
  performance?: {
    total_time_seconds: number;
    compute_time_seconds: number;
    payload_size_kb: number;
  };
}

export const signalsAPI = {
  getSignals: async (filters?: SignalFilters & { offset?: number }): Promise<PaginatedSignalsResponse> => {
    return apiClient.get<PaginatedSignalsResponse>('/api/v1/signals/trending', {
      limit: filters?.limit ?? 15,
      offset: filters?.offset ?? 0,
      min_score: filters?.min_score,
      entity_type: filters?.entity_type,
      timeframe: filters?.timeframe,
    });
  },

  getSignalById: async (id: number): Promise<Signal> => {
    return apiClient.get<Signal>(`/api/v1/signals/${id}`);
  },

  getSignalsByEntity: async (entityId: number, filters?: Omit<SignalFilters, 'entity_id'>): Promise<PaginatedSignalsResponse> => {
    return apiClient.get<PaginatedSignalsResponse>('/api/v1/signals/trending', {
      limit: filters?.limit ?? 15,
      offset: filters?.offset ?? 0,
      entity_id: entityId,
      min_score: filters?.min_score,
      entity_type: filters?.entity_type,
      timeframe: filters?.timeframe,
    });
  },

  getEntityArticles: async (entity: string, limit: number = 5): Promise<{ entity: string; articles: any[] }> => {
    return apiClient.get<{ entity: string; articles: any[] }>(`/api/v1/signals/${entity}/articles`, {
      limit,
    });
  },
};
