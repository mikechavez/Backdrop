import feedparser
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional
from time import mktime

from crypto_news_aggregator.models.article import (
    ArticleCreate,
    ArticleMetrics,
    ArticleAuthor,
)
from crypto_news_aggregator.core.config import get_settings


class RSSService:
    def __init__(self):
        settings = get_settings()
        self.feed_urls = {
            # Original 4 feeds
            # "chaingpt": settings.CHAINGPT_RSS_URL,  # Removed - returns 404
            "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "cointelegraph": "https://cointelegraph.com/rss",
            "decrypt": "https://decrypt.co/feed",
            # "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",  # Removed - 14% tier 1 rate, low volume

            # News & General (4 sources)
            "theblock": "https://www.theblock.co/rss.xml",
            "cryptoslate": "https://cryptoslate.com/feed/",
            # "benzinga": "https://www.benzinga.com/feed",  # Benzinga excluded - advertising content
            "bitcoin.com": "https://news.bitcoin.com/feed/",
            "dlnews": "https://www.dlnews.com/arc/outboundfeeds/rss/",
            # "watcherguru": "https://watcher.guru/news/feed",  # Removed - 7% tier 1 rate, mostly stock noise

            # Research & Analysis (1 working source)
            # "glassnode": "https://insights.glassnode.com/feed/",  # Removed - 5.3% tier 1 rate, too specialized
            "messari": "https://messari.io/rss",
            # Note: delphidigital, bankless, galaxy feeds have technical issues (SSL/XML)

            # DeFi-Focused (1 working source)
            "thedefiant": "https://thedefiant.io/feed",
            # Note: defillama returns HTML, dune has malformed XML
        }

    async def fetch_feed(self, url: str) -> Optional[feedparser.FeedParserDict]:
        """Asynchronously fetches and parses an RSS feed."""
        try:
            loop = asyncio.get_event_loop()
            # feedparser is not async, so we run it in a thread pool
            feed = await loop.run_in_executor(None, feedparser.parse, url)
            if feed.bozo:
                print(f"Error parsing feed {url}: {feed.bozo_exception}")
                return None
            return feed
        except Exception as e:
            print(f"An error occurred while fetching feed {url}: {e}")
            return None

    async def fetch_all_feeds(self) -> List[ArticleCreate]:
        """Fetches and processes all configured RSS feeds."""
        tasks = [self.fetch_feed(url) for url in self.feed_urls.values()]
        feeds = await asyncio.gather(*tasks)

        all_articles = []
        source_names = list(self.feed_urls.keys())

        for i, feed in enumerate(feeds):
            if feed:
                source = source_names[i]
                articles = self.parse_feed(feed, source)
                all_articles.extend(articles)

        return all_articles

    def parse_feed(
        self, feed: feedparser.FeedParserDict, source: str
    ) -> List[ArticleCreate]:
        """Parses a feed and returns a list of Article objects."""
        articles = []
        for entry in feed.entries:
            published_date = (
                datetime.fromtimestamp(mktime(entry.published_parsed))
                if hasattr(entry, "published_parsed") and entry.published_parsed
                else datetime.utcnow()
            )

            author = (
                ArticleAuthor(id=entry.author, name=entry.author)
                if hasattr(entry, "author") and entry.author
                else None
            )
            article = ArticleCreate(
                title=entry.title,
                text=entry.summary,
                url=str(entry.link),
                source_id=entry.link,  # Use link as a unique ID for RSS
                source=source,  # Use the actual feed name (coindesk, cointelegraph, etc.)
                author=author,
                published_at=published_date,
                metrics=ArticleMetrics(),
                raw_data=entry,
            )
            articles.append(article)
        return articles


async def main():
    rss_service = RSSService()
    articles = await rss_service.fetch_all_feeds()
    await create_or_update_articles(articles)
    print(f"Successfully fetched and saved {len(articles)} articles.")


if __name__ == "__main__":
    asyncio.run(main())
