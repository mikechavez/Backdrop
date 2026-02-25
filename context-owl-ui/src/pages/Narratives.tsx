import { useState, useEffect } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { useSearchParams } from 'react-router-dom';
import { Sparkles, TrendingUp, Flame, Zap, Star, Wind, AlertCircle } from 'lucide-react';
import { narrativesAPI } from '../api';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { ErrorMessage } from '../components/ErrorMessage';
import { NarrativesSkeleton } from '../components/Skeleton';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import { formatRelativeTime, formatNumber } from '../lib/formatters';
import { cn } from '../lib/cn';
import { ArticleSkeleton } from '../components/ArticleSkeleton';

// Lifecycle configuration with icons, colors, and glow effects
const lifecycleConfig = {
  emerging: { icon: Sparkles, color: 'blue-400', glow: 'shadow-glow-blue', label: 'Emerging' },
  rising: { icon: TrendingUp, color: 'green-400', glow: 'shadow-glow-green', label: 'Rising' },
  hot: { icon: Flame, color: 'orange-400', glow: 'shadow-glow-orange', label: 'Hot' },
  heating: { icon: Zap, color: 'red-400', glow: 'shadow-glow-red', label: 'Heating' },
  mature: { icon: Star, color: 'purple-400', glow: 'shadow-glow-purple', label: 'Mature' },
  cooling: { icon: Wind, color: 'gray-400', glow: '', label: 'Cooling' },
} as const;

/**
 * Safely parse narrative date values to ISO string format
 */
const parseNarrativeDate = (dateValue: any): string => {
  if (!dateValue) return new Date().toISOString();
  if (dateValue instanceof Date) {
    return isNaN(dateValue.getTime()) ? new Date().toISOString() : dateValue.toISOString();
  }
  if (typeof dateValue === 'string') {
    const date = new Date(dateValue);
    if (!isNaN(date.getTime())) {
      return dateValue;
    }
  }
  try {
    const date = new Date(dateValue);
    return isNaN(date.getTime()) ? new Date().toISOString() : date.toISOString();
  } catch {
    return new Date().toISOString();
  }
};


interface PaginationState {
  offset: number;
  totalCount: number;
}

const NARRATIVES_PER_PAGE = 10;
const ARTICLES_PER_PAGE = 20;

export function Narratives() {
  const [searchParams] = useSearchParams();
  const [expandedArticles, setExpandedArticles] = useState<Set<number>>(new Set());
  const [narrativeArticles, setNarrativeArticles] = useState<Map<string, any[]>>(new Map());
  const [loadingArticles, setLoadingArticles] = useState<Set<string>>(new Set());
  const [loadingMore, setLoadingMore] = useState<Set<string>>(new Set());
  const [paginationState, setPaginationState] = useState<Map<string, PaginationState>>(new Map());
  const [loadErrors, setLoadErrors] = useState<Map<string, string>>(new Map());
  const [highlightedNarrativeId, setHighlightedNarrativeId] = useState<string | null>(null);

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
    queryKey: ['narratives'],
    queryFn: ({ pageParam = 0 }) => narrativesAPI.getNarratives({ offset: pageParam, limit: NARRATIVES_PER_PAGE }),
    getNextPageParam: (lastPage) => lastPage.has_more ? lastPage.offset + NARRATIVES_PER_PAGE : undefined,
    initialPageParam: 0,
    refetchInterval: 60000, // 60 seconds
    staleTime: 0, // Always consider data stale
  });

  const sentinelRef = useInfiniteScroll({
    hasMore: hasNextPage ?? false,
    isLoading: isFetchingNextPage,
    onLoadMore: () => fetchNextPage(),
    threshold: 300,
  });

  // Flatten pages array into single narratives array
  const narratives = data?.pages.flatMap((page) => page.narratives) ?? [];
  const totalCount = data?.pages[0]?.total_count ?? 0;

  // Handle highlight query parameter
  useEffect(() => {
    const highlightId = searchParams.get('highlight');
    if (highlightId) {
      setHighlightedNarrativeId(highlightId);

      // Find the index of the narrative with this ID and scroll to it
      const index = narratives.findIndex(n => n._id === highlightId);
      if (index >= 0) {
        setTimeout(() => {
          const element = document.getElementById(`narrative-${highlightId}`);
          if (element) {
            element.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }
        }, 100);
      }
    }
  }, [searchParams, narratives]);

  if (isLoading) return <NarrativesSkeleton />;
  if (error) return <ErrorMessage message={error.message} onRetry={() => refetch()} />;

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
          Active Narratives
        </h1>
        <p className="mt-2 text-gray-600 dark:text-gray-400">
          Clustered stories and trending topics in the crypto space
          {narratives.length > 0 && totalCount > 0 && (
            <span className="text-gray-500 dark:text-gray-400 ml-2">
              ({narratives.length} of {totalCount})
            </span>
          )}
        </p>
        {dataUpdatedAt && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-2">
            Last updated: {formatRelativeTime(parseNarrativeDate(dataUpdatedAt))}
          </p>
        )}
      </div>

      <div className="space-y-6">
        {narratives.map((narrative, index) => {
          // Handle both old and new field names for backward compatibility
          // Use title if it exists and is distinct from theme (not just entity name)
          // Otherwise fall back to a better display value
          const displayTitle = (() => {
            // Use title if it exists, isn't empty, and isn't just the theme/entity
            if (narrative.title && narrative.title.trim() && narrative.title !== narrative.theme) {
              return narrative.title;
            }
            // Fallback: Use first sentence of summary if available and concise
            if (narrative.summary) {
              const firstSentence = narrative.summary.split('.')[0] + '.';
              if (firstSentence.length > 0 && firstSentence.length < 100) {
                return firstSentence;
              }
            }
            // Last resort: use theme or entity name
            return narrative.title || narrative.theme || 'Untitled Narrative';
          })();
          const displaySummary = narrative.summary || narrative.story;
          const isExpanded = expandedArticles.has(index);
          const narrativeId = narrative._id || '';
          const articles = narrativeArticles.get(narrativeId) || narrative.articles || [];
          const isLoadingArticles = loadingArticles.has(narrativeId);
          
          const paginationInfo = paginationState.get(narrativeId);
          const totalArticles = paginationInfo?.totalCount || narrative.article_count || articles.length;
          const hasMore = articles.length < totalArticles;

          // Calculate progress indicator values
          const currentPage = Math.floor(articles.length / ARTICLES_PER_PAGE) + (articles.length % ARTICLES_PER_PAGE > 0 ? 1 : 0);
          const totalPages = Math.ceil(totalArticles / ARTICLES_PER_PAGE);
          
          const toggleExpanded = async () => {
            console.log('[DEBUG] Card clicked - Narrative ID:', narrativeId, 'Title:', displayTitle);
            const newExpanded = new Set(expandedArticles);
            if (newExpanded.has(index)) {
              console.log('[DEBUG] Collapsing card at index:', index);
              newExpanded.delete(index);
            } else {
              console.log('[DEBUG] Expanding card at index:', index);
              newExpanded.add(index);

              // Fetch articles if not already loaded
              if (narrativeId && !narrativeArticles.has(narrativeId) && !loadingArticles.has(narrativeId)) {
                console.log('[DEBUG] Fetching articles for narrative:', narrativeId);
                setLoadingArticles(prev => new Set(prev).add(narrativeId));

                // Clear any previous errors for this narrative
                setLoadErrors(prev => {
                  const next = new Map(prev);
                  next.delete(narrativeId);
                  return next;
                });

                try {
                  const response = await narrativesAPI.getArticlesPaginated(narrativeId, 0, ARTICLES_PER_PAGE);
                  console.log('[DEBUG] API Response:', response);
                  console.log('[DEBUG] Articles in response:', response.articles?.length || 0);
                  console.log('[DEBUG] Total count:', response.total_count);
                  setNarrativeArticles(prev => new Map(prev).set(narrativeId, response.articles || []));
                  setPaginationState(prev => new Map(prev).set(narrativeId, {
                    offset: response.offset + response.limit,
                    totalCount: response.total_count
                  }));
                } catch (error) {
                  console.error('[ERROR] Failed to fetch articles:', error);

                  // Set user-friendly error message
                  setLoadErrors(prev => new Map(prev).set(
                    narrativeId,
                    'Failed to load articles. Please try again.'
                  ));
                } finally {
                  setLoadingArticles(prev => {
                    const next = new Set(prev);
                    next.delete(narrativeId);
                    return next;
                  });
                }
              } else {
                console.log('[DEBUG] Skipping article fetch - narrativeId:', narrativeId, 'already has articles:', narrativeArticles.has(narrativeId));
              }
            }
            setExpandedArticles(newExpanded);
          };
          
          const loadMoreArticles = async () => {
            if (!narrativeId || !paginationInfo) return;

            const nextOffset = paginationInfo.offset;
            setLoadingMore(prev => new Set(prev).add(narrativeId));

            // Clear any previous errors for this narrative
            setLoadErrors(prev => {
              const next = new Map(prev);
              next.delete(narrativeId);
              return next;
            });

            try {
              const response = await narrativesAPI.getArticlesPaginated(narrativeId, nextOffset, ARTICLES_PER_PAGE);
              console.log('[DEBUG] Load more response:', response);

              // Append new articles to existing ones
              setNarrativeArticles(prev => {
                const existing = prev.get(narrativeId) || [];
                return new Map(prev).set(narrativeId, [...existing, ...response.articles]);
              });

              // Update pagination state with new offset
              setPaginationState(prev => new Map(prev).set(narrativeId, {
                offset: response.offset + response.limit,
                totalCount: response.total_count
              }));
            } catch (error) {
              console.error('[ERROR] Failed to load more articles:', error);

              // Set user-friendly error message
              setLoadErrors(prev => new Map(prev).set(
                narrativeId,
                'Failed to load more articles. Please try again.'
              ));
            } finally {
              setLoadingMore(prev => {
                const next = new Set(prev);
                next.delete(narrativeId);
                return next;
              });
            }
          };

          const retryLoadArticles = async () => {
            const articles = narrativeArticles.get(narrativeId) || [];

            // If no articles have been loaded yet, retry initial load
            if (articles.length === 0) {
              console.log('[DEBUG] Retrying initial load for narrative:', narrativeId);

              // Clear error before retry
              setLoadErrors(prev => {
                const next = new Map(prev);
                next.delete(narrativeId);
                return next;
              });

              setLoadingArticles(prev => new Set(prev).add(narrativeId));

              try {
                const response = await narrativesAPI.getArticlesPaginated(narrativeId, 0, ARTICLES_PER_PAGE);

                setNarrativeArticles(prev => new Map(prev).set(narrativeId, response.articles || []));
                setPaginationState(prev => new Map(prev).set(narrativeId, {
                  offset: response.offset + response.limit,
                  totalCount: response.total_count
                }));
              } catch (error) {
                console.error('[ERROR] Retry failed:', error);
                setLoadErrors(prev => new Map(prev).set(
                  narrativeId,
                  'Failed to load articles. Please try again.'
                ));
              } finally {
                setLoadingArticles(prev => {
                  const next = new Set(prev);
                  next.delete(narrativeId);
                  return next;
                });
              }
            } else {
              // If some articles are loaded, retry load more
              console.log('[DEBUG] Retrying load more for narrative:', narrativeId);
              await loadMoreArticles();
            }
          };

          const isHighlighted = highlightedNarrativeId === narrativeId;

          return (
          <Card
            key={`${narrative.theme}-${index}`}
            id={`narrative-${narrativeId}`}
            className={cn(isHighlighted && 'highlight-pulse')}
          >
            <div onClick={toggleExpanded}>
            <CardHeader>
              {/* Title and Lifecycle badge in same row */}
              <div className="flex items-start justify-between gap-3">
                <CardTitle>{displayTitle}</CardTitle>
                
                {/* Lifecycle badge */}
                {(() => {
                  const lifecycleValue = narrative.lifecycle_state || narrative.lifecycle;
                  const config = lifecycleValue && lifecycleConfig[lifecycleValue as keyof typeof lifecycleConfig];
                  if (!config) return null;
                  
                  const Icon = config.icon;
                  
                  // Define gradient styles for each lifecycle state
                  const gradientStyles: Record<string, string> = {
                    emerging: 'text-white bg-gradient-to-r from-blue-500 to-indigo-500 dark:from-blue-600 dark:to-indigo-600 shadow-sm',
                    rising: 'text-white bg-gradient-to-r from-green-500 to-emerald-500 dark:from-green-600 dark:to-emerald-600 shadow-sm',
                    hot: 'text-white bg-gradient-to-r from-orange-500 to-red-500 dark:from-orange-600 dark:to-red-600 shadow-sm',
                    heating: 'text-white bg-gradient-to-r from-red-500 to-pink-500 dark:from-red-600 dark:to-pink-600 shadow-sm',
                    mature: 'text-white bg-gradient-to-r from-purple-500 to-violet-500 dark:from-purple-600 dark:to-violet-600 shadow-sm',
                    cooling: 'text-white bg-gradient-to-r from-gray-500 to-slate-500 dark:from-gray-600 dark:to-slate-600 shadow-sm',
                  };
                  
                  const gradientClass = gradientStyles[lifecycleValue as string] || `text-${config.color} bg-${config.color}/10 dark:bg-${config.color}/20`;
                  
                  return (
                    <span className={cn(
                      'flex items-center gap-1.5 text-xs font-semibold px-2 py-1 rounded-full whitespace-nowrap',
                      gradientClass
                    )}>
                      <Icon className="w-3 h-3" />
                      {config.label}
                    </span>
                  );
                })()}
              </div>
            </CardHeader>
            <CardContent>
              {displaySummary && (
                <p className="text-gray-700 dark:text-gray-300 mb-4">{displaySummary}</p>
              )}
              
              {narrative.entities && narrative.entities.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-4">
                  {narrative.entities.map((entity, idx) => (
                    <span
                      key={idx}
                      className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 px-2 py-1 rounded text-sm"
                    >
                      {entity}
                    </span>
                  ))}
                </div>
              )}

              {/* Articles section */}
              {(narrative.article_count > 0 || articles.length > 0) && (
                <div className="pt-4 border-t border-gray-200 dark:border-dark-border">
                  <div className="flex items-center justify-between">
                    <div className="text-sm text-blue-600 dark:text-blue-400 font-medium flex items-center gap-1">
                      {isExpanded ? '▼' : '▶'} {formatNumber(narrative.article_count)} Articles
                    </div>

                    {/* Progress indicator and Showing X of Y Articles badge */}
                    {isExpanded && articles.length > 0 && (
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">
                          Page {currentPage} of {totalPages}
                        </span>
                        <span className="text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-2 py-1 rounded-full">
                          Showing {formatNumber(articles.length)} of {formatNumber(totalArticles)}
                        </span>
                      </div>
                    )}
                  </div>
                  
                  {isExpanded && (() => {
                    console.log('[DEBUG] Rendering expanded article section - isLoadingArticles:', isLoadingArticles, 'articles.length:', articles.length);
                    return (
                    <div className="mt-3 space-y-2">
                      {isLoadingArticles ? (
                        <div className="mt-3 space-y-2">
                          {[...Array(5)].map((_, i) => (
                            <ArticleSkeleton key={i} />
                          ))}
                        </div>
                      ) : articles.length > 0 ? (
                        <>
                          {articles.map((article, articleIdx) => {
                            console.log('[DEBUG] Rendering article:', articleIdx, article.title);
                            return (
                            <div key={articleIdx} className="text-sm bg-gray-50 dark:bg-dark-hover p-3 rounded">
                              <a
                                href={article.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:underline font-medium block mb-1"
                                onClick={(e) => e.stopPropagation()}
                              >
                                {article.title}
                              </a>
                              <div className="flex items-center gap-2 text-gray-500 dark:text-gray-400 text-xs">
                                <span className="capitalize">{article.source}</span>
                                <span>•</span>
                                <span>{formatRelativeTime(article.published_at)}</span>
                              </div>
                            </div>
                            );
                          })}

                          {/* Show skeleton loaders while loading more articles */}
                          {loadingMore.has(narrativeId) && (
                            <div className="mt-2 space-y-2">
                              {[...Array(5)].map((_, i) => (
                                <ArticleSkeleton key={`loading-${i}`} />
                              ))}
                            </div>
                          )}

                          {/* Load More button */}
                          {hasMore && (
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                loadMoreArticles();
                              }}
                              className="w-full mt-3 px-4 py-2 bg-blue-600 dark:bg-blue-700 hover:bg-blue-700 dark:hover:bg-blue-600 text-white text-sm font-medium rounded transition-colors"
                            >
                              Load More
                            </button>
                          )}

                          {/* Error message with retry */}
                          {loadErrors.has(narrativeId) && (
                            <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200
                                            dark:border-red-800 rounded-lg">
                              <div className="flex items-center justify-between gap-3">
                                <div className="flex items-start gap-2 flex-1">
                                  <AlertCircle className="w-4 h-4 text-red-600 dark:text-red-400 mt-0.5 flex-shrink-0" />
                                  <span className="text-sm text-red-700 dark:text-red-300">
                                    {loadErrors.get(narrativeId)}
                                  </span>
                                </div>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    retryLoadArticles();
                                  }}
                                  className="text-sm text-red-600 dark:text-red-400 hover:text-red-800
                                             dark:hover:text-red-300 font-medium hover:underline whitespace-nowrap"
                                >
                                  Retry
                                </button>
                              </div>
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                          No articles available
                        </div>
                      )}
                    </div>
                    );
                  })()}
                </div>
              )}
            </CardContent>
            </div>
          </Card>
          );
        })}
      </div>

      {/* Sentinel element for infinite scroll trigger */}
      {narratives.length > 0 && <div ref={sentinelRef} className="h-10" />}

      {/* Loading indicator for next page */}
      {isFetchingNextPage && (
        <div className="text-center py-8">
          <p className="text-gray-500 dark:text-gray-400">Loading more narratives...</p>
        </div>
      )}

      {/* All narratives loaded indicator */}
      {!hasNextPage && narratives.length > 0 && (
        <div className="text-center py-8">
          <p className="text-gray-500 dark:text-gray-400">All narratives loaded</p>
        </div>
      )}

      {/* Empty state */}
      {narratives.length === 0 && !isLoading && (
        <div className="text-center py-12">
          <p className="text-gray-500 dark:text-gray-400">No narratives detected yet</p>
        </div>
      )}
    </div>
  );
}
