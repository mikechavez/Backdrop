import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { briefingAPI } from '../api';
import { ErrorMessage } from '../components/ErrorMessage';
import { BriefingSkeleton } from '../components/Skeleton';
import { formatTheme } from '../lib/formatters';
import type { Briefing as BriefingType, BriefingRecommendation } from '../types';

/**
 * Format the briefing date for display
 * e.g., "Thursday, December 26, 2025"
 */
function formatBriefingDate(dateString: string): string {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}

/**
 * Format the briefing time for display
 * e.g., "8:00 AM EST"
 */
function formatBriefingTime(dateString: string): string {
  const date = new Date(dateString);
  return new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(date);
}

/**
 * Get the greeting based on briefing type
 */
function getBriefingTitle(type: 'morning' | 'evening'): string {
  return type === 'morning'
    ? 'Your Morning Crypto Briefing'
    : 'Your Evening Crypto Briefing';
}

/**
 * Format the next briefing time for display
 * e.g., "Today at 8:00 PM EST" or "Tomorrow at 8:00 AM EST"
 */
function formatNextBriefingTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);
  const isTomorrow = date.toDateString() === tomorrow.toDateString();

  const timeStr = new Intl.DateTimeFormat('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(date);

  if (isToday) {
    return `Today at ${timeStr}`;
  } else if (isTomorrow) {
    return `Tomorrow at ${timeStr}`;
  } else {
    const dayStr = new Intl.DateTimeFormat('en-US', {
      weekday: 'long',
    }).format(date);
    return `${dayStr} at ${timeStr}`;
  }
}

/**
 * Render markdown-like narrative as HTML
 * Simple conversion for bold text and paragraphs
 */
function renderNarrative(narrative: string): React.ReactNode[] {
  // Split by double newlines for paragraphs
  const paragraphs = narrative.split(/\n\n+/);

  return paragraphs.map((paragraph, index) => {
    // Convert **text** to bold
    const html = paragraph
      .replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-gray-900 dark:text-gray-100">$1</strong>')
      .replace(/\n/g, '<br />');

    return (
      <p
        key={index}
        className="text-lg leading-relaxed text-gray-700 dark:text-gray-300"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    );
  });
}

/**
 * Recommended reading item component
 */
function RecommendationItem({ recommendation }: { recommendation: BriefingRecommendation }) {
  const href = recommendation.narrative_id
    ? `/narratives?highlight=${recommendation.narrative_id}`
    : '/narratives';

  return (
    <Link
      to={href}
      className="group block py-3"
    >
      <div className="flex items-start gap-3">
        <span className="text-gray-400 dark:text-gray-500 group-hover:text-blue-500 dark:group-hover:text-blue-400 transition-colors">
          &rarr;
        </span>
        <div>
          <p className="text-gray-900 dark:text-gray-100 group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors font-medium">
            {recommendation.title}
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            {formatTheme(recommendation.theme)}
          </p>
        </div>
      </div>
    </Link>
  );
}

/**
 * Story page banner — editorial CTA linking to the interactive case study
 */
function StoryBanner() {
  return (
    <motion.a
      href="/story.html"
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      className="group block mb-10 rounded-lg border border-amber-300/30 dark:border-amber-500/20 bg-gradient-to-r from-amber-50 via-amber-50/80 to-transparent dark:from-amber-950/30 dark:via-amber-950/20 dark:to-transparent px-6 py-5 hover:border-amber-400/50 dark:hover:border-amber-500/40 transition-all duration-300"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-widest text-amber-600/70 dark:text-amber-500/70 mb-1.5">
            Interactive · 6-Month Case Study
          </p>
          <p className="text-base font-medium text-gray-900 dark:text-gray-100 leading-snug">
            I had code. I didn't have a system.
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            The fastest way to master Agentic AI is to learn exactly where it breaks. This is that lesson.
          </p>
        </div>
        <div className="flex-shrink-0">
          <span className="inline-flex items-center gap-1 text-sm font-medium text-amber-700 dark:text-amber-400 group-hover:gap-2 transition-all duration-200">
            Explore
            <ArrowRight className="w-4 h-4" />
          </span>
        </div>
      </div>
    </motion.a>
  );
}

/**
 * Placeholder briefing for when no real briefing exists yet
 */
function getPlaceholderBriefing(): BriefingType {
  const now = new Date();
  const hour = now.getHours();
  const type = hour < 12 ? 'morning' : 'evening';

  return {
    _id: 'placeholder',
    type,
    generated_at: now.toISOString(),
    content: {
      narrative: `Welcome to Backdrop, your crypto intelligence companion.

The briefing agent is being set up and will start generating daily analysis soon. Once active, you'll receive **two briefings daily** at 8:00 AM EST and 8:00 PM EST.

Each briefing synthesizes the latest narratives, trending signals, and market movements into a concise analyst memo. The agent learns from feedback over time, improving its analysis and becoming more attuned to what matters most.

In the meantime, explore the **Signals** page to see entities with unusual activity, or dive into **Narratives** to understand the broader themes shaping the market.`,
      key_insights: [],
      entities_mentioned: [],
      detected_patterns: [],
      recommendations: [
        { title: 'View Market Signals', theme: 'market_volatility' },
        { title: 'Explore Narratives', theme: 'ecosystem_growth' },
      ],
    },
    metadata: {
      narratives_analyzed: 0,
      signals_analyzed: 0,
      articles_analyzed: 0,
      generation_time_ms: 0,
    },
    version: '2.0',
  };
}

export function Briefing() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['briefing', 'latest'],
    queryFn: () => briefingAPI.getLatest(),
    refetchInterval: 5 * 60 * 1000, // 5 minutes
    staleTime: 60 * 1000, // 1 minute
  });

  if (isLoading) return <BriefingSkeleton />;
  if (error) return <ErrorMessage message={error.message} onRetry={() => refetch()} />;

  // Use real briefing or placeholder
  const briefing = data?.briefing || getPlaceholderBriefing();
  const nextBriefingAt = data?.next_briefing_at;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4 }}
      className="max-w-2xl mx-auto"
    >
      {/* Story Page Banner */}
      <StoryBanner />

      {/* Header */}
      <header className="text-center mb-12">
        <h1 className="text-3xl md:text-4xl font-light text-gray-900 dark:text-gray-100 mb-3">
          {getBriefingTitle(briefing.type)}
        </h1>
        <p className="text-gray-500 dark:text-gray-400 text-lg">
          {formatBriefingDate(briefing.generated_at)} &middot; {formatBriefingTime(briefing.generated_at)}
        </p>
      </header>

      {/* Divider */}
      <div className="border-t border-gray-200 dark:border-gray-700 mb-10" />

      {/* Narrative Content */}
      <article className="space-y-6 mb-12">
        {renderNarrative(briefing.content.narrative)}
      </article>

      {/* Divider */}
      <div className="border-t border-gray-200 dark:border-gray-700 mb-10" />

      {/* Recommended Reading */}
      {briefing.content.recommendations && briefing.content.recommendations.length > 0 && (
        <section className="mb-12">
          <h2 className="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
            Recommended Reading
          </h2>
          <div className="divide-y divide-gray-100 dark:divide-gray-800">
            {briefing.content.recommendations.map((rec, index) => (
              <RecommendationItem key={index} recommendation={rec} />
            ))}
          </div>
        </section>
      )}

      {/* Divider */}
      <div className="border-t border-gray-200 dark:border-gray-700 mb-8" />

      {/* Next Briefing */}
      {nextBriefingAt && (
        <footer className="text-center text-gray-500 dark:text-gray-400 text-sm">
          Next briefing: {formatNextBriefingTime(nextBriefingAt)}
        </footer>
      )}
    </motion.div>
  );
}
