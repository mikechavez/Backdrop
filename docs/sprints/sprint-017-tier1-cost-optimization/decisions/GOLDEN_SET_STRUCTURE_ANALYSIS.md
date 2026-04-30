---
date: 2026-04-29
type: analysis
---

# Golden Set Structure & Complexity Analysis

## File Structure Overview

All three golden set files are **JSONL format** (one valid JSON object per line, 100 articles each).

### Common Fields (All Operations)
- `_id`: MongoDB ObjectId (format: `{"$oid": "..."}`)
- `title`: Article headline (string)
- `text`: Article content (HTML-escaped)
- `created_at`: Timestamp (format: `{"$date": "2026-04-14T...Z"}`)

### Operation-Specific Fields
- **entity_extraction**: `entities` (array of objects with name, type, ticker, confidence, is_primary)
- **sentiment_analysis**: `sentiment` (object with label and score)
- **theme_extraction**: `themes` (array of strings)

---

## Article Identification

**ID Field:** `_id` (MongoDB ObjectId)
- Format: 24-character hex string (e.g., `69ddd19a972adb5ad8c76bbf`)
- Same 100 articles appear across all three operations
- Sample first 3 IDs:
  - `69ddd19a972adb5ad8c76bbf`
  - `69dde0a0972adb5ad8c76c09`
  - `69ddf73b972adb5ad8c76c56`

---

## Complexity Distribution

### entity_extraction

**Field:** `entities` array (objects with name, type, confidence, is_primary)

```
Entity counts per article:
  Min: 1
  Max: 9
  Mean: 2.82
  Q1: 2.0
  Median: 2.5
  Q3: 4.0
```

**Insight:** Low to moderate complexity. 75% of articles have ≤4 entities. Mix of short/long-tail extraction.

---

### sentiment_analysis

**Field:** `sentiment` object with:
- `label`: "positive", "neutral", or "negative"
- `score`: float in range [-1.0, 0.8]

```
Label distribution:
  Positive: 50 articles (50%)
  Neutral: 24 articles (24%)
  Negative: 26 articles (26%)

Score range:
  Min: -0.900
  Max: 0.800
  Mean: 0.134
```

**Insight:** Balanced but positive-skewed dataset. Moderate range, no extreme polarization. Good for threshold testing.

---

### theme_extraction

**Field:** `themes` array (strings, no metadata)

```
Theme counts per article:
  Min: 3
  Max: 8
  Mean: 5.42
  Q1: 5.0
  Median: 5.0
  Q3: 6.0
```

**Insight:** Moderate complexity, tight distribution. Most articles have 5-6 themes. Few outliers.

---

## Validation Worksheet Coverage

The f053-validation-worksheet.md contains **manual labels from you** for:
- **entity_extraction:** 10 samples labeled
- **sentiment_analysis:** 10 samples labeled
- **theme_extraction:** 10 samples labeled

### Labeled Samples by Operation

#### entity_extraction (10 samples)
| Sample | Title |
|--------|-------|
| 0 | Bitcoin, Ether ETFs See Nearly $1 Billion in Weekly Inflows |
| 2 | US Justice Department opens claims for victims of $4 billion OneCoin... |
| 4 | DOJ Opens $40M Compensation Process for OneCoin Crypto Fraud Victims |
| 6 | Bitcoin ETFs clock $291M outflows as BTC blasts past $74K |
| 7 | Web3 hacks cost $464M in Q1 as phishing drives majority of losses |
| 9 | Morning Minute: The SEC Just Gave DeFi The Green Light |
| 10 | Deutsche Börse invests $200 million in Kraken parent Payward |
| 11 | XRP Ledger taps Boundless for bank-grade privacy on public... |
| 12 | Fake Ledger app on Apple App Store linked to $9.5M crypto theft |
| 22 | XRP consolidation may transform into explosive rally if $1.40... |

**Match Rate:** 3/10 = 30% exact match with Haiku (samples 2, 4, 7)

#### sentiment_analysis (10 samples)
| Sample | Title |
|--------|-------|
| 0 | Bitcoin, Ether ETFs See Nearly $1 Billion in Weekly Inflows |
| 1 | Circle, Dunamu Partner on Crypto Education in South Korea |
| 2 | US Justice Department opens claims for victims of $4 billion OneCoin... |
| 3 | Relm Insurance Launches Crypto and Cannabis Kidnap Coverage |
| 4 | DOJ Opens $40M Compensation Process for OneCoin Crypto Fraud Victims |
| 5 | Crypto Market Cap Hits $2.6 Trillion as Bitcoin Eyes $75K... |
| 6 | Bitcoin ETFs clock $291M outflows as BTC blasts past $74K |
| 7 | Web3 hacks cost $464M in Q1 as phishing drives majority of losses |
| 8 | Bitcoin price soars to 4 week high passing multiple resistance... |
| 9 | Morning Minute: The SEC Just Gave DeFi The Green Light |

**Match Rate:** 6/10 = 60% exact match with Haiku (samples 0, 1, 5, 6, 7, 8)

#### theme_extraction (10 samples)
| Sample | Title |
|--------|-------|
| 0 | Bitcoin, Ether ETFs See Nearly $1 Billion in Weekly Inflows |
| 1 | Circle, Dunamu Partner on Crypto Education in South Korea |
| 2 | US Justice Department opens claims for victims of $4 billion OneCoin... |
| 4 | DOJ Opens $40M Compensation Process for OneCoin Crypto Fraud Victims |
| 6 | Bitcoin ETFs clock $291M outflows as BTC blasts past $74K |
| 7 | Web3 hacks cost $464M in Q1 as phishing drives majority of losses |
| 9 | Morning Minute: The SEC Just Gave DeFi The Green Light |
| 23 | XRP consolidation may transform into explosive rally if $1.40... |
| 26 | Goldman Sachs to use options strategy for planned Bitcoin income ETF |
| 30 | DAO behind CoW Swap urges users to stay off platform after 'hijacking' |

**Match Rate:** 1/10 = 10% exact match with Haiku (sample 6)

---

## Key Observations

### 1. Validation Data Quality
- **Sentiment analysis** has highest agreement (60%), suggests good quality baseline
- **Entity extraction** moderate agreement (30%), expected given entity lists vary
- **Theme extraction** low agreement (10%), indicates Haiku over-includes themes vs. manual labels

### 2. Complexity Suitable for Scoring
- All operations have good variance in complexity (Q1 ≠ Q3)
- No extreme outliers that would skew statistics
- Dataset size (100 samples) sufficient for threshold validation

### 3. Scoring Approach Implications
- **For entity_extraction:** F1 scoring on entities (how many predicted match reference)
- **For sentiment_analysis:** Accuracy on label (positive/neutral/negative)
- **For theme_extraction:** Adjusted F1 on themes (reference vs. predicted)
- **Threshold values** from TASK-082 are realistic given distribution

---

## Next Steps (Phase 3 Scoring)

With this structure understood:

1. **Load Phase 1 baseline scores** from `phase-1-baselines/` 
   - Extract F1/accuracy for each operation
   
2. **Load Phase 2 challenger outputs** from `phase-2-challenger-runs/`
   - Parse JSONL outputs from Flash, DeepSeek, Qwen
   - Calculate scores using same metrics as baseline

3. **Apply thresholds** (from TASK-082):
   - entity_extraction: F1 ≥ 0.82
   - sentiment_analysis: Accuracy ≥ 77%
   - theme_extraction: Adjusted F1 ≥ 0.78

4. **Validation check:** Spot-check 5-10 labeled samples per operation
   - Verify scoring logic on known labels from worksheet
   - Build confidence before full pass/fail determination
