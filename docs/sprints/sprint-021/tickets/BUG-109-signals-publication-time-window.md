---
ticket_id: BUG-109
type: bug
title: Signals can surface old news as fresh after reprocessing
priority: high
status: OPEN
date_created: 2026-09-15
branch: null
related: BUG-108
---

# BUG-109: Signals can surface old news as fresh after reprocessing

## Problem

The Signals page explicitly requests `24h`, but `compute_trending_signals()` assigns mentions to time windows using `entity_mentions.created_at`, which is processing time. Enriching an old article today can therefore make old news appear in today's Signals. The 30-day enrichment eligibility cutoff uses article ingestion time and does not implement a 24-hour publication window.

This behavior was identified by repository inspection during BUG-108 post-deployment review. A production reset/rebuild has not been performed or authorized by this ticket.

## Product decisions — confirmed by operator on 2026-09-15

- Signals means **what the news discussed in the past 24 hours**, measured by source article publication time.
- **Exclude undated articles.** Do not substitute processing time, ingestion time, feed retrieval time, or the current time when publication time is missing, invalid, or cannot be established.
- Keep the page explicitly requesting `24h`; preserve the existing `7d` API default for other callers and support explicit `7d`/`30d` using the same publication-time semantics.
- Keep processing timestamps for operational monitoring; do not rewrite them to masquerade as publication timestamps.

## Code evidence and files to inspect

- `src/crypto_news_aggregator/services/signal_service.py`: `compute_trending_signals()` filters on `entity_mentions.created_at`, uses it for current/previous counts and first/latest timestamps, and uses it again in the source-count aggregation.
- `src/crypto_news_aggregator/db/operations/entity_mentions.py`: mention writers stamp `created_at` and `timestamp` at processing time. Preserve BUG-108 transaction ownership fencing and unique-key behavior.
- `src/crypto_news_aggregator/models/article.py`: source timestamp field is `published_at`; ingestion timestamp is `created_at`.
- `src/crypto_news_aggregator/services/rss_service.py`: `parse_feed()` currently substitutes `datetime.utcnow()` when `published_parsed` is absent. It also converts parsed feed times through local-time `mktime`. Merely switching the Signals query to `published_at` is insufficient if that field contains fabricated publication dates. Preserve UTC correctly and distinguish missing source dates from valid source dates without unnecessarily dropping article ingestion.
- `src/crypto_news_aggregator/api/v1/endpoints/signals.py`: review trending computation, associated article retrieval, and cache keys so results from the old timestamp semantics cannot leak through after rollout.
- `context-owl-ui/src/pages/Signals.tsx` and `src/api/signals.ts`: retain the explicit window across pagination and refresh.

## Expected behavior

Use one UTC reference time per calculation. For a requested duration W, the current interval is [now − W, now] and the previous interval is [now − 2W, now − W). Exactly-at-boundary records belong to only one period. Exclude future publication times from both periods.

An article published 20 days ago and processed now must not contribute to 24h Signals. An article published two hours ago and processed now may contribute. An undated article processed now must not contribute. Apply the same temporal basis consistently to current/previous mention counts, velocity, first/latest timestamps, and source diversity. Keep any intentional current-plus-previous source aggregation scope documented; do not mix publication and processing clocks.

## Implementation scope

1. Define a trustworthy publication-time representation, normalized to UTC, including how unknown dates are represented without rejecting ingestion unnecessarily. Trace relevant ingestion paths and prevent fabricated current timestamps from being treated as source publication dates.
2. Implement publication-based Signals computation using an article join or a persisted, provenance-aware publication field on mentions. Choose a bounded/index-supported approach and document any index or data preparation required. Preserve legacy mention-to-article linkage (normally string `article_id` versus ObjectId article `_id`) and handle missing/orphaned links safely.
3. Handle existing data explicitly. Assess whether source publication time can be established from stored source metadata; do not assume every legacy `published_at` is trustworthy because it is populated. Provide read-only counts/dry-run assessment before any repair. Exclude unverifiable records rather than invent dates.
4. Invalidate/version affected caches as part of the code rollout plan. Verify article lists shown with Signals obey the displayed window where applicable. Keep scoring weights, thresholds, enrichment scheduling, retry/lease behavior, and unrelated signal features out of scope.
5. Add meaningful behavioral tests through actual computation and relevant ingestion/API paths. Record actual results and limitations; a source-text assertion is not proof of time-window behavior.

## Acceptance criteria

- [ ] A weeks-old article processed today is absent from 24h counts and cannot create a current signal.
- [ ] A recently published article counts independently of mention processing time.
- [ ] Missing, null, malformed, or unverifiable publication dates are excluded; missing RSS dates are not fabricated as current publication times.
- [ ] Future-dated articles are excluded; UTC offsets and both window boundaries are tested.
- [ ] Previous-period counts and velocity use publication time; source diversity uses the same clock and documented window scope.
- [ ] Explicit 7d/30d windows follow the same semantics; UI remains 24h and API default remains 7d.
- [ ] Reprocessing/retrying an article does not move its news date forward or duplicate its contribution.
- [ ] Legacy/orphaned mention records are handled deliberately; rollout requires no blind historical timestamp rewrite.
- [ ] Cache behavior and relevant article lists agree with the new semantics.
- [ ] Relevant tests/checks pass, and staging demonstrates old article processed now excluded versus recent dated article included.

## Relationship to BUG-108 and rollout

[BUG-108](BUG-108-signals-page-no-signals.md) addresses enrichment reliability, ownership safety, and duplicate prevention. BUG-109 addresses the distinct meaning of news freshness.

**BUG-109 must be fixed and validated before rebuilding/backfilling production mentions as part of BUG-108 recovery.** Clearing a signals collection alone would not change this computation. No reset, deletion, or migration is authorized by creating this ticket. Read-only checks can continue while implementation proceeds locally.

The production review on 2026-09-15 found enrichment blocked by its missing unique index, a transaction-capable replica-set configuration, 144 articles ingested in the preceding 24h, zero recent primary mentions, and 2,016 duplicate mention groups containing 41,390 excess records. These are point-in-time observations, not publication freshness evidence. Duplicate cleanup/reset and index creation require a separately reviewed, explicitly approved scope.

## Resolution

Open. No implementation, production deletion, data repair, index creation, or deployment performed for this ticket. Product intent and undated-article exclusion are resolved; implementation and validation remain pending.
