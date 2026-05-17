# Briefing Generation Prompts

## Overview

The briefing generation system uses a **3-phase LLM pipeline** to synthesize crypto narratives and market signals into high-quality, grounded briefings:

1. **Generation** — Create initial briefing from narratives + signals
2. **Critique** — Evaluate for hallucination, entity clarity, quality issues
3. **Refinement** — Fix issues using full source context

**File:** `src/crypto_news_aggregator/services/briefing_agent.py`

---

## Architecture

### Pipeline Flow

```
Narratives + Signals + Memory
         │
         ▼
    ┌─────────────────────┐
    │  Phase 1: Generate  │  LLM creates initial briefing
    │  (Haiku + system)   │  Input: narratives, signals, patterns
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │  Phase 2: Critique  │  LLM evaluates 10 quality dimensions
    │  (Haiku, 1K tokens) │  Checks: hallucination, entity clarity, etc.
    └──────────┬──────────┘
               │
        ┌──────┴──────┐
        │             │
        ▼             ▼
    PASS          NEEDS FIX
    (done)           │
               ▼─────────────────┐
               │  Phase 3: Refine│  LLM fixes issues (up to 2 iterations)
               │  (Haiku, 4K)    │  Refinement call 1, 2, etc.
               └────────┬────────┘
                        │
                        ▼
                    SAVE BRIEFING
```

### Models & Configuration

- **Primary Model:** Claude Haiku 4.5 (`claude-haiku-4-5-20251001`)
- **Fallback Model:** Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)
- **Generation:** max_tokens=4096
- **Critique:** max_tokens=1024
- **Refinement:** max_tokens=4096
- **Cost per briefing:** ~$0.002-0.004 (Haiku)

---

## Phase 1: System Prompt & Rules

### Core System Prompt

```
You are a senior crypto market analyst writing a [morning/evening] briefing memo.

Your role is to synthesize ONLY the narratives listed below into an insightful briefing.

═══════════════════════════════════════════════════════════════════════════════
CRITICAL: ZERO TOLERANCE FOR HALLUCINATION
═══════════════════════════════════════════════════════════════════════════════

You will be given a list of narratives below. Your briefing MUST:
✓ ONLY discuss narratives explicitly listed in the data below
✓ ONLY use facts, names, and details that appear in those narratives
✗ NEVER add companies, people, events, or facts from your training knowledge
✗ NEVER mention entities unless they appear in the narratives below
✗ NEVER invent acquisitions, partnerships, or regulatory events

If you mention something not in the provided narratives, the briefing is INVALID.
═══════════════════════════════════════════════════════════════════════════════
```

### 11 Critical Writing Rules

#### Rule 1: SPECIFIC ENTITY REFERENCES (NEW - CRITICAL)
- **ALWAYS use full entity names:** "Binance", "BlackRock", "Cardano"
- **NEVER use vague references:** "the platform", "the exchange", "the network"
- If an entity is mentioned multiple times, use its name each time
- Example GOOD: "Binance has expanded its stablecoin offerings..."
- Example BAD: "The exchange is expanding..." (which exchange?)

#### Rule 2: EXPLAIN "WHY IT MATTERS" (MANDATORY)
- Every significant development MUST include its implications
- Use phrases like:
  - "The significance lies in..."
  - "This matters because..."
  - "The immediate impact is..."
  - "This represents..."
- Connect events to broader market trends or investor decisions
- Example GOOD: "BlackRock's Bitcoin ETF positioning represents material institutional endorsement that could drive Q1 capital flows despite regulatory uncertainty."
- Example BAD: "BlackRock designated Bitcoin ETF as key theme." (so what?)

#### Rule 3: ONLY COVER NARRATIVES FROM THE DATA
- Read the "Active Narratives" section carefully
- Each narrative you discuss MUST match one of the titles listed
- Do not add stories that aren't in the list

#### Rule 4: USE EXACT DETAILS FROM SUMMARIES
- The narrative summaries contain the facts you should use
- Copy specific details (names, amounts, events) from the summaries
- If a summary lacks details, say so rather than inventing them

#### Rule 5: NO GENERIC FILLER
- **BANNED phrases:**
  - "The crypto markets continue to..."
  - "In a mix of developments..."
  - "Looking ahead, the industry will be shaped by..."
  - "Navigating challenges"
  - "Amid uncertainty"
  - "In the evolving landscape"
- Start directly with your most important story
- End with specific actionable focus areas

#### Rule 6: PROFESSIONAL ANALYST TONE
- Write as flowing memo, not bullet points
- Connect related developments with causal reasoning
- Be direct about uncertainty when data is limited
- Use informed opinion with clear reasoning

#### Rule 7: STRUCTURE
- Each paragraph = one narrative or connected set of narratives
- Open with most significant development
- End with specific "immediate focus" areas

#### Rule 8: RECOMMENDATIONS (CRITICAL)
- Include 2-3 recommendations for further reading
- **ONLY recommend narratives from the "ALLOWED NARRATIVES" list**
- Use the **EXACT narrative title** as recommendation title (matching case)
- For theme, use the topic/category (e.g., "Regulation", "Trading", "Infrastructure")
- Example: `{"title": "Binance Expands in South Korea", "theme": "Regulatory Expansion"}`
- **NEVER create recommendation titles that aren't in the allowed list**
- **NEVER suggest topics or narratives that weren't provided**

#### Rule 9: CONSOLIDATE DUPLICATE EVENTS (NEW - BUG-081)
- If multiple narratives describe the same underlying event from different angles, synthesize into one
- Do NOT present the same event twice with different framing
- Look for overlapping entities, similar dollar amounts, or same infrastructure/platform
- Example: Two narratives about a Polkadot bridge exploit = one consolidated paragraph

#### Rule 10: NO UNNAMED ENTITIES (NEW - BUG-081, CRITICAL)
- If you cannot name a specific platform, exchange, or entity from provided narratives, don't reference it
- **NEVER use phrases like:**
  - "two platforms"
  - "multiple exchanges"
  - "several protocols"
- Unless you can **name each one explicitly**
- **NEVER imply a count of affected parties you cannot enumerate by name**
- If a narrative lacks specific details, acknowledge the limitation rather than imply unnamed actors

#### Rule 11: VERIFY FIGURE PLAUSIBILITY (NEW - BUG-081)
- Before citing any financial figure, consider whether it's plausible (~$2-3T crypto market cap)
- **A single-event liquidation exceeding $50B, a hack exceeding $10B = almost certainly errors**
- If a figure seems implausible, flag uncertainty: "reported figures suggest $X, though this would be historically unprecedented"
- When source articles disagree on a figure, note the discrepancy rather than picking the most dramatic number

### Output Format

```json
{
    "narrative": "The briefing text...",
    "key_insights": ["insight1", "insight2", "insight3"],
    "entities_mentioned": ["Entity1", "Entity2"],  // Full names only
    "detected_patterns": ["pattern1", "pattern2"],
    "recommendations": [
        {"title": "Narrative Title", "theme": "Category"}
    ],
    "confidence_score": 0.85
}
```

---

## Phase 1: Generation Prompt

**File:** `briefing_agent.py:649-719` (`_build_generation_prompt()`)

### Prompt Structure

The generation prompt assembles 8 sections of context:

#### 1. Time Context (Display Timezone)
```
Generate the [morning/evening] crypto briefing for [Day, Month Date, Year].
```
- Uses Chicago timezone (CST/CDT) to match frontend display
- Human-readable format for context

#### 2. Memory Context (If Available)
- Previous feedback on tone, coverage, focus areas
- Preferences from memory system
- Editor notes or guidelines

#### 3. Current Trending Signals (Top 10)
```
## Current Trending Signals

- Bitcoin: score=0.78, velocity=45%
- Ethereum: score=0.65, velocity=32%
...
```
- Real-time market sentiment
- Score (0-1) and velocity (% change)

#### 4. ALLOWED NARRATIVES (Bold Explicit Section)
```
═══════════════════════════════════════════════════════════════════════════════
ALLOWED NARRATIVES - You may ONLY discuss these stories:
  1. SEC Regulatory Crackdown on Crypto Exchanges
  2. Bitcoin ETF Adoption Accelerates
  3. DeFi Protocol Security Audit Results
  ...
Any other company, person, or event NOT listed above is FORBIDDEN.
═══════════════════════════════════════════════════════════════════════════════
```
- Numbered list of titles (max 8)
- Explicit emphasis: "You may ONLY discuss these"
- Warning: "Any other... is FORBIDDEN"

#### 5. Narrative Details (Full Context)
```
## Narrative Details (use these facts):

### SEC Regulatory Crackdown on Crypto Exchanges
Sources: 5 articles
Facts: The SEC issued enforcement action against Binance and Coinbase...
```
- Title
- Article count (shows narrative strength)
- Full summary (copy-paste from narrative document)
- Key entities

#### 6. Detected Patterns (If Any)
```
## Market Patterns Detected
- Correlation: Bitcoin and Ethereum moving in sync (0.87 correlation)
- Divergence: Regulatory sentiment vs. institutional adoption
```

#### 7. Manual Inputs (If Any, Up to 3)
```
## External Inputs to Consider
### Breaking News
A major exchange announced...
```

#### 8. Final Reminders
```
---

Generate the briefing now. REMEMBER:
- ONLY use facts from the narratives and signals above
- Include specific details from the narrative summaries
- If a narrative lacks details, either skip it or acknowledge the limitation
- No generic openings or closings
- RECOMMENDATIONS: Include 2-3 recommendations ONLY from the ALLOWED NARRATIVES list
- Return ONLY valid JSON.
```

### Example Generation Prompt (Condensed)

```
Generate the morning crypto briefing for Wednesday, May 14, 2026.

## Current Trending Signals
- Bitcoin: score=0.82, velocity=52%
- Ethereum: score=0.71, velocity=38%
- Solana: score=0.68, velocity=25%

═══════════════════════════════════════════════════════════════════════════════
ALLOWED NARRATIVES - You may ONLY discuss these stories:
  1. SEC Enforcement Actions Against Major Exchanges
  2. BlackRock Bitcoin ETF Reaches $5B AUM
  3. Solana Network Upgrade Reduces Latency
  4. DeFi Lending Protocol Security Audit
  5. Federal Reserve Digital Dollar Progress
Any other company, person, or event NOT listed above is FORBIDDEN.
═══════════════════════════════════════════════════════════════════════════════

## Narrative Details (use these facts):

### SEC Enforcement Actions Against Major Exchanges
Sources: 7 articles
Facts: The SEC issued enforcement action claiming both Binance and Coinbase operated as
unregistered securities exchanges by offering staking services. This represents the most
significant regulatory action this quarter...

### BlackRock Bitcoin ETF Reaches $5B AUM
Sources: 4 articles
Facts: BlackRock's spot Bitcoin ETF exceeded $5 billion in assets under management,
signaling sustained institutional demand for direct Bitcoin exposure...

[Continue for narratives 3-5]

---

Generate the briefing now. REMEMBER:
- ONLY use facts from the narratives above
- Include specific details from the summaries
- RECOMMENDATIONS: 2-3 from ALLOWED NARRATIVES list only
- Return ONLY valid JSON.
```

---

## Phase 2: Critique Prompt

**File:** `briefing_agent.py:721-776` (`_build_critique_prompt()`)

**Purpose:** Evaluate briefing across 10 quality dimensions before sending to user  
**Model:** Claude Haiku 4.5  
**Max tokens:** 1024

### Critique Checklist

#### 1. HALLUCINATION (Most Critical)
- Does the briefing mention facts, companies, events, or numbers NOT in the provided narratives?
- Any external knowledge from training data?

#### 2. VAGUE ENTITY REFERENCES (NEW - CRITICAL)
- Does it use "the platform", "the exchange", "the network" instead of specific names?
- Every entity must be explicitly named from narratives

#### 3. MISSING "WHY IT MATTERS"
- Are events mentioned without explaining significance or implications?
- Does each development explain its importance?

#### 4. VAGUE CLAIMS
- Statements like "X is navigating challenges" without specific details?
- Each claim needs specifics

#### 5. MISSING CONTEXT
- Are numbers mentioned without baselines or comparisons?
- Do figures have proper context?

#### 6. GENERIC FILLER
- Starts with "The crypto markets continue to..."?
- Ends with generic forward-looking statements?
- Contains banned phrases: "amid uncertainty", "navigating challenges", "evolving landscape"?

#### 7. ABRUPT TRANSITIONS
- Does it switch topics mid-paragraph without logical connection?
- Are related developments properly linked?

#### 8. DUPLICATE EVENTS (CRITICAL - NEW BUG-081)
- Does the briefing describe the same underlying event more than once with different framing?
- Look for overlapping entities, similar figures, or same infrastructure involved
- If two sections cover the same incident, this is a CRITICAL issue — must be consolidated

#### 9. UNNAMED ENTITIES (CRITICAL - NEW BUG-081)
- Does it reference unnamed platforms, exchanges, or entities?
- Phrases like "two platforms", "multiple exchanges", "several protocols" without naming each?
- Every referenced entity must be explicitly named from provided narratives

#### 10. IMPLAUSIBLE FIGURES (NEW BUG-082)
- Are any cited figures implausible relative to ~$2-3T total crypto market?
- $50B+ single-event liquidations, $10B+ hacks = historically unprecedented
- Flag any such figures

### Critique Response Format

```json
{
    "needs_refinement": true/false,
    "issues": [
        "Hallucination: mentions 'FTX collapse' not in narratives",
        "Unnamed entities: '2 exchanges' without naming which ones",
        "Generic filler: opens with 'crypto markets continue to...'"
    ],
    "suggestions": [
        "Remove FTX reference entirely",
        "Replace 'multiple exchanges' with explicit names from narratives",
        "Start with most significant development instead"
    ]
}
```

### Example Critique Prompt (Condensed)

```
Review this crypto briefing for quality issues:

BRIEFING NARRATIVE:
The crypto markets continue to navigate regulatory challenges...

KEY INSIGHTS:
["SEC enforcement escalating", "Institutional adoption growing", "Market consolidation"]

AVAILABLE NARRATIVES:
["SEC Enforcement Actions Against Major Exchanges", "BlackRock Bitcoin ETF Reaches $5B AUM", ...]

AVAILABLE ENTITIES:
["SEC", "Binance", "Coinbase", "BlackRock", "Bitcoin", "Ethereum", ...]

Check for these issues:

1. HALLUCINATION: Does the briefing mention facts NOT from provided narratives?
2. VAGUE ENTITY REFERENCES: Use of "the platform" instead of specific names?
3. MISSING "WHY IT MATTERS": Events without explaining implications?
4. VAGUE CLAIMS: Details without specifics?
5. MISSING CONTEXT: Numbers without baselines?
6. GENERIC FILLER: Banned phrases like "evolving landscape"?
7. ABRUPT TRANSITIONS: Topics switched without logical flow?
8. DUPLICATE EVENTS: Same event described twice differently?
9. UNNAMED ENTITIES: "Multiple exchanges" without naming each?
10. IMPLAUSIBLE FIGURES: $50B+ liquidations or similar extremes?

Respond with JSON...
```

---

## Phase 3: Refinement Prompt

**File:** `briefing_agent.py:795-868` (`_build_refinement_prompt()`)

**Purpose:** Fix issues identified in critique, improve quality  
**Model:** Claude Haiku 4.5  
**Max tokens:** 4096  
**Max iterations:** 2

### Refinement Structure

#### 1. Original Briefing
- Full text from generation phase
- Shows what needs fixing

#### 2. Critique Feedback
- Specific issues identified
- Suggestions for improvement

#### 3. Available Source Context (Detailed)
```
AVAILABLE SOURCE CONTEXT:

Narratives (facts you may reference):
1. SEC Enforcement Actions Against Major Exchanges
   Articles: 7
   Summary: The SEC issued enforcement action...
   Entities: SEC, Binance, Coinbase, Bitcoin

2. BlackRock Bitcoin ETF Reaches $5B AUM
   Articles: 4
   Summary: BlackRock's spot Bitcoin ETF exceeded $5 billion...
   Entities: BlackRock, Bitcoin, Bitcoin ETF

Trending Signals (entities with momentum):
- Bitcoin: score=0.82, velocity=52%
- Ethereum: score=0.71, velocity=38%

Detected Patterns (up to 5 shown):
- Correlation: Institutional adoption and ETF flows moving together
- Divergence: Regulatory news causing temporary sentiment swings
```

#### 4. Refinement Instructions
```
REFINEMENT INSTRUCTIONS:
- Return ONLY valid JSON in the same format as the original briefing
- Do NOT ask for additional data or context
- Use ONLY the source context provided above
- If a claim is not supported by the source context, REMOVE it
- If source context is sparse, produce a conservative briefing
- Do NOT include any text outside the JSON object
```

### Example Refinement Prompt (Condensed)

```
Refine this crypto briefing based on the critique feedback:

ORIGINAL BRIEFING:
The crypto markets continue to navigate regulatory challenges with SEC enforcement
actions against major exchanges signaling... [Note: removed vague "the platform" refs]

CRITIQUE FEEDBACK:
{
    "needs_refinement": true,
    "issues": [
        "Generic opening: 'crypto markets continue to navigate'",
        "Missing 'why it matters' for SEC action",
        "Vague claim about impact without specifics"
    ],
    "suggestions": [
        "Start with most significant story: SEC enforcement",
        "Explain why SEC actions matter: institutional confidence, market structure",
        "Include specific details from SEC action narrative"
    ]
}

AVAILABLE SOURCE CONTEXT:

Narratives:
1. SEC Enforcement Actions Against Major Exchanges
   Summary: The SEC issued enforcement action against both Binance and Coinbase
   claiming they operated as unregistered securities exchanges by offering staking
   services. The commission argues staking services should be regulated as securities.
   This is the most significant regulatory action this quarter and affects ~60% of
   US exchange volume according to reporting...
   Entities: SEC, Binance, Coinbase

2. BlackRock Bitcoin ETF Reaches $5B AUM
   Summary: BlackRock's iShares Bitcoin Trust ETF (ticker: IBIT) has attracted
   $5.2 billion in assets since launch, signaling strong institutional demand...
   Entities: BlackRock, Bitcoin

Trending Signals:
- Bitcoin: score=0.82, velocity=52%
- Ethereum: score=0.71, velocity=38%

Detected Patterns:
- Regulatory news causes 1-2 day volatility swings but doesn't reverse
  longer institutional adoption trends

---

REFINEMENT INSTRUCTIONS:
- Return ONLY valid JSON
- Use ONLY the source context above
- Remove unsupported claims entirely
- Start with SEC enforcement (most significant)
- Explain why it matters for market structure
- Return ONLY valid JSON.
```

---

## Design Principles

### 1. Grounding (Anti-Hallucination)
- **Explicit "ALLOWED NARRATIVES" section** lists every valid narrative title
- **Available entities extracted** from narratives and listed in critique
- **Repeated reminders:** "ONLY use facts from the provided narratives"
- **Refinement prompt includes full source context** so model can't invent details

### 2. Explicitness Over Vagueness
- **Rule 1:** Full entity names every time, never "the exchange"
- **Rule 10:** No unnamed entities, no implied counts
- **Critique item 9:** Explicitly checks for vague references
- **Refinement:** Removes unsupported claims entirely

### 3. Context & Reasoning
- **Rule 2:** "Why it matters" mandatory for every development
- **Rule 4:** Copy specific details from summaries, don't paraphrase
- **Rule 11:** Figure plausibility checks against $2-3T market cap
- **Critique item 3:** Checks if implications are explained

### 4. Quality Control (Multi-Pass)
- **Generation:** Create initial briefing with all context available
- **Critique:** Evaluate 10 quality dimensions
- **Refinement:** Fix issues with full source context (up to 2 iterations)
- **Save:** Only after quality gates pass (or max iterations reached)

### 5. Reproducibility
- **All inputs in prompts:** Narratives, signals, patterns included
- **No external knowledge assumed:** Everything needed is in the prompt
- **Recommendations matched to narratives** (FEATURE-035): Enables UI to link to full narrative documents

---

## Quality Improvements (Sprint 15)

### BUG-081: Briefing Quality Guardrails
- Added Rule 9: Consolidate duplicate events (prevent same event reported twice)
- Added Rule 10: No unnamed entities (every reference must be explicit)
- Added Rule 11: Figure plausibility validation (flag $50B+ extremes)
- Enhanced critique to check for unnamed entities and duplicates
- Consolidated accounts for same-event narratives

### BUG-082: Post-Generation Plausibility Check
- Regex pattern to detect implausible financial figures
- $50B threshold for liquidations/hacks (flag for editor review)
- Manual review flags for historically unprecedented figures

### FEATURE-035: Narrative ID Matching
- Recommendations matched to narrative ObjectIDs in MongoDB
- Enables UI to link briefing recommendations to full narratives
- Case-insensitive title matching for robustness

---

## Cost Profile

### Per Briefing

| Phase | Call | Input Tokens | Output Tokens | Cost |
|-------|------|--------------|---------------|------|
| Generation | 1 | 1-2K | 500-1K | ~$0.001 |
| Critique | 1 | 1-2K | 200-400 | ~$0.0005 |
| Refinement | 1-2 | 2-3K each | 500-1K each | ~$0.001-0.002 |
| **Total** | **3-4** | **~4-7K** | **~1.2-2.4K** | **~$0.002-0.004** |

**Cost notes:**
- Haiku pricing: ~$0.80/$24 per 1M input/output tokens
- Sonnet fallback (~2x cost) only if Haiku fails
- Critique call is cheapest (lowest token count)
- Refinement is most expensive (full source context)

---

## Quality Guarantees

✅ **No hallucinated companies/events** — Explicit narrative allowlist  
✅ **No unnamed entities** — Rule 10 + Critique item 9  
✅ **No generic filler** — Rule 5 + Critique item 6  
✅ **Specific details from source** — Rule 4 + Refinement grounding  
✅ **All claims explained** — Rule 2 + Critique item 3  
✅ **Plausible figures only** — Rule 11 + BUG-082  
✅ **No duplicate events** — Rule 9 + Critique item 8  
✅ **Recommendations grounded** — Rule 8 + FEATURE-035  

---

## Debugging

### Briefing is Hallucinating
- Check "ALLOWED NARRATIVES" list in generation prompt
- Verify critique is catching unsupported claims
- Inspect refinement — is full source context provided?

### Entities Are Vague
- Check Rule 1 enforcement in generation
- Verify critique checks for "the platform", "the exchange"
- Look at refinement source context — are entity names available?

### Generic Filler Present
- Rule 5 banned phrases not in system prompt?
- Critique not checking for "evolving landscape"?
- Check generation prompt final reminders

### Recommendations Don't Match Narratives
- FEATURE-035 matching working? Check briefing_agent.py:870-911
- Case sensitivity issue in title matching?
- Narrative title in output != allowed narrative title?

---

## Related Documentation

- **[40-processing.md](docs/_generated/system/40-processing.md)** — Narrative construction (feeds briefing generation)
- **[60-llm.md](docs/_generated/system/60-llm.md)** — LLM gateway and model selection
- **[PROMPT_RELIABILITY_GUIDE.md](docs/PROMPT_RELIABILITY_GUIDE.md)** — Prompt design best practices
- **briefing_agent.py** — Full implementation

---

*Last updated: 2026-05-16*  
*Sprint: 15 (BUG-081, BUG-082, FEATURE-035)*
