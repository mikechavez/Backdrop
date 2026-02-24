import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  DollarSign, 
  TrendingUp, 
  Database, 
  RefreshCw,
  AlertTriangle,
  CheckCircle,
  Zap,
  Brain,
  Trash2
} from 'lucide-react';
import { motion } from 'framer-motion';
import { adminAPI } from '../api';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { ErrorMessage } from '../components/ErrorMessage';
import { CostMonitorSkeleton } from '../components/Skeleton';
import { CostAlert } from '../components/CostAlert';
import { cn } from '../lib/cn';

// Original monthly cost before optimization
const ORIGINAL_MONTHLY_COST = 92;

/**
 * Stat card component for displaying key metrics
 */
interface StatCardProps {
  title: string;
  value: string;
  subtitle?: React.ReactNode;
  icon: React.ElementType;
  iconColor: string;
  trend?: 'up' | 'down' | 'neutral';
  trendValue?: string;
}

function StatCard({ title, value, subtitle, icon: Icon, iconColor, trend, trendValue }: StatCardProps) {
  return (
    <Card className="relative overflow-hidden">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500 dark:text-gray-400">{title}</p>
          <p className="mt-2 text-3xl font-bold text-gray-900 dark:text-gray-100">{value}</p>
          {subtitle && (
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
          )}
          {trend && trendValue && (
            <div className={cn(
              'mt-2 inline-flex items-center text-sm font-medium',
              trend === 'up' ? 'text-green-600 dark:text-green-400' : 
              trend === 'down' ? 'text-red-600 dark:text-red-400' : 
              'text-gray-600 dark:text-gray-400'
            )}>
              {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'} {trendValue}
            </div>
          )}
        </div>
        <div className={cn('p-3 rounded-lg', iconColor)}>
          <Icon className="w-6 h-6 text-white" />
        </div>
      </div>
    </Card>
  );
}

/**
 * Progress bar component for visualizing percentages
 */
interface ProgressBarProps {
  value: number;
  max?: number;
  color?: string;
  showLabel?: boolean;
  label?: string;
}

function ProgressBar({ value, max = 100, color = 'bg-blue-500', showLabel = true, label }: ProgressBarProps) {
  const percentage = Math.min((value / max) * 100, 100);
  
  return (
    <div className="w-full">
      {showLabel && (
        <div className="flex justify-between text-sm mb-1">
          <span className="text-gray-600 dark:text-gray-400">{label}</span>
          <span className="font-medium text-gray-900 dark:text-gray-100">{percentage.toFixed(1)}%</span>
        </div>
      )}
      <div className="h-2 bg-gray-200 dark:bg-dark-border rounded-full overflow-hidden">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className={cn('h-full rounded-full', color)}
        />
      </div>
    </div>
  );
}

/**
 * Daily cost bar chart
 */
interface DailyCostBarProps {
  date: string;
  cost: number;
  maxCost: number;
  cacheHitRate: number;
}

function DailyCostBar({ date, cost, maxCost, cacheHitRate }: DailyCostBarProps) {
  const percentage = maxCost > 0 ? (cost / maxCost) * 100 : 0;
  const formattedDate = new Date(date).toLocaleDateString('en-US', { 
    month: 'short', 
    day: 'numeric' 
  });
  
  return (
    <div className="flex items-center gap-4 py-2">
      <span className="w-16 text-sm text-gray-600 dark:text-gray-400 shrink-0">
        {formattedDate}
      </span>
      <div className="flex-1 h-6 bg-gray-100 dark:bg-dark-border rounded-full overflow-hidden relative">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${percentage}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className="h-full bg-gradient-to-r from-blue-500 to-purple-500 rounded-full"
        />
        <span className="absolute inset-0 flex items-center justify-center text-xs font-medium text-gray-700 dark:text-gray-300">
          ${cost.toFixed(2)}
        </span>
      </div>
      <span className="w-16 text-sm text-gray-500 dark:text-gray-400 text-right shrink-0">
        {cacheHitRate.toFixed(0)}% hit
      </span>
    </div>
  );
}

/**
 * Processing distribution bar for source breakdown
 */
interface ProcessingBarProps {
  source: string;
  llmPercentage: number;
  llmCount: number;
  regexCount: number;
}

function ProcessingBar({ source, llmPercentage, llmCount, regexCount }: ProcessingBarProps) {
  return (
    <div className="py-2">
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium text-gray-700 dark:text-gray-300 capitalize">{source}</span>
        <span className="text-gray-500 dark:text-gray-400">
          {llmCount} LLM / {regexCount} Regex
        </span>
      </div>
      <div className="h-3 bg-gray-100 dark:bg-dark-border rounded-full overflow-hidden flex">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${llmPercentage}%` }}
          transition={{ duration: 0.5, ease: 'easeOut' }}
          className="h-full bg-purple-500"
          title={`LLM: ${llmPercentage.toFixed(1)}%`}
        />
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${100 - llmPercentage}%` }}
          transition={{ duration: 0.5, ease: 'easeOut', delay: 0.1 }}
          className="h-full bg-green-500"
          title={`Regex: ${(100 - llmPercentage).toFixed(1)}%`}
        />
      </div>
    </div>
  );
}

export function CostMonitor() {
  const queryClient = useQueryClient();
  const [dailyDays, setDailyDays] = useState(7);
  
  // Fetch cost summary
  const { 
    data: summary, 
    isLoading: summaryLoading, 
    error: summaryError,
    refetch: refetchSummary 
  } = useQuery({
    queryKey: ['costSummary'],
    queryFn: () => adminAPI.getCostSummary(),
    refetchInterval: 60000, // 1 minute
  });

  // Fetch daily costs
  const { 
    data: dailyCosts, 
    isLoading: dailyLoading,
    error: dailyError 
  } = useQuery({
    queryKey: ['dailyCosts', dailyDays],
    queryFn: () => adminAPI.getDailyCosts(dailyDays),
    refetchInterval: 300000, // 5 minutes
  });

  // Fetch model breakdown
  const { 
    data: modelCosts, 
    isLoading: modelLoading,
    error: modelError 
  } = useQuery({
    queryKey: ['modelCosts'],
    queryFn: () => adminAPI.getCostsByModel(30),
    refetchInterval: 300000, // 5 minutes
  });

  // Fetch cache stats
  const { 
    data: cacheStats, 
    isLoading: cacheLoading,
    error: cacheError 
  } = useQuery({
    queryKey: ['cacheStats'],
    queryFn: () => adminAPI.getCacheStats(),
    refetchInterval: 60000, // 1 minute
  });

  // Fetch processing stats
  const { 
    data: processingStats, 
    isLoading: processingLoading,
    error: processingError 
  } = useQuery({
    queryKey: ['processingStats'],
    queryFn: () => adminAPI.getProcessingStats(7),
    refetchInterval: 300000, // 5 minutes
  });

  // Clear expired cache mutation
  const clearCacheMutation = useMutation({
    mutationFn: () => adminAPI.clearExpiredCache(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cacheStats'] });
    },
  });

  // Loading state
  const isLoading = summaryLoading || dailyLoading || modelLoading || cacheLoading || processingLoading;
  
  // Error handling
  const error = summaryError || dailyError || modelError || cacheError || processingError;
  
  if (isLoading && !summary) return <CostMonitorSkeleton />;
  if (error) return <ErrorMessage message={(error as Error).message} onRetry={() => refetchSummary()} />;

  // Calculate savings
  const savings = ORIGINAL_MONTHLY_COST - (summary?.projected_monthly || 0);
  const savingsPercent = ((savings / ORIGINAL_MONTHLY_COST) * 100).toFixed(0);

  // Get max daily cost for bar scaling
  const maxDailyCost = dailyCosts?.daily_costs.reduce(
    (max, day) => Math.max(max, day.total_cost), 
    0
  ) || 1;

  // Get projected monthly color
  const getProjectedColor = (projected: number) => {
    if (projected < 10) return 'text-green-600 dark:text-green-400';
    if (projected < 15) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-600 dark:text-red-400';
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">
            Cost Monitoring Dashboard
          </h1>
          <p className="mt-2 text-gray-600 dark:text-gray-400">
            Real-time LLM API costs and optimization metrics
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className={cn(
            'px-3 py-1 rounded-full text-sm font-medium',
            (summary?.projected_monthly || 0) < 10 
              ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
              : 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300'
          )}>
            Target: &lt;$10/mo
          </span>
          <button
            onClick={() => {
              queryClient.invalidateQueries({ queryKey: ['costSummary'] });
              queryClient.invalidateQueries({ queryKey: ['dailyCosts'] });
              queryClient.invalidateQueries({ queryKey: ['modelCosts'] });
              queryClient.invalidateQueries({ queryKey: ['cacheStats'] });
              queryClient.invalidateQueries({ queryKey: ['processingStats'] });
            }}
            className="p-2 rounded-lg bg-gray-100 dark:bg-dark-hover hover:bg-gray-200 dark:hover:bg-dark-border transition-colors"
            title="Refresh all data"
          >
            <RefreshCw className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </button>
        </div>
      </div>

      {/* Cost Alert Banner */}
      {summary && (
        <CostAlert
          dailyCost={dailyCosts?.daily_costs?.[dailyCosts.daily_costs.length - 1]?.total_cost || 0}
          projectedMonthly={summary.projected_monthly || 0}
          target={10}
        />
      )}

      {/* Stat Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Month to Date"
          value={`$${summary?.month_to_date.toFixed(2) || '0.00'}`}
          subtitle={`${summary?.days_elapsed || 0} days elapsed`}
          icon={DollarSign}
          iconColor="bg-blue-500"
        />
        <StatCard
          title="Projected Monthly"
          value={`$${summary?.projected_monthly.toFixed(2) || '0.00'}`}
          subtitle={
            <span className={getProjectedColor(summary?.projected_monthly || 0)}>
              {(summary?.projected_monthly || 0) < 10 ? '✓ Under target' : '⚠ Above target'}
            </span>
          }
          icon={TrendingUp}
          iconColor={(summary?.projected_monthly || 0) < 10 ? 'bg-green-500' : 'bg-yellow-500'}
        />
        <StatCard
          title="Monthly Savings"
          value={`$${savings.toFixed(2)}`}
          subtitle={`${savingsPercent}% reduction from $${ORIGINAL_MONTHLY_COST}/mo`}
          icon={CheckCircle}
          iconColor="bg-emerald-500"
          trend="up"
          trendValue={`${savingsPercent}% saved`}
        />
        <StatCard
          title="Cache Hit Rate"
          value={`${summary?.cache_hit_rate_percent.toFixed(1) || '0'}%`}
          subtitle={`${summary?.cached_calls || 0} / ${summary?.total_calls || 0} calls`}
          icon={Database}
          iconColor={(summary?.cache_hit_rate_percent || 0) >= 40 ? 'bg-purple-500' : 'bg-orange-500'}
        />
      </div>

      {/* Main Content Grid */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Daily Cost Trend */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Daily Cost Trend</CardTitle>
              <select
                value={dailyDays}
                onChange={(e) => setDailyDays(Number(e.target.value))}
                className="px-3 py-1 text-sm border border-gray-300 dark:border-dark-border rounded-lg bg-white dark:bg-dark-card text-gray-700 dark:text-gray-300 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value={7}>Last 7 days</option>
                <option value={14}>Last 14 days</option>
                <option value={30}>Last 30 days</option>
              </select>
            </div>
          </CardHeader>
          <CardContent>
            {dailyCosts?.daily_costs.length === 0 ? (
              <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                No cost data available yet
              </p>
            ) : (
              <div className="space-y-1">
                {dailyCosts?.daily_costs.map((day) => (
                  <DailyCostBar
                    key={day.date}
                    date={day.date}
                    cost={day.total_cost}
                    maxCost={maxDailyCost}
                    cacheHitRate={day.cache_hit_rate}
                  />
                ))}
                <div className="pt-4 border-t border-gray-200 dark:border-dark-border mt-4">
                  <div className="flex justify-between text-sm font-medium">
                    <span className="text-gray-600 dark:text-gray-400">Period Total</span>
                    <span className="text-gray-900 dark:text-gray-100">
                      ${dailyCosts?.total_cost.toFixed(2) || '0.00'}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Cost by Model */}
        <Card>
          <CardHeader>
            <CardTitle>Cost by Model</CardTitle>
          </CardHeader>
          <CardContent>
            {modelCosts?.models.length === 0 ? (
              <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                No model data available yet
              </p>
            ) : (
              <div className="space-y-4">
                {modelCosts?.models.map((model) => {
                  const isHaiku = model.model?.toLowerCase().includes('haiku');
                  const isSonnet = model.model?.toLowerCase().includes('sonnet');
                  
                  return (
                    <div 
                      key={model.model} 
                      className="p-4 bg-gray-50 dark:bg-dark-hover rounded-lg"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          {isHaiku ? (
                            <Zap className="w-5 h-5 text-yellow-500" />
                          ) : isSonnet ? (
                            <Brain className="w-5 h-5 text-purple-500" />
                          ) : (
                            <Database className="w-5 h-5 text-gray-500" />
                          )}
                          <span className="font-medium text-gray-900 dark:text-gray-100">
                            {isHaiku ? '🏃 Haiku' : isSonnet ? '🧠 Sonnet' : model.model || 'Unknown'}
                          </span>
                        </div>
                        <span className="text-lg font-bold text-gray-900 dark:text-gray-100">
                          ${model.total_cost.toFixed(2)}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-2 text-sm text-gray-600 dark:text-gray-400">
                        <div>Calls: {model.total_calls.toLocaleString()}</div>
                        <div>Cache: {model.cache_hit_rate_percent.toFixed(1)}%</div>
                        <div>Input: {(model.input_tokens / 1000).toFixed(1)}k tokens</div>
                        <div>Output: {(model.output_tokens / 1000).toFixed(1)}k tokens</div>
                      </div>
                    </div>
                  );
                })}
                <div className="pt-4 border-t border-gray-200 dark:border-dark-border">
                  <div className="flex justify-between text-sm font-medium">
                    <span className="text-gray-600 dark:text-gray-400">Total (30 days)</span>
                    <span className="text-gray-900 dark:text-gray-100">
                      ${modelCosts?.total_cost.toFixed(2) || '0.00'}
                    </span>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Cache Performance */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Cache Performance</CardTitle>
              <button
                onClick={() => clearCacheMutation.mutate()}
                disabled={clearCacheMutation.isPending || (cacheStats?.cache_entries.expired || 0) === 0}
                className={cn(
                  'flex items-center gap-1 px-3 py-1 text-sm rounded-lg transition-colors',
                  clearCacheMutation.isPending || (cacheStats?.cache_entries.expired || 0) === 0
                    ? 'bg-gray-100 dark:bg-dark-border text-gray-400 cursor-not-allowed'
                    : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50'
                )}
              >
                <Trash2 className="w-4 h-4" />
                Clear Expired
              </button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="space-y-6">
              {/* Hit Rate Gauge */}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-gray-600 dark:text-gray-400">
                    Hit Rate
                  </span>
                  <span className={cn(
                    'text-2xl font-bold',
                    (cacheStats?.performance.hit_rate_percent || 0) >= 40 
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-orange-600 dark:text-orange-400'
                  )}>
                    {cacheStats?.performance.hit_rate_percent.toFixed(1) || '0'}%
                  </span>
                </div>
                <ProgressBar
                  value={cacheStats?.performance.hit_rate_percent || 0}
                  color={(cacheStats?.performance.hit_rate_percent || 0) >= 40 ? 'bg-green-500' : 'bg-orange-500'}
                  showLabel={false}
                />
                {(cacheStats?.performance.hit_rate_percent || 0) < 40 && (
                  <div className="flex items-center gap-2 mt-2 text-sm text-orange-600 dark:text-orange-400">
                    <AlertTriangle className="w-4 h-4" />
                    <span>Hit rate below 40% - consider increasing cache TTL</span>
                  </div>
                )}
              </div>

              {/* Cache Stats Grid */}
              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-gray-50 dark:bg-dark-hover rounded-lg">
                  <div className="text-sm text-gray-500 dark:text-gray-400">Active Entries</div>
                  <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
                    {cacheStats?.cache_entries.active.toLocaleString() || 0}
                  </div>
                </div>
                <div className="p-3 bg-gray-50 dark:bg-dark-hover rounded-lg">
                  <div className="text-sm text-gray-500 dark:text-gray-400">Expired Entries</div>
                  <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
                    {cacheStats?.cache_entries.expired.toLocaleString() || 0}
                  </div>
                </div>
                <div className="p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                  <div className="text-sm text-green-600 dark:text-green-400">Cache Hits</div>
                  <div className="text-xl font-bold text-green-700 dark:text-green-300">
                    {cacheStats?.performance.cache_hits.toLocaleString() || 0}
                  </div>
                </div>
                <div className="p-3 bg-red-50 dark:bg-red-900/20 rounded-lg">
                  <div className="text-sm text-red-600 dark:text-red-400">Cache Misses</div>
                  <div className="text-xl font-bold text-red-700 dark:text-red-300">
                    {cacheStats?.performance.cache_misses.toLocaleString() || 0}
                  </div>
                </div>
              </div>

              {clearCacheMutation.isSuccess && (
                <div className="flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
                  <CheckCircle className="w-4 h-4" />
                  <span>{clearCacheMutation.data?.message}</span>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Processing Distribution */}
        <Card>
          <CardHeader>
            <CardTitle>Processing Distribution</CardTitle>
          </CardHeader>
          <CardContent>
            {processingStats?.sources.length === 0 ? (
              <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                No processing data available yet
              </p>
            ) : (
              <div className="space-y-4">
                {/* Summary */}
                <div className="grid grid-cols-3 gap-4 p-4 bg-gray-50 dark:bg-dark-hover rounded-lg">
                  <div className="text-center">
                    <div className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                      {processingStats?.summary.total_articles.toLocaleString() || 0}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">Total Articles</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                      {processingStats?.summary.total_llm_extractions.toLocaleString() || 0}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">LLM Extractions</div>
                  </div>
                  <div className="text-center">
                    <div className="text-2xl font-bold text-green-600 dark:text-green-400">
                      {processingStats?.summary.total_simple_extractions.toLocaleString() || 0}
                    </div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">Regex Extractions</div>
                  </div>
                </div>

                {/* Legend */}
                <div className="flex items-center gap-4 text-sm">
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-purple-500 rounded" />
                    <span className="text-gray-600 dark:text-gray-400">LLM (Haiku)</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-3 h-3 bg-green-500 rounded" />
                    <span className="text-gray-600 dark:text-gray-400">Regex (Free)</span>
                  </div>
                </div>

                {/* Source Breakdown */}
                <div className="space-y-2">
                  {processingStats?.sources.slice(0, 10).map((source) => (
                    <ProcessingBar
                      key={source.source}
                      source={source.source}
                      llmPercentage={source.llm_percentage}
                      llmCount={source.llm_extractions}
                      regexCount={source.simple_extractions}
                    />
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Cost by Operation */}
      <Card>
        <CardHeader>
          <CardTitle>Cost by Operation</CardTitle>
        </CardHeader>
        <CardContent>
          {!summary?.breakdown_by_operation || Object.keys(summary.breakdown_by_operation).length === 0 ? (
            <p className="text-gray-500 dark:text-gray-400 text-center py-8">
              No operation data available yet
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-gray-200 dark:border-dark-border">
                    <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Operation
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Cost
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Calls
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Cached
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Input Tokens
                    </th>
                    <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">
                      Output Tokens
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(summary.breakdown_by_operation).map(([operation, data]) => (
                    <tr 
                      key={operation}
                      className="border-b border-gray-100 dark:border-dark-border hover:bg-gray-50 dark:hover:bg-dark-hover"
                    >
                      <td className="py-3 px-4">
                        <span className="font-medium text-gray-900 dark:text-gray-100 capitalize">
                          {operation.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right font-mono text-gray-900 dark:text-gray-100">
                        ${data.cost.toFixed(4)}
                      </td>
                      <td className="py-3 px-4 text-right text-gray-700 dark:text-gray-300">
                        {data.calls.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right text-gray-700 dark:text-gray-300">
                        {data.cached_calls.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right text-gray-700 dark:text-gray-300">
                        {data.input_tokens.toLocaleString()}
                      </td>
                      <td className="py-3 px-4 text-right text-gray-700 dark:text-gray-300">
                        {data.output_tokens.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
