// Core entity types
export interface Entity {
  id: number;
  name: string;
  entity_type: string;
  created_at: string;
}

export interface EntityMention {
  id: number;
  entity_id: number;
  article_id: number;
  mention_count: number;
  sentiment_score: number | null;
  created_at: string;
}

// Narrative summary for signals
export interface NarrativeSummary {
  id: string;                  // Narrative ObjectId
  title: string;               // Narrative title
  theme: string;               // Theme category
  lifecycle: string;           // Lifecycle stage
}

// Signal types
export interface Signal {
  entity: string;              // Entity name (e.g., "Solana")
  entity_type: string;         // Type (e.g., "cryptocurrency")
  signal_score: number;        // Overall signal strength
  velocity: number;            // Mentions per hour
  source_count: number;        // Number of sources
  sentiment: number;           // Sentiment score (-1 to 1)
  is_emerging: boolean;        // True if not part of any narrative
  narratives: NarrativeSummary[]; // Narratives containing this entity
  recent_articles: ArticleLink[]; // Recent articles mentioning this entity
  first_seen: string;          // ISO timestamp
  last_updated: string;        // ISO timestamp
}

export interface SignalScore {
  id: number;
  entity_id: number;
  signal_type: string;
  score: number;
  metadata: Record<string, any>;
  created_at: string;
}

// Lifecycle history entry
export interface LifecycleHistoryEntry {
  state: string;              // Lifecycle state (emerging, rising, hot, cooling, dormant)
  timestamp: string;          // ISO timestamp when state changed
  article_count: number;      // Article count at time of change
  velocity: number;           // Velocity at time of change
}

// Peak activity metrics
export interface PeakActivity {
  date: string;               // Date of peak activity (YYYY-MM-DD)
  article_count: number;      // Number of articles at peak
  velocity: number;           // Velocity at peak
}

// Entity relationship
export interface EntityRelationship {
  a: string;                  // First entity name
  b: string;                  // Second entity name
  weight: number;             // Co-occurrence weight
}

// Narrative types
export interface Narrative {
  _id?: string;               // MongoDB ObjectId (optional, for unique keys)
  theme: string;              // Theme category (e.g., regulatory, defi_adoption)
  title: string;              // Generated narrative title
  summary: string;            // AI-generated narrative summary
  entities?: string[];        // List of entities in this narrative
  article_count: number;      // Number of articles supporting this narrative
  mention_velocity: number;   // Articles per day rate
  lifecycle: string;          // Lifecycle stage: emerging, rising, hot, cooling, dormant
  lifecycle_state?: string;   // New lifecycle state field (if backend returns it)
  lifecycle_history?: LifecycleHistoryEntry[]; // History of lifecycle transitions
  fingerprint?: number[];     // Narrative fingerprint vector (if backend returns it)
  momentum?: string;          // Momentum trend: growing, declining, stable, unknown
  recency_score?: number;     // Freshness score (0-1), higher = more recent
  entity_relationships?: EntityRelationship[]; // Top entity co-occurrence pairs
  first_seen: string;         // ISO timestamp when narrative was first detected
  last_updated: string;       // ISO timestamp of last update
  last_article_at?: string;   // ISO timestamp when most recent article was published to this narrative
  days_active?: number;       // Number of days narrative has been active
  peak_activity?: PeakActivity; // Peak activity metrics
  timeline_data?: Array<{date: string; article_count: number; entities: string[]; velocity: number}>; // Daily timeline snapshots
  articles?: ArticleLink[];   // Articles supporting this narrative
  // Resurrection/reawakening fields
  reawakening_count?: number; // Number of times narrative has been reactivated from dormant state
  reawakened_from?: string;   // ISO timestamp when narrative went dormant before most recent reactivation
  resurrection_velocity?: number; // Articles per day in last 48 hours during reactivation
  // Backward compatibility fields
  updated_at?: string;        // Alias for last_updated
  story?: string;             // Alias for summary
}

export interface NarrativeArticle {
  id: number;
  narrative_id: number;
  article_id: number;
  relevance_score: number;
  created_at: string;
}

// Article types
export interface Article {
  id: number;
  title: string;
  url: string;
  published_at: string;
  source: string;
  summary: string | null;
  sentiment_score: number | null;
  created_at: string;
}

// Simplified article for signal/narrative displays
export interface ArticleLink {
  title: string;
  url: string;
  source: string;
  published_at: string;
}

// API response types
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// Signal response types
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

export interface SignalsResponse {
  signals: Signal[];
  total: number;
}

// Narrative response types
export interface PaginatedNarrativesResponse {
  narratives: Narrative[];
  total_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
}

// Backend returns array directly, not wrapped in object
export type NarrativesResponse = Narrative[];

export interface EntityDetailResponse {
  entity: Entity;
  mentions: EntityMention[];
  signals: Signal[];
  recent_articles: Article[];
}

// Filter and query types
export interface SignalFilters extends Record<string, string | number | boolean | undefined> {
  entity_id?: number;
  signal_type?: string;
  min_score?: number;
  min_strength?: number;
  limit?: number;
  offset?: number;
  entity_type?: string;
  timeframe?: '24h' | '7d' | '30d';
}

export interface NarrativeFilters extends Record<string, string | number | boolean | string[] | undefined> {
  min_articles?: number;
  limit?: number;
  offset?: number;
}

// Briefing types
export interface BriefingRecommendation {
  title: string;           // Narrative title
  theme: string;           // Theme category (Regulatory, Technology, etc.)
  narrative_id?: string;   // Optional link to narrative
}

export interface BriefingContent {
  narrative: string;                    // Full analyst memo (markdown)
  key_insights: string[];               // Bullet points
  entities_mentioned: string[];         // Entities in this briefing
  detected_patterns: string[];          // Patterns agent identified
  recommendations: BriefingRecommendation[]; // Recommended reading
}

export interface BriefingMetadata {
  narratives_analyzed: number;
  signals_analyzed: number;
  articles_analyzed: number;
  generation_time_ms: number;
}

export interface Briefing {
  _id: string;
  type: 'morning' | 'evening';
  generated_at: string;                 // ISO timestamp
  content: BriefingContent;
  metadata: BriefingMetadata;
  version: string;
}

export interface BriefingResponse {
  briefing: Briefing | null;
  next_briefing_at: string;             // ISO timestamp for next briefing
}
