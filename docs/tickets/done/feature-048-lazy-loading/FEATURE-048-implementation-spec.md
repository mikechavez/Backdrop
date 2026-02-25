# FEATURE-048: Lazy Loading Implementation Spec

> **Purpose**: Exact code changes for Claude Code to implement lazy loading on Signals and Narratives pages.
> **Approach**: Cursor-based pagination (backend) + Intersection Observer infinite scroll (frontend).
> **Constraint**: Atlas M0 — no `allowDiskUse`, avoid expensive sorts on large result sets.

---

## Architecture Summary

```
CURRENT:  Frontend loads ALL items → waits → renders everything
NEW:      Frontend loads 15 items → renders immediately → loads more on scroll
```

**Signals page**: Backend `/api/v1/signals/trending` computes all signals, returns all. Change to return paginated slices.

**Narratives page**: Backend `/api/v1/narratives/active` returns all active narratives. Change to return paginated slices. (Article pagination within narratives already exists — don't touch it.)

---

## PART 1: Backend — Signals Pagination

### File: `src/crypto_news_aggregator/api/v1/endpoints/signals.py`

#### 1A. Add pagination params to `get_trending_signals`

**Find** the function signature (around line 394):

```python
@router.get("/trending")
async def get_trending_signals(
    limit: int = Query(default=50, ge=1, le=100, description="Maximum number of results"),
    min_score: float = Query(default=0.0, ge=0.0, le=10.0, description="Minimum signal score"),
    entity_type: Optional[str] = Query(default=None, description="Filter by entity type (ticker, project, event)"),
    timeframe: str = Query(default="7d", description="Time window for scoring (24h, 7d, or 30d)"),
) -> Dict[str, Any]:
```

**Replace with**:

```python
@router.get("/trending")
async def get_trending_signals(
    limit: int = Query(default=15, ge=1, le=100, description="Maximum number of results per page"),
    offset: int = Query(default=0, ge=0, description="Number of items to skip for pagination"),
    min_score: float = Query(default=0.0, ge=0.0, le=10.0, description="Minimum signal score"),
    entity_type: Optional[str] = Query(default=None, description="Filter by entity type (ticker, project, event)"),
    timeframe: str = Query(default="7d", description="Time window for scoring (24h, 7d, or 30d)"),
) -> Dict[str, Any]:
```

> Changed default limit from 50→15 (one page). Added `offset` param.

#### 1B. Change compute call to fetch full set, then slice

The current code computes `trending` and then builds the full response. We need to:
1. Always compute the FULL signal set (for caching — signals are computed on-demand and expensive)
2. Slice AFTER computation for the paginated response
3. Only batch-fetch narratives/articles for the CURRENT PAGE's entities (not all)

**Find** the block starting around line 444 (after validation, after cache check):

```python
    # Compute signals on-demand
    try:
        start_time = time.time()

        # Compute trending signals using the new on-demand approach
        trending = await compute_trending_signals(
            timeframe=timeframe,
            limit=limit,
            min_score=min_score,
            entity_type=entity_type,
        )
```

**Replace with**:

```python
    # Compute signals on-demand
    try:
        start_time = time.time()

        # Always compute full set (up to 100) for caching; paginate after
        max_compute = 100
        trending = await compute_trending_signals(
            timeframe=timeframe,
            limit=max_compute,
            min_score=min_score,
            entity_type=entity_type,
        )
```


#### 1C. Update cache key to NOT include offset/limit

Cache the full enriched response and slice from cache for subsequent pages. The cache key must NOT include offset/limit so all pages share the same cache entry.

**Find** the cache key (around line 435):

```python
    # Build cache key including timeframe
    cache_key = f"signals:trending:v2:{limit}:{min_score}:{entity_type or 'all'}:{timeframe}"
```

**Replace with**:

```python
    # Build cache key — cache the FULL result set, not per-page
    # Pagination (offset/limit) is applied after cache retrieval
    cache_key = f"signals:trending:v3:{min_score}:{entity_type or 'all'}:{timeframe}"
```

**Find** the cache hit block (around line 438-442):

```python
    # Try to get from cache (Redis or in-memory) - 60 second TTL
    cached_result = get_from_cache(cache_key)
    if cached_result is not None:
        # Add cache hit indicator
        cached_result["cached"] = True
        return cached_result
```

**Replace with**:

```python
    # Try to get from cache (Redis or in-memory) - 60 second TTL
    cached_result = get_from_cache(cache_key)
    if cached_result is not None:
        # Paginate from cached full result
        all_signals = cached_result.get("signals", [])
        total_count = len(all_signals)
        page_signals = all_signals[offset:offset + limit]
        return {
            "count": len(page_signals),
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total_count,
            "filters": cached_result.get("filters", {}),
            "signals": page_signals,
            "cached": True,
            "computed_at": cached_result.get("computed_at"),
            "performance": cached_result.get("performance", {}),
        }
```

#### 1D. Enrich all signals, cache full set, return paginated slice

Enrich ALL signals (not just the page), cache the full enriched list, then return the sliced page. The enrichment is already batched and fast (~0.3s for 50 entities). This keeps the cache useful for all pages.

**Replace everything** from after `compute_trending_signals()` through `return response` (roughly lines 456-529) with:

```python
        compute_time = time.time() - start_time
        logger.info(f"[Signals] Computed {len(trending)} trending signals in {compute_time:.3f}s")

        total_count = len(trending)

        # Collect ALL narrative IDs and entities for batch fetching (for cache)
        all_narrative_ids = set()
        entities = []
        for signal in trending:
            narrative_ids = signal.get("narrative_ids", [])
            all_narrative_ids.update(narrative_ids)
            entities.append(signal["entity"])

        # Batch fetch all narratives in one query
        batch_start = time.time()
        narratives_list = await get_narrative_details(list(all_narrative_ids))
        narratives_by_id = {n["id"]: n for n in narratives_list}
        logger.info(f"[Signals] Batch fetched {len(narratives_list)} narratives in {time.time() - batch_start:.3f}s")

        # Batch fetch all articles in one query
        batch_start = time.time()
        articles_by_entity = await get_recent_articles_batch(entities, limit_per_entity=5)
        total_articles = sum(len(articles) for articles in articles_by_entity.values())
        logger.info(f"[Signals] Batch fetched {total_articles} articles for {len(entities)} entities in {time.time() - batch_start:.3f}s")

        # Build FULL enriched list (for caching)
        all_enriched_signals = []
        for signal in trending:
            narrative_ids = signal.get("narrative_ids", [])
            narratives = [narratives_by_id[nid] for nid in narrative_ids if nid in narratives_by_id]
            recent_articles = articles_by_entity.get(signal["entity"], [])

            all_enriched_signals.append({
                "entity": signal["entity"],
                "entity_type": signal["entity_type"],
                "signal_score": signal.get("score", 0.0),
                "velocity": signal.get("velocity", 0.0),
                "mentions": signal.get("mentions", 0),
                "source_count": signal.get("source_count", 0),
                "recency_factor": signal.get("recency_factor", 0.0),
                "sentiment": signal.get("sentiment", {}),
                "is_emerging": signal.get("is_emerging", False),
                "narratives": narratives,
                "recent_articles": recent_articles,
            })

        # Cache the FULL enriched list
        total_time = time.time() - start_time
        payload_size = len(json.dumps(all_enriched_signals)) / 1024
        logger.info(f"[Signals] Total request time: {total_time:.3f}s, Payload: {payload_size:.2f}KB")

        full_cache = {
            "signals": all_enriched_signals,
            "filters": {
                "min_score": min_score,
                "entity_type": entity_type,
                "timeframe": timeframe,
            },
            "computed_at": datetime.now().isoformat(),
            "performance": {
                "total_time_seconds": round(total_time, 3),
                "compute_time_seconds": round(compute_time, 3),
                "payload_size_kb": round(payload_size, 2),
            },
        }
        set_in_cache(cache_key, full_cache, ttl_seconds=60)

        # Return paginated slice
        page_signals = all_enriched_signals[offset:offset + limit]
        response = {
            "count": len(page_signals),
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total_count,
            "filters": {
                "min_score": min_score,
                "entity_type": entity_type,
                "timeframe": timeframe,
            },
            "signals": page_signals,
            "cached": False,
            "computed_at": full_cache["computed_at"],
            "performance": full_cache["performance"],
        }

        return response
```

---

## PART 2: Backend — Narratives Pagination

**IMPORTANT**: The `/active` endpoint does NOT call `get_active_narratives()` from `db/operations/narratives.py`. It has its own inline aggregation pipeline. All changes go in the API endpoint file. Do NOT modify `db/operations/narratives.py`.

### File: `src/crypto_news_aggregator/api/v1/endpoints/narratives.py`

#### 2A. Add PaginatedNarrativesResponse model

**Find** the end of the `NarrativeResponse` class (after the `json_schema_extra` block, around line 247):

```python
            }
        }


@router.get("/active", response_model=List[NarrativeResponse])
```

**Replace with**:

```python
            }
        }


class PaginatedNarrativesResponse(BaseModel):
    """Paginated response wrapper for narratives."""
    narratives: List[NarrativeResponse] = Field(..., description="Narratives for this page")
    total_count: int = Field(..., description="Total number of matching narratives")
    offset: int = Field(..., description="Current offset")
    limit: int = Field(..., description="Page size")
    has_more: bool = Field(..., description="Whether more pages are available")


@router.get("/active", response_model=PaginatedNarrativesResponse)
```

#### 2B. Add offset param to endpoint signature

**Find** (line 250-252):

```python
async def get_active_narratives_endpoint(
    limit: int = Query(50, ge=1, le=200, description="Maximum number of narratives to return"),
    lifecycle_state: Optional[str] = Query(None, description="Filter by lifecycle_state (emerging, hot, mature)")
):
```

**Replace with**:

```python
async def get_active_narratives_endpoint(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of narratives per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip for pagination"),
    lifecycle_state: Optional[str] = Query(None, description="Filter by lifecycle_state (emerging, hot, mature)")
):
```

> Default limit changed from 50 to 10 (one page of narratives). Added offset param.

#### 2C. Update cache key to exclude offset/limit

**Find** (line 270):

```python
    cache_key = f"narratives:active:{limit}:{lifecycle_state or 'all'}"
```

**Replace with**:

```python
    # Cache key excludes offset/limit — cache full set, paginate from cache
    cache_key = f"narratives:active:v2:{lifecycle_state or 'all'}"
```

#### 2D. Update cache hit to return paginated slice

**Find** (lines 272-278):

```python
    if cache_key in _narratives_cache:
        cached_data, cached_time = _narratives_cache[cache_key]
        if datetime.now() - cached_time < _narratives_cache_ttl:
            return cached_data
        else:
            # Remove expired entry
            del _narratives_cache[cache_key]
```

**Replace with**:

```python
    if cache_key in _narratives_cache:
        cached_data, cached_time = _narratives_cache[cache_key]
        if datetime.now() - cached_time < _narratives_cache_ttl:
            # Paginate from cached full list
            total_count = len(cached_data)
            page = cached_data[offset:offset + limit]
            return PaginatedNarrativesResponse(
                narratives=page,
                total_count=total_count,
                offset=offset,
                limit=limit,
                has_more=(offset + limit) < total_count,
            )
        else:
            # Remove expired entry
            del _narratives_cache[cache_key]
```

#### 2E. Change pipeline $limit to fetch full set for caching

**Find** in the aggregation pipeline (line 300):

```python
            {'$limit': limit},
```

**Replace with**:

```python
            {'$limit': 200},  # Fetch full set for caching; paginate in Python after
```

#### 2F. Update response construction and caching

**Find** (lines 445-451):

```python
        # Convert to response models
        response = [NarrativeResponse(**n) for n in response_data]
        
        # Store in cache with current timestamp (1-minute TTL)
        _narratives_cache[cache_key] = (response, datetime.now())
        
        return response
```

**Replace with**:

```python
        # Convert to response models
        all_narratives = [NarrativeResponse(**n) for n in response_data]
        
        # Cache the FULL list (1-minute TTL); pagination applied on retrieval
        _narratives_cache[cache_key] = (all_narratives, datetime.now())
        
        # Return paginated slice
        total_count = len(all_narratives)
        page = all_narratives[offset:offset + limit]
        return PaginatedNarrativesResponse(
            narratives=page,
            total_count=total_count,
            offset=offset,
            limit=limit,
            has_more=(offset + limit) < total_count,
        )
```

#### 2G. Update the empty-result early return

**Find** (lines 351-352):

```python
        if not narratives:
            return []
```

**Replace with**:

```python
        if not narratives:
            return PaginatedNarrativesResponse(
                narratives=[],
                total_count=0,
                offset=offset,
                limit=limit,
                has_more=False,
            )
```

#### 2H. Verify no other callers of get_active_narratives

Before finalizing, confirm no other code paths are affected:

```bash
grep -rn "get_active_narratives" src/ --include="*.py"
```

If it's only imported (but unused) in the API endpoint file, no action needed. If other files call it (e.g., briefing generation), those callers are unaffected since we're not changing the function.

---

## PART 3: Frontend — API Client Types and Functions

### File: `context-owl-ui/src/api/signals.ts`

**Replace entire file with**:

```typescript
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
};
```

### File: `context-owl-ui/src/api/narratives.ts`

**Find** the `getNarratives` method:

```typescript
  getNarratives: async (): Promise<NarrativesResponse> => {
    return apiClient.get<NarrativesResponse>('/api/v1/narratives/active');
  },
```

**Replace with**:

```typescript
  getNarratives: async (params?: { limit?: number; offset?: number }): Promise<PaginatedNarrativesResponse> => {
    return apiClient.get<PaginatedNarrativesResponse>('/api/v1/narratives/active', {
      limit: params?.limit ?? 10,
      offset: params?.offset ?? 0,
    });
  },
```

**Add this interface** at the top of the file (after existing imports/interfaces):

```typescript
export interface PaginatedNarrativesResponse {
  narratives: Narrative[];
  total_count: number;
  offset: number;
  limit: number;
  has_more: boolean;
}
```

---

## PART 4: Frontend — Shared Infinite Scroll Hook

### File: `context-owl-ui/src/hooks/useInfiniteScroll.ts` (NEW FILE)

```typescript
import { useEffect, useRef, useCallback } from 'react';

interface UseInfiniteScrollOptions {
  /** Whether more data is available */
  hasMore: boolean;
  /** Whether data is currently being fetched */
  isLoading: boolean;
  /** Callback to load next page */
  onLoadMore: () => void;
  /** Pixel threshold before bottom to trigger load (default 300) */
  threshold?: number;
}

/**
 * Intersection Observer-based infinite scroll hook.
 * Returns a ref to attach to a sentinel element at the bottom of the list.
 */
export function useInfiniteScroll({
  hasMore,
  isLoading,
  onLoadMore,
  threshold = 300,
}: UseInfiniteScrollOptions) {
  const sentinelRef = useRef<HTMLDivElement | null>(null);

  const handleIntersect = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const entry = entries[0];
      if (entry.isIntersecting && hasMore && !isLoading) {
        onLoadMore();
      }
    },
    [hasMore, isLoading, onLoadMore]
  );

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(handleIntersect, {
      rootMargin: `0px 0px ${threshold}px 0px`,
    });

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [handleIntersect, threshold]);

  return sentinelRef;
}
```

---

## PART 5: Frontend — Signals Page with Infinite Scroll

### File: `context-owl-ui/src/pages/Signals.tsx`

This is the biggest change. The page currently uses a single `useQuery` call. Replace it with `useInfiniteQuery` from `@tanstack/react-query`.

#### 5A. Update imports

**Find**:

```typescript
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
```

**Replace with**:

```typescript
import { useState, useCallback } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
```

#### 5B. Replace the query hook

**Find** the query block inside `Signals()`:

```typescript
  const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['signals'],
    queryFn: () => signalsAPI.getSignals({ limit: 50 }),
    refetchInterval: 30000, // 30 seconds
    staleTime: 0, // Always consider data stale
  });
```

**Replace with**:

```typescript
  const SIGNALS_PER_PAGE = 15;

  const {
    data,
    isLoading,
    error,
    refetch,
    dataUpdatedAt,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['signals'],
    queryFn: ({ pageParam = 0 }) =>
      signalsAPI.getSignals({ limit: SIGNALS_PER_PAGE, offset: pageParam }),
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.offset + lastPage.limit : undefined,
    initialPageParam: 0,
    refetchInterval: 30000,
    staleTime: 0,
  });

  // Flatten all pages into a single signals array
  const signals = data?.pages.flatMap((page) => page.signals) ?? [];
  const totalCount = data?.pages[0]?.total_count ?? 0;

  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const sentinelRef = useInfiniteScroll({
    hasMore: !!hasNextPage,
    isLoading: isFetchingNextPage,
    onLoadMore: loadMore,
  });
```

#### 5C. Update the rendering

**Find** the debug log block:

```typescript
  // Debug: Log the first signal to see if recent_articles is present
  if (data?.signals && data.signals.length > 0) {
    console.log('First signal data:', data.signals[0]);
    console.log('Has recent_articles?', 'recent_articles' in data.signals[0]);
    console.log('Recent articles count:', data.signals[0].recent_articles?.length);
  }
```

**Replace with** (or just delete it):

```typescript
  // Debug logging
  if (signals.length > 0) {
    console.log('First signal data:', signals[0]);
    console.log('Total signals:', totalCount, 'Loaded:', signals.length);
  }
```

**Find** the subtitle paragraph:

```typescript
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Top entities showing unusual activity in the last 24 hours
        </p>
```

**Replace with**:

```typescript
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Top entities showing unusual activity in the last 24 hours
          {totalCount > 0 && (
            <span className="text-sm text-gray-500 dark:text-gray-400 ml-2">
              ({signals.length} of {totalCount})
            </span>
          )}
        </p>
```

**Find** the grid mapping:

```typescript
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {data?.signals.map((signal, index) => {
```

**Replace with**:

```typescript
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {signals.map((signal, index) => {
```

**Find** the empty state check at the bottom:

```typescript
      {data?.signals.length === 0 && (
```

**Replace with**:

```typescript
      {/* Infinite scroll sentinel + loading indicator */}
      {signals.length > 0 && (
        <div ref={sentinelRef} className="flex justify-center py-8">
          {isFetchingNextPage && (
            <div className="text-sm text-gray-500 dark:text-gray-400">Loading more signals...</div>
          )}
          {!hasNextPage && signals.length >= SIGNALS_PER_PAGE && (
            <div className="text-sm text-gray-500 dark:text-gray-400">All signals loaded</div>
          )}
        </div>
      )}

      {signals.length === 0 && !isLoading && (
```

---

## PART 6: Frontend — Narratives Page with Infinite Scroll


> **Preserve existing behavior**: The Narratives page uses `useSearchParams` to read a `?highlight=` query parameter and scroll to a specific narrative. This code (the `highlightedNarrativeId` state and the `useEffect` that reads `searchParams`) must be kept as-is. The highlight feature will only work for narratives on the currently loaded pages. This is an acceptable limitation.

### File: `context-owl-ui/src/pages/Narratives.tsx`

#### 6A. Update imports

**Find**:

```typescript
import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
```

**Replace with**:

```typescript
import { useState, useEffect, useCallback } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
```

#### 6B. Replace the query hook

> **Note on API response shape change**: The current code does `result.length` because the API returns a raw array. The new API returns `{ narratives: [...], total_count, ... }`. The replacement below handles this correctly via `data?.pages.flatMap((page) => page.narratives)`. The `narrativesAPI.getNarratives` return type is updated in Part 3.

**Find**:

```typescript
  const { data, isLoading, error, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['narratives'],
    queryFn: async () => {
      const result = await narrativesAPI.getNarratives();
      console.log('[DEBUG] API returned:', result.length, 'narratives');
      return result;
    },
    refetchInterval: 60000, // 60 seconds
  });

  const narratives = data || [];
```

**Replace with**:

```typescript
  const NARRATIVES_PER_PAGE = 10;

  const {
    data,
    isLoading,
    error,
    refetch,
    dataUpdatedAt,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['narratives'],
    queryFn: ({ pageParam = 0 }) =>
      narrativesAPI.getNarratives({ limit: NARRATIVES_PER_PAGE, offset: pageParam }),
    getNextPageParam: (lastPage) =>
      lastPage.has_more ? lastPage.offset + lastPage.limit : undefined,
    initialPageParam: 0,
    refetchInterval: 60000,
  });

  // Flatten all pages into a single narratives array
  const narratives = data?.pages.flatMap((page) => page.narratives) ?? [];
  const totalCount = data?.pages[0]?.total_count ?? 0;

  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);

  const sentinelRef = useInfiniteScroll({
    hasMore: !!hasNextPage,
    isLoading: isFetchingNextPage,
    onLoadMore: loadMore,
  });
```

#### 6C. Add count display

**Find** the header subtitle:

```typescript
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Clustered stories and trending topics in the crypto space
        </p>
```

**Replace with**:

```typescript
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Clustered stories and trending topics in the crypto space
          {totalCount > 0 && (
            <span className="text-sm text-gray-500 dark:text-gray-400 ml-2">
              ({narratives.length} of {totalCount})
            </span>
          )}
        </p>
```

#### 6D. Add sentinel element before the empty state

**Find** the closing of the narratives list and empty state (around line 470-476):

```typescript
      </div>

      {narratives.length === 0 && (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400">No narratives detected yet</p>
        </div>
      )}
```

**Replace with**:

```typescript
      </div>

      {/* Infinite scroll sentinel + loading indicator */}
      {narratives.length > 0 && (
        <div ref={sentinelRef} className="flex justify-center py-8">
          {isFetchingNextPage && (
            <div className="text-sm text-gray-500 dark:text-gray-400">Loading more narratives...</div>
          )}
          {!hasNextPage && narratives.length >= NARRATIVES_PER_PAGE && (
            <div className="text-sm text-gray-500 dark:text-gray-400">All narratives loaded</div>
          )}
        </div>
      )}

      {narratives.length === 0 && !isLoading && (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400">No narratives detected yet</p>
        </div>
      )}
```

---

## PART 7: Types Update

### File: `context-owl-ui/src/types/index.ts` (or wherever types are defined)

Check if `SignalFilters` already has `offset`. If not, add it:

```typescript
export interface SignalFilters {
  limit?: number;
  offset?: number;
  min_score?: number;
  entity_type?: string;
  timeframe?: string;
}
```

Also check `NarrativesResponse` — it was previously likely `Narrative[]` (a raw array). The API now returns an object with `{ narratives, total_count, ... }`. Update accordingly or rely on the new `PaginatedNarrativesResponse` type defined in `narratives.ts`.

---

## Testing Checklist

After implementing, verify:

1. **Backend**:
   - `GET /api/v1/signals/trending` — returns `{ signals: [...15 items...], total_count: 50, has_more: true, offset: 0 }`
   - `GET /api/v1/signals/trending?offset=15` — returns next 15, `offset: 15`
   - `GET /api/v1/signals/trending?offset=45` — returns remaining items, `has_more: false`
   - Second request within 60s should be `cached: true`
   - `GET /api/v1/narratives/active` — same pagination shape
   - `GET /api/v1/narratives/active?offset=10` — returns next page

2. **Frontend**:
   - Signals page loads first 15 cards within 2-3 seconds
   - Scrolling to bottom triggers loading of next 15
   - "Loading more signals..." text appears during fetch
   - "All signals loaded" appears after last page
   - Counter shows "(15 of 50)" updating as more load
   - Narratives page same behavior with 10-item pages
   - Expanding a narrative's articles still works (existing pagination untouched)
   - `?highlight=` query param on narratives still works
   - No layout shifts when new items load

3. **Edge cases**:
   - Empty results (0 signals/narratives) — shows empty state, no sentinel
   - Single page of results — no "Loading more" triggers
   - Network error during infinite scroll — react-query handles retry
   - Stale cache with pagination — verify fresh data after 60s

---


## Files Changed Summary

| File | Change Type |
|------|-------------|
| `src/.../api/v1/endpoints/signals.py` | Modified — add offset param, paginate response, update cache |
| `src/.../api/v1/endpoints/narratives.py` | Modified — add PaginatedNarrativesResponse model, offset/limit params, paginate cache + response |
| `context-owl-ui/src/api/signals.ts` | Modified — new response type, add offset param |
| `context-owl-ui/src/api/narratives.ts` | Modified — new response type, add params |
| `context-owl-ui/src/hooks/useInfiniteScroll.ts` | **NEW** — shared infinite scroll hook |
| `context-owl-ui/src/pages/Signals.tsx` | Modified — useInfiniteQuery + sentinel |
| `context-owl-ui/src/pages/Narratives.tsx` | Modified — useInfiniteQuery + sentinel |
| `context-owl-ui/src/types/index.ts` | Modified — update SignalFilters, response types |

> **Note**: `db/operations/narratives.py` is NOT modified — the `/active` endpoint has its own inline pipeline.
