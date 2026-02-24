/**
 * Skeleton loader components for all pages.
 * Uses Tailwind's animate-pulse to match the existing ArticleSkeleton convention.
 */

// ---------------------------------------------------------------------------
// Primitives
// ---------------------------------------------------------------------------

function SkeletonLine({ width = 'w-full', height = 'h-4' }: { width?: string; height?: string }) {
  return <div className={`${height} ${width} bg-gray-200 dark:bg-gray-700 rounded`} />;
}

function SkeletonBadge({ width = 'w-16' }: { width?: string }) {
  return <div className={`h-5 ${width} bg-gray-200 dark:bg-gray-700 rounded-full`} />;
}

function SkeletonBlock({ height = 'h-24' }: { height?: string }) {
  return <div className={`${height} w-full bg-gray-200 dark:bg-gray-700 rounded`} />;
}

// ---------------------------------------------------------------------------
// Briefing skeleton
// ---------------------------------------------------------------------------

export function BriefingSkeleton() {
  return (
    <div className="max-w-2xl mx-auto animate-pulse">
      {/* Header */}
      <div className="text-center mb-12 space-y-3">
        <SkeletonLine width="w-2/3 mx-auto" height="h-9" />
        <SkeletonLine width="w-1/3 mx-auto" height="h-5" />
      </div>

      <div className="border-t border-gray-200 dark:border-gray-700 mb-10" />

      {/* Narrative body — 4 paragraph blocks */}
      <div className="space-y-6 mb-12">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="space-y-2">
            <SkeletonLine width="w-full" />
            <SkeletonLine width="w-full" />
            <SkeletonLine width={i % 2 === 0 ? 'w-4/5' : 'w-3/4'} />
          </div>
        ))}
      </div>

      <div className="border-t border-gray-200 dark:border-gray-700 mb-10" />

      {/* Recommended Reading */}
      <div className="mb-12">
        <SkeletonLine width="w-40" height="h-3" />
        <div className="mt-4 divide-y divide-gray-100 dark:divide-gray-800">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="flex items-start gap-3 py-3">
              <div className="h-4 w-4 bg-gray-200 dark:bg-gray-700 rounded mt-0.5 shrink-0" />
              <div className="flex-1 space-y-1.5">
                <SkeletonLine width="w-3/4" />
                <SkeletonLine width="w-1/4" height="h-3" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Signals skeleton
// ---------------------------------------------------------------------------

function SignalCardSkeleton() {
  return (
    <div className="bg-white dark:bg-dark-card rounded-lg border border-gray-200 dark:border-dark-border p-5 space-y-4 animate-pulse">
      {/* Title row: rank + name + badge */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="h-5 w-6 bg-gray-200 dark:bg-gray-700 rounded" />
        <SkeletonLine width="w-28" height="h-5" />
        <SkeletonBadge width="w-20" />
      </div>
      {/* Rows */}
      {[...Array(3)].map((_, i) => (
        <div key={i} className="flex items-center justify-between">
          <SkeletonLine width="w-12" height="h-3" />
          <SkeletonBadge width={i === 0 ? 'w-16' : 'w-24'} />
        </div>
      ))}
    </div>
  );
}

export function SignalsSkeleton() {
  return (
    <div>
      {/* Page header */}
      <div className="mb-8 space-y-2 animate-pulse">
        <SkeletonLine width="w-48" height="h-9" />
        <SkeletonLine width="w-80" height="h-5" />
      </div>
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {[...Array(9)].map((_, i) => (
          <SignalCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Narratives skeleton
// ---------------------------------------------------------------------------

function NarrativeCardSkeleton() {
  return (
    <div className="bg-white dark:bg-dark-card rounded-lg border border-gray-200 dark:border-dark-border p-5 space-y-4 animate-pulse">
      {/* Title + lifecycle badge row */}
      <div className="flex items-start justify-between gap-3">
        <SkeletonLine width="w-2/3" height="h-5" />
        <SkeletonBadge width="w-20" />
      </div>
      {/* Summary lines */}
      <div className="space-y-2">
        <SkeletonLine />
        <SkeletonLine width="w-5/6" />
      </div>
      {/* Entity tags */}
      <div className="flex gap-2 flex-wrap">
        {[...Array(3)].map((_, i) => (
          <SkeletonBadge key={i} width="w-16" />
        ))}
      </div>
      {/* Article count row */}
      <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
        <SkeletonLine width="w-24" height="h-3" />
      </div>
    </div>
  );
}

export function NarrativesSkeleton() {
  return (
    <div>
      {/* Page header */}
      <div className="mb-8 space-y-2 animate-pulse">
        <SkeletonLine width="w-52" height="h-9" />
        <SkeletonLine width="w-72" height="h-5" />
      </div>
      <div className="space-y-6">
        {[...Array(5)].map((_, i) => (
          <NarrativeCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Articles skeleton
// ---------------------------------------------------------------------------

function ArticlesTableRowSkeleton() {
  return (
    <tr className="border-b border-gray-100 dark:border-dark-border">
      <td className="px-4 py-3">
        <SkeletonLine width="w-16" height="h-3" />
      </td>
      <td className="px-4 py-3">
        <div className="space-y-1.5">
          <SkeletonLine width="w-full" />
          <SkeletonLine width="w-3/4" />
        </div>
      </td>
      <td className="px-4 py-3">
        <SkeletonBadge width="w-20" />
      </td>
      <td className="px-4 py-3">
        <div className="flex gap-1">
          {[...Array(2)].map((_, i) => (
            <SkeletonBadge key={i} width="w-14" />
          ))}
        </div>
      </td>
    </tr>
  );
}

export function ArticlesSkeleton() {
  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="animate-pulse space-y-2">
        <SkeletonLine width="w-48" height="h-9" />
        <SkeletonLine width="w-64" height="h-5" />
      </div>

      <div className="bg-white dark:bg-dark-card rounded-lg border border-gray-200 dark:border-dark-border">
        {/* Card header */}
        <div className="p-5 border-b border-gray-200 dark:border-dark-border animate-pulse">
          <SkeletonLine width="w-28" height="h-5" />
        </div>
        <div className="p-5">
          <div className="overflow-x-auto animate-pulse">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-dark-border">
              <thead className="bg-gray-50 dark:bg-dark-card">
                <tr>
                  {['w-10', 'w-full', 'w-16', 'w-20'].map((w, i) => (
                    <th key={i} className="px-4 py-3">
                      <SkeletonLine width={w} height="h-3" />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-dark-bg">
                {[...Array(12)].map((_, i) => (
                  <ArticlesTableRowSkeleton key={i} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CostMonitor skeleton
// ---------------------------------------------------------------------------

export function CostMonitorSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <SkeletonLine width="w-72" height="h-9" />
          <SkeletonLine width="w-80" height="h-5" />
        </div>
        <div className="flex items-center gap-2">
          <SkeletonBadge width="w-28" />
          <div className="h-9 w-9 bg-gray-200 dark:bg-gray-700 rounded-lg" />
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-white dark:bg-dark-card rounded-lg border border-gray-200 dark:border-dark-border p-5">
            <div className="flex items-start justify-between">
              <div className="space-y-2 flex-1">
                <SkeletonLine width="w-28" height="h-3" />
                <SkeletonLine width="w-20" height="h-8" />
                <SkeletonLine width="w-24" height="h-3" />
              </div>
              <div className="h-12 w-12 bg-gray-200 dark:bg-gray-700 rounded-lg shrink-0 ml-3" />
            </div>
          </div>
        ))}
      </div>

      {/* Main content grid — chart + model breakdown */}
      <div className="grid gap-6 lg:grid-cols-2">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="bg-white dark:bg-dark-card rounded-lg border border-gray-200 dark:border-dark-border p-5 space-y-4">
            <SkeletonLine width="w-40" height="h-5" />
            <SkeletonBlock height="h-48" />
          </div>
        ))}
      </div>

      {/* Operations table */}
      <div className="bg-white dark:bg-dark-card rounded-lg border border-gray-200 dark:border-dark-border p-5 space-y-4">
        <SkeletonLine width="w-36" height="h-5" />
        <SkeletonBlock height="h-40" />
      </div>
    </div>
  );
}
