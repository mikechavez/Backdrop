import { useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { TrendingUp, ArrowUp, Activity, Minus, TrendingDown, Loader } from 'lucide-react';
import { signalsAPI } from '../api';
import type { ArticleLink } from '../types';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { ErrorMessage } from '../components/ErrorMessage';
import { SignalsSkeleton } from '../components/Skeleton';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { formatRelativeTime, formatEntityType, getEntityTypeColor } from '../lib/formatters';
import { cn } from '../lib/cn';

/**
 * Safely parse date values to ISO string format
 * Handles null, undefined, invalid dates, and various date formats
 */
const parseDateSafe = (dateValue: any): string => {
  // Handle null, undefined, or empty values
  if (!dateValue) return new Date().toISOString();
  
  // If it's already a Date object, convert to ISO string
  if (dateValue instanceof Date) {
    return isNaN(dateValue.getTime()) ? new Date().toISOString() : dateValue.toISOString();
  }
  
  // If it's a string, validate it can be parsed
  if (typeof dateValue === 'string') {
    // Return as-is if it's already a valid date string
    const date = new Date(dateValue);
    if (!isNaN(date.getTime())) {
      return dateValue;
    }
  }
  
  // Try to convert any other type to a date
  try {
    const date = new Date(dateValue);
    return isNaN(date.getTime()) ? new Date().toISOString() : date.toISOString();
  } catch {
    return new Date().toISOString();
  }
};

/**
 * Get velocity indicator based on velocity value
 * Returns icon component, label, and color classes for the badge
 * 
 * Velocity is a percentage (e.g., 1379 = 1379% growth = 13.79x increase)
 * Thresholds:
 * - Surging: >= 500 (500%+ growth, 5x or more - truly explosive)
 * - Rising: >= 200 (200%+ growth, 2x-5x - strong growth)
 * - Growing: >= 50 (50%+ growth, 1.5x-2x - moderate growth)
 * - Active: >= 0 (0-50% growth - steady)
 * - Declining: < 0 (negative growth - losing momentum)
 */
const getVelocityIndicator = (velocity: number): { icon: any; label: string; colorClass: string } => {
  if (velocity >= 500) {
    return { icon: TrendingUp, label: 'Surging', colorClass: 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300' };
  } else if (velocity >= 200) {
    return { icon: ArrowUp, label: 'Rising', colorClass: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300' };
  } else if (velocity >= 50) {
    return { icon: Activity, label: 'Growing', colorClass: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' };
  } else if (velocity >= 0) {
    return { icon: Minus, label: 'Active', colorClass: 'bg-gray-100 dark:bg-gray-700/30 text-gray-700 dark:text-gray-300' };
  } else {
    return { icon: TrendingDown, label: 'Declining', colorClass: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300' };
  }
};


const SIGNALS_PER_PAGE = 15;

export function Signals() {
  const [expandedArticles, setExpandedArticles] = useState<Set<number>>(new Set());
  const [articlesByEntity, setArticlesByEntity] = useState<Record<string, ArticleLink[]>>({});
  const [loadingArticles, setLoadingArticles] = useState<Set<string>>(new Set());

  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
    refetch,
    dataUpdatedAt
  } = useInfiniteQuery({
    queryKey: ['signals'],
    queryFn: ({ pageParam = 0 }) => signalsAPI.getSignals({ offset: pageParam, limit: SIGNALS_PER_PAGE }),
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.offset + SIGNALS_PER_PAGE : undefined,
    initialPageParam: 0,
    refetchInterval: 30000, // 30 seconds
    staleTime: 25000, // Consider fresh for 25 seconds (5s buffer before next refetchInterval)
    refetchOnWindowFocus: false, // Prevent refetch storms on tab focus
  });

  const sentinelRef = useInfiniteScroll({
    hasMore: hasNextPage ?? false,
    isLoading: isFetchingNextPage,
    onLoadMore: () => fetchNextPage(),
    threshold: 300,
  });

  const handleLoadArticles = async (entity: string) => {
    // If already loaded, don't fetch again
    if (articlesByEntity[entity] !== undefined) return;

    // If already loading, don't fetch again
    if (loadingArticles.has(entity)) return;

    setLoadingArticles(new Set(loadingArticles).add(entity));
    try {
      const response = await signalsAPI.getEntityArticles(entity);
      setArticlesByEntity(prev => ({
        ...prev,
        [entity]: response.articles,
      }));
    } catch (err) {
      console.error(`Failed to fetch articles for ${entity}:`, err);
      setArticlesByEntity(prev => ({
        ...prev,
        [entity]: [],
      }));
    } finally {
      const newLoading = new Set(loadingArticles);
      newLoading.delete(entity);
      setLoadingArticles(newLoading);
    }
  };

  if (isLoading) return <SignalsSkeleton />;
  if (error) return <ErrorMessage message={error.message} onRetry={() => refetch()} />;

  // Flatten pages array into single signals array
  const signals = data?.pages.flatMap((page) => page.signals) ?? [];

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Market Signals</h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Top entities showing unusual activity in the last 24 hours
        </p>
        {dataUpdatedAt && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
            Last updated: {formatRelativeTime(parseDateSafe(dataUpdatedAt))}
          </p>
        )}
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {signals.map((signal, index) => {
          const ticker = signal.entity.match(/\$[A-Z]+/)?.[0];
          const entityName = signal.entity.replace(/\$[A-Z]+/g, '').trim();

          const velocityIndicator = getVelocityIndicator(signal.velocity);

          return (
          <Card key={`${signal.entity}-${index}`}>
            <CardHeader>
              <CardTitle className="text-lg">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-blue-600 dark:text-blue-400 font-bold">#{index + 1}</span>
                  {/* TODO: Add Link to entity detail when endpoints ready */}
                  <span>{entityName}</span>
                  {ticker && <span className="text-gray-500 dark:text-gray-400">{ticker}</span>}
                  <span className={cn('flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full', velocityIndicator.colorClass)}>
                    {(() => {
                      const Icon = velocityIndicator.icon;
                      return <Icon className="w-3 h-3" />;
                    })()}
                    {velocityIndicator.label}
                  </span>
                </div>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500 dark:text-gray-400">Type:</span>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${getEntityTypeColor(signal.entity_type)}`}>
                    {formatEntityType(signal.entity_type)}
                  </span>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500 dark:text-gray-400">Last Updated:</span>
                  <span className="text-gray-700 dark:text-gray-300">
                    {formatRelativeTime(parseDateSafe(signal.last_updated))}
                  </span>
                </div>

                {/* Emerging badge */}
                {signal.is_emerging && (
                  <div className="mt-3 pt-3 border-t border-gray-200 dark:border-dark-border">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-medium text-yellow-700 dark:text-yellow-300 bg-yellow-100 dark:bg-yellow-900/30 px-2 py-1 rounded-full">
                        🆕 Emerging
                      </span>
                      <span className="text-xs text-gray-500 dark:text-gray-400">Not yet part of any narrative</span>
                    </div>
                  </div>
                )}

                {/* Recent articles section with lazy-loading */}
                <div className="mt-3 pt-3 border-t border-gray-200 dark:border-dark-border">
                  <button
                    onClick={async () => {
                      const newExpanded = new Set(expandedArticles);
                      const isCurrentlyExpanded = newExpanded.has(index);

                      if (isCurrentlyExpanded) {
                        newExpanded.delete(index);
                      } else {
                        newExpanded.add(index);
                        // Fetch articles if not already loaded
                        if (articlesByEntity[signal.entity] === undefined) {
                          await handleLoadArticles(signal.entity);
                        }
                      }
                      setExpandedArticles(newExpanded);
                    }}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 font-medium flex items-center gap-1"
                  >
                    {expandedArticles.has(index) ? '▼' : '▶'} Recent mentions
                  </button>

                  {expandedArticles.has(index) && (
                    <div className="mt-2 space-y-2">
                      {loadingArticles.has(signal.entity) ? (
                        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 py-2">
                          <Loader className="w-3 h-3 animate-spin" />
                          Loading articles...
                        </div>
                      ) : articlesByEntity[signal.entity] && articlesByEntity[signal.entity].length > 0 ? (
                        articlesByEntity[signal.entity].map((article, articleIdx) => (
                          <div key={articleIdx} className="text-xs bg-gray-50 dark:bg-dark-hover p-2 rounded">
                            <a
                              href={article.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:underline font-medium block mb-1"
                            >
                              {article.title}
                            </a>
                            <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400">
                              <span className="capitalize">{article.source}</span>
                              <span>•</span>
                              <span>{formatRelativeTime(article.published_at)}</span>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p className="text-xs text-gray-500 dark:text-gray-400 py-2">No articles found</p>
                      )}
                    </div>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
          );
        })}
      </div>

      {/* Sentinel element for infinite scroll trigger */}
      {signals.length > 0 && <div ref={sentinelRef} className="h-10" />}

      {/* Loading indicator for next page */}
      {isFetchingNextPage && (
        <div className="text-center py-8">
          <p className="text-gray-500 dark:text-gray-400">Loading more signals...</p>
        </div>
      )}

      {/* All signals loaded indicator */}
      {!hasNextPage && signals.length > 0 && (
        <div className="text-center py-8">
          <p className="text-gray-500 dark:text-gray-400">All signals loaded</p>
        </div>
      )}

      {/* Empty state */}
      {signals.length === 0 && !isLoading && (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400">No signals detected yet</p>
        </div>
      )}
    </div>
  );
}
