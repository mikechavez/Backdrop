import { useQuery } from '@tanstack/react-query';
import { ExternalLink } from 'lucide-react';
import { articlesAPI } from '../api';
import { Card, CardHeader, CardTitle, CardContent } from '../components/Card';
import { ErrorMessage } from '../components/ErrorMessage';
import { ArticlesSkeleton } from '../components/Skeleton';
import { formatRelativeTime, getEntityTypeColor } from '../lib/formatters';

const getSourceColor = (source: string): string => {
  const sourceColors: Record<string, string> = {
    twitter: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300',
    telegram: 'bg-cyan-100 dark:bg-cyan-900/30 text-cyan-700 dark:text-cyan-300',
    rss: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300',
    coindesk: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300',
    cointelegraph: 'bg-pink-100 dark:bg-pink-900/30 text-pink-700 dark:text-pink-300',
    decrypt: 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300',
    bitcoinmagazine: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300',
  };
  return sourceColors[source.toLowerCase()] || 'bg-gray-100 dark:bg-gray-700/30 text-gray-700 dark:text-gray-300';
};

export function Articles() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['articles', 'recent'],
    queryFn: () => articlesAPI.getRecent(100),
    refetchInterval: 60000, // Refetch every minute
  });

  if (isLoading) {
    return <ArticlesSkeleton />;
  }

  if (error) {
    return <ErrorMessage message={error instanceof Error ? error.message : 'Failed to load articles'} />;
  }

  const articles = data?.articles || [];

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <div>
          <h1 className="text-3xl font-bold text-gray-900 dark:text-gray-100">Recent Articles</h1>
          <p className="text-gray-600 dark:text-gray-400 mt-1">
            Last {articles.length} articles in chronological order
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Article Feed</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-dark-border">
              <thead className="bg-gray-50 dark:bg-dark-card">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Time
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Title
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Source
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Entities
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-dark-bg divide-y divide-gray-200 dark:divide-dark-border">
                {articles.map((article) => (
                  <tr key={article.id} className="hover:bg-gray-50 dark:hover:bg-dark-hover">
                    <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {formatRelativeTime(article.published_at)}
                    </td>
                    <td className="px-4 py-3 text-sm">
                      <a
                        href={article.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 hover:underline flex items-center gap-1 group"
                      >
                        <span className="line-clamp-2">{article.title}</span>
                        <ExternalLink className="w-4 h-4 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity" />
                      </a>
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getSourceColor(article.source)}`}>
                        {article.source}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-1">
                        {article.entities.slice(0, 3).map((entity, idx) => (
                          <span
                            key={idx}
                            className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getEntityTypeColor(entity.type)}`}
                          >
                            {entity.name}
                          </span>
                        ))}
                        {article.entities.length > 3 && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-gray-700/30 text-gray-600 dark:text-gray-400">
                            +{article.entities.length - 3} more
                          </span>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {articles.length === 0 && (
            <div className="text-center py-12 text-gray-500 dark:text-gray-400">
              No articles found
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
