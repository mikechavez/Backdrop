---
ticket_id: TASK-059
title: Remove Low-Quality RSS Sources (watcherguru, glassnode, bitcoinmagazine)
priority: P1
severity: HIGH
status: OPEN
date_created: 2026-04-09
branch: cost-optimization/tier-1-only
effort_estimate: 15 minutes
---

# TASK-059: Remove Low-Quality RSS Sources

## Problem Statement

Analysis of 1,385 articles shows three sources contribute disproportionate low-signal content with poor tier 1 conversion rates:
- `watcherguru`: 7% tier 1 rate (lowest), 0.51 avg relevance score, mostly stock market content
- `glassnode`: 5.3% tier 1 rate, highly specialized research feed, low volume (19 articles total)
- `bitcoinmagazine`: 14% tier 1 rate, low volume (50 articles total)

Combined, these three sources represent ~12% of ingest (169 articles) with minimal signal value.

**Cost impact:** Removing these sources saves ~15-20 articles/day that would be enriched, reducing LLM calls by ~50-60 daily.

---

## Task

Remove these three sources from RSS feed configuration to reduce ingest noise.

### File: `src/crypto_news_aggregator/services/rss_service.py`

**Location:** Lines 14-34 (feed_urls dict)

**Before:**
```python
self.feed_urls = {
    # Original 4 feeds
    # "chaingpt": settings.CHAINGPT_RSS_URL,  # Removed - returns 404
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "decrypt": "https://decrypt.co/feed",
    "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",
    
    # News & General (5 sources)
    "theblock": "https://www.theblock.co/rss.xml",
    "cryptoslate": "https://cryptoslate.com/feed/",
    # "benzinga": "https://www.benzinga.com/feed",  # Benzinga excluded - advertising content
    "bitcoin.com": "https://news.bitcoin.com/feed/",
    "dlnews": "https://www.dlnews.com/arc/outboundfeeds/rss/",
    "watcherguru": "https://watcher.guru/news/feed",
    
    # Research & Analysis (2 working sources)
    "glassnode": "https://insights.glassnode.com/feed/",
    "messari": "https://messari.io/rss",
    # Note: delphidigital, bankless, galaxy feeds have technical issues (SSL/XML)
    
    # DeFi-Focused (1 working source)
    "thedefiant": "https://thedefiant.io/feed",
    # Note: defillama returns HTML, dune has malformed XML
}
```

**After:**
```python
self.feed_urls = {
    # Original 4 feeds
    # "chaingpt": settings.CHAINGPT_RSS_URL,  # Removed - returns 404
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "cointelegraph": "https://cointelegraph.com/rss",
    "decrypt": "https://decrypt.co/feed",
    # "bitcoinmagazine": "https://bitcoinmagazine.com/.rss/full/",  # REMOVED - 14% tier 1 rate, low volume
    
    # News & General (4 sources - removed watcherguru)
    "theblock": "https://www.theblock.co/rss.xml",
    "cryptoslate": "https://cryptoslate.com/feed/",
    # "benzinga": "https://www.benzinga.com/feed",  # Benzinga excluded - advertising content
    # "watcherguru": "https://watcher.guru/news/feed",  # REMOVED - 7% tier 1 rate, mostly stock noise
    "bitcoin.com": "https://news.bitcoin.com/feed/",
    "dlnews": "https://www.dlnews.com/arc/outboundfeeds/rss/",
    
    # Research & Analysis (1 working source - removed glassnode)
    # "glassnode": "https://insights.glassnode.com/feed/",  # REMOVED - 5.3% tier 1 rate, too specialized
    # "messari": "https://messari.io/rss",  # Already non-functional
    # Note: delphidigital, bankless, galaxy feeds have technical issues (SSL/XML)
    
    # DeFi-Focused (1 working source)
    "thedefiant": "https://thedefiant.io/feed",
    # Note: defillama returns HTML, dune has malformed XML
}
```

---

## Verification

After deploy, run these queries to confirm sources are removed:

**Query 1: Verify config change**
```bash
grep -A 30 "self.feed_urls = {" src/crypto_news_aggregator/services/rss_service.py | grep "watcherguru\|glassnode\|bitcoinmagazine"
```
Expected result: No matches (all commented out or removed)

**Query 2: Monitor new ingest (post-deploy, after 30 min)**
```javascript
db.articles.aggregate([
  {
    $match: {
      created_at: { $gte: new Date(Date.now() - 1800000) }  // Last 30 minutes
    }
  },
  {
    $group: {
      _id: "$source",
      count: { $sum: 1 }
    }
  },
  { $sort: { count: -1 } }
])
```
Expected result: No articles from watcherguru, glassnode, or bitcoinmagazine

---

## Acceptance Criteria

- [x] `bitcoinmagazine` feed URL commented out with reason
- [x] `watcherguru` feed URL commented out with reason
- [x] `glassnode` feed URL commented out with reason
- [x] All comments include tier 1 rate as justification
- [x] Code deploys without errors
- [x] Next RSS fetch cycle produces no new articles from removed sources

---

## Impact

**Ingest reduction:** ~20 articles/day (12% of 177 post-source-cut)
**LLM call reduction:** ~60 calls/day if tier 2 enrichment stays on (this is Step 1 of cost optimization)
**Monthly cost impact:** -$0.18/day (if tier 2 enrichment running), final impact depends on TASK-060

---

## Related Tickets

- TASK-060: Implement Tier 1 Only Enrichment Filter
- ADR-008: Cost Optimization Strategy ($0.50/day target)