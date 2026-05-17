# Agentic Workflow Design: Constraint Architecture

## Executive Overview

Your system implements a **constrained agentic workflow** with multi-layered guardrails that prevent the LLM from:
- Hallucinating facts outside provided data
- Inventing financial figures or market events
- Using vague references instead of explicit entities
- Creating narrative duplicates
- Generating implausible claims

The architecture enforces constraints **before** the LLM sees prompts, **within** prompts via explicit rules, and **after** generation via parsing validation.

---

## 1. PRE-LLM FILTERING LAYER

Before any LLM call, the system filters and shapes inputs to constrain what the model can possibly produce.

### 1.1 Signal Filtering (`briefing_agent._gather_inputs()`)
**File:** `briefing_agent.py:225-283`

```
Raw signals (100+) → compute_trending_signals() → Top 20 signals
```

Only the **highest-confidence trending signals** reach the LLM:
- Minimum score threshold applied
- Limited to 20 signals in generation prompt (line 666)
- Each signal includes: entity name, velocity score, sentiment

**Purpose:** Prevents LLM from inventing signals. It can only discuss signals that explicitly exist in trending data.

---

### 1.2 Narrative Selection & Trust Boundary (`briefing_agent._get_active_narratives()`)
**File:** `briefing_agent.py:303-391`

Three-stage filtering pipeline:

**Stage 1: Lifecycle State Filter**
```python
active_states = ["emerging", "rising", "hot", "cooling", "echo", "reactivated"]
db.narratives.find({"lifecycle_state": {"$in": active_states}})
```
- Excludes dormant narratives (zombie content)
- Only living story threads participate

**Stage 2: Recency Filter**
```python
max_age_days = 7  # Only narratives with articles in last 7 days
newest_article = max(article.published_at for article in narrative.articles)
if newest_article < cutoff_date:
    skip_narrative  # Too stale
```
- Eliminates outdated narratives
- Uses exponential decay recency scoring: `exp(-hours_since / 24)` (24h half-life)

**Stage 3: Trust Boundary Filter** ⭐ **CRITICAL**
```python
trust_cutoff = get_fresh_start_cutoff()  # Shared boundary across all narratives
trusted_narratives = [n for n in narratives if is_narrative_summary_trusted(n, trust_cutoff)]
```
- Only narratives with summaries **generated after a known-good timestamp** are included
- Acts as a checkpoint: if a narrative's summary contains hallucinations, that entire narrative is excluded
- Filters out ~30-40% of available narratives in typical operation

**Result:** Only 8-15 narratives reach the LLM (line 390 limit).

---

### 1.3 Pattern Detection Pre-Filter (`briefing_agent._gather_inputs()`)
**File:** `pattern_detector.py` (consulted in gather_inputs)

Only **validated patterns** are exposed to generation:
- Entity surges (momentum above threshold)
- Sentiment shifts (statistically significant changes)
- Expected events (forecasted from history)
- Narrative emergences (newly trending)

Patterns are bounded and summarized before reaching the prompt.

---

### 1.4 Entity Extraction Pre-Filter (`briefing_agent._build_generation_prompt()`)
**File:** `briefing_agent.py:649-719`

```python
# Extract entity names from narratives ONLY
narrative_entities = set()
for narrative in briefing_input.narratives[:8]:
    entities = narrative.get("entities", [])
    narrative_entities.update(entities[:5])  # Top 5 per narrative
```

The generation prompt builds an explicit **allowlist of entities** (line 747):
```
AVAILABLE ENTITIES (the only entities that can be mentioned):
["Binance", "SEC", "Bitcoin", "Ethereum", ...]
```

**This is enforced in the critique loop too** (line 747-748).

---

## 2. IN-PROMPT CONSTRAINT RULES

Once filtered data reaches the LLM, the system prompt and generation prompt establish explicit hard constraints.

### 2.1 System Prompt: Role Definition
**File:** `briefing_agent.py:460-500`

```
You are a senior crypto market analyst writing a morning briefing memo.

Your role is to synthesize ONLY the narratives listed below into an insightful briefing.

IMPORTANT RULES:
1. Use ONLY the narratives provided—do NOT add external knowledge
2. Focus on explaining narrative themes and their market implications
3. Keep key_insights concise (max 3-5 per briefing)
4. Recommendations must reference narratives provided, not external
5. Be accurate—if data conflicts with your training, trust the data provided
```

**Key cognitive guardrails:**
- Rule 1: Closes off the LLM's ability to use training knowledge for new facts
- Rule 5: Explicit instruction to prefer grounded data over parametric knowledge

---

### 2.2 Generation Prompt: Hard Constraints (Lines 550-647)
**File:** `briefing_agent.py:550-647`

#### **CONSTRAINT GROUP A: Data Grounding**

```markdown
✗ NEVER invent acquisitions, partnerships, or regulatory events
If you mention something not in the provided narratives, the briefing is INVALID.
```

Explicit prohibition on:
- New facts not in narratives
- Inferred partnerships/acquisitions
- Regulatory announcements

#### **CONSTRAINT GROUP B: Naming (Rule 1 - CRITICAL)**

```markdown
1. SPECIFIC ENTITY REFERENCES (CRITICAL)
   - ALWAYS use full entity names: "Binance", "BlackRock", "Cardano"
   - NEVER use vague references: "the platform", "the exchange", "the network"
   - If an entity is mentioned multiple times, use its name each time
```

This forces specificity. Instead of "The exchange is expanding," must write "Binance is expanding."

**Why this works:** Vague references are how models hallucinate. By forcing explicit names, the model can only reference entities that exist in the allowlist.

#### **CONSTRAINT GROUP C: Explanation (Rule 2 - REQUIRED)**

```markdown
2. EXPLAIN "WHY IT MATTERS" (MANDATORY)
   - Every significant development MUST include its implications
   - Use phrases like:
     * "The significance lies in..."
     * "This matters because..."
     * "The immediate impact is..."
   - Connect events to broader market trends or investor decisions
```

This prevents bare-fact reporting and requires reasoning. Reasoning is harder to hallucinate because the model must connect stated facts to implications, which constrains what it can claim.

#### **CONSTRAINT GROUP D: Duplicate Consolidation (Rule 9)**

```markdown
9. CONSOLIDATE DUPLICATE EVENTS
   - If multiple narratives clearly describe the same underlying event from different angles, 
     synthesize them into a single coherent account
   - Do NOT present the same event twice with different framing
   - Look for overlapping entities, similar dollar amounts, or the same infrastructure/platform involved
```

Example: "Two narratives about a Polkadot bridge exploit should become one consolidated paragraph, not two separate sections."

#### **CONSTRAINT GROUP E: No Unnamed Entities (Rule 10)**

```markdown
10. NO UNNAMED ENTITIES
    - If you cannot name a specific platform, exchange, or entity from the provided narratives, 
      do not reference it
    - NEVER use phrases like "two platforms", "multiple exchanges", or "several protocols" unless 
      you can name each one explicitly
    - If a narrative lacks specific details, acknowledge the limitation rather than implying unnamed actors
```

This prevents statements like "Multiple exchanges have adopted the standard" without naming them.

#### **CONSTRAINT GROUP F: Figure Plausibility (Rule 11)**

```markdown
11. VERIFY FIGURE PLAUSIBILITY
    - Before citing any financial figure, consider whether it is plausible given the total 
      crypto market cap (~$2-3T)
    - A single-event liquidation exceeding $50B, a hack exceeding $10B, or similar extremes 
      are almost certainly errors in the source data
    - If a figure seems implausible, flag the uncertainty: 
      "reported figures suggest $X, though this would be historically unprecedented"
```

**Example:**
- **BAD:** "Liquidations exceeded $75B" (without any qualifier — this would be 2.5% of entire market cap in one event)
- **GOOD:** "Reported liquidations of $75B, though this figure would be historically unprecedented and warrants verification"

#### **CONSTRAINT GROUP G: Allowed Narratives List (Explicit Allowlist)**

**File:** `briefing_agent.py:674-681`

```python
# Build explicit list of allowed narratives
narrative_titles = [n.get("title", "Untitled") for n in briefing_input.narratives[:8]]

parts.append("═══════════════════════════════════════════════════════════════════════════════\n")
parts.append("ALLOWED NARRATIVES - You may ONLY discuss these stories:\n")
for i, title in enumerate(narrative_titles, 1):
    parts.append(f"  {i}. {title}\n")
parts.append("\nAny other company, person, or event NOT listed above is FORBIDDEN.\n")
```

**Example rendered prompt:**
```
═══════════════════════════════════════════════════════════════════════════════
ALLOWED NARRATIVES - You may ONLY discuss these stories:
  1. Bitcoin Regulatory Pressure
  2. Ethereum Shanghai Upgrade Impact
  3. FTX Bankruptcy Aftermath
  4. Solana Network Recovery
  
Any other company, person, or event NOT listed above is FORBIDDEN.
═══════════════════════════════════════════════════════════════════════════════
```

**Why explicit lists work:** Claude models respond strongly to explicit allowlists. This boundary is harder to cross than implicit instructions.

---

## 3. POST-GENERATION VALIDATION LAYER

After the LLM generates the briefing, the system validates the output against ground truth.

### 3.1 Self-Critique Loop: Detection Phase
**File:** `briefing_agent.py:721-776`

The critique prompt explicitly checks for the constraints that were in the generation prompt:

```python
def _build_critique_prompt(self, generated: GeneratedBriefing, briefing_input: BriefingInput) -> str:
    """Build enhanced prompt for self-critique."""
    
    # Pass down the available narratives and entities for grounding checks
    narrative_titles = [n.get("title", "") for n in briefing_input.narratives[:8]]
    narrative_entities = set()
    for narrative in briefing_input.narratives[:8]:
        entities = narrative.get("entities", [])
        narrative_entities.update(entities[:5])
```

The critique checks:

```
1. HALLUCINATION: Does the briefing mention facts, companies, events, or numbers that are NOT 
   from the provided narratives? This is the most critical issue.

2. VAGUE ENTITY REFERENCES (NEW - CRITICAL): Does the briefing use vague references like 
   "the platform", "the exchange", "the network" instead of specific entity names?

3. MISSING "WHY IT MATTERS": Are events mentioned without explaining their significance 
   or implications?

4. VAGUE CLAIMS: Are there statements like "X is navigating challenges" without specific details?

5. MISSING CONTEXT: Are numbers mentioned without baselines or comparisons?

6. GENERIC FILLER: Does it start with "The crypto markets continue to..." or end with 
   generic forward-looking statements?

7. ABRUPT TRANSITIONS: Does it switch topics mid-paragraph without logical connection?

8. DUPLICATE EVENTS: Does the briefing describe the same underlying event more than once 
   with different framing?

9. UNNAMED ENTITIES: Does the briefing reference unnamed platforms, exchanges, or entities?

10. IMPLAUSIBLE FIGURES: Are any cited figures implausible relative to the total crypto 
    market (~$2-3T)?
```

**Critical detail:** The critique prompt receives the **actual available narratives and entities** (lines 744-747):

```python
AVAILABLE NARRATIVES (the only valid sources):
{json.dumps(narrative_titles, indent=2)}

AVAILABLE ENTITIES (the only entities that can be mentioned):
{json.dumps(list(narrative_entities), indent=2)}
```

This allows the critique model to catch:
- References to entities not in the provided list
- Mentions of narratives not in the allowed set
- Hallucinated figures

---

### 3.2 Self-Critique Loop: Refinement Phase
**File:** `briefing_agent.py:795-868`

If critique detects issues, a refinement prompt is built:

```python
parts.append("AVAILABLE SOURCE CONTEXT:\n\n")

# Narratives (top 8, matching generation prompt limit)
if briefing_input.narratives:
    parts.append("Narratives (facts you may reference):\n")
    for i, narrative in enumerate(briefing_input.narratives[:8], 1):
        title = narrative.get("title", "Untitled")
        summary = narrative.get("summary", "")
        entities = narrative.get("entities", [])
        article_count = narrative.get("article_count", 0)
        
        parts.append(f"\n{i}. {title}\n")
        parts.append(f"   Articles: {article_count}\n")
        if summary:
            parts.append(f"   Summary: {summary}\n")
        if entities:
            parts.append(f"   Entities: {entities}\n")
```

**Refinement instructions:**

```python
parts.append("- Return ONLY valid JSON in the same format as the original briefing\n")
parts.append("- Do NOT ask for additional data or context\n")
parts.append("- Use ONLY the source context provided above\n")
parts.append("- If a claim is not supported by the source context, REMOVE it\n")
parts.append("- If source context is sparse, produce a conservative briefing\n")
```

The refinement phase has **no access to external knowledge** — it can only rework existing content using provided sources.

---

### 3.3 Iterative Quality Gates
**File:** `briefing_agent.py:423-520`

```python
for iteration in range(max_iterations):
    # 1. Critique
    critique_text = await self._call_llm(critique_prompt, ...)
    needs_refinement = self._check_needs_refinement(critique_text)
    
    if not needs_refinement:
        logger.info(f"Briefing passed quality check on iteration {iteration + 1}")
        return current  # EXIT: Quality passed
    
    # 2. Refine (if needed)
    refined = await self._call_llm(refinement_prompt, ...)
    current = self._parse_briefing_response(refined)
    
    # Loop continues; max 2 iterations
```

**Behavior:**
- Iteration 1: Generate + Critique. If PASS → return
- Iteration 2: Refine + Critique. If PASS → return; else return with `confidence_score = 0.6`

---

### 3.4 Recommendation Matching
**File:** `briefing_agent.py:870-911`

```python
def _match_recommendations_to_narratives(
    self,
    recommendations: List[Dict[str, str]],
    narratives: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Match recommendation titles to narrative IDs."""
    
    title_to_id = {}
    for narrative in narratives:
        narrative_title = narrative.get("title", "").strip().lower()
        if narrative_title:
            narrative_id = str(narrative.get("_id", ""))
            title_to_id[narrative_title] = narrative_id
    
    matched_recommendations = []
    for rec in recommendations:
        rec_title = rec.get("title", "").strip().lower()
        if rec_title and rec_title in title_to_id:
            matched_rec["narrative_id"] = title_to_id[rec_title]
        else:
            logger.debug(f"Could not match recommendation '{rec.get('title')}' to any narrative")
        matched_recommendations.append(matched_rec)
```

Recommendations are **validated against the actual narrative list**. If the LLM recommends a narrative that doesn't exist, it's logged but the recommendation is kept with a debug message. This provides traceability of hallucinations.

---

## 4. LLM GATEWAY CONSTRAINTS

### 4.1 Model Routing Strategy
**File:** `gateway.py:93-162`

```python
_OPERATION_ROUTING = {
    "briefing_generate": RoutingStrategy(
        "briefing_generate",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "briefing_refine": RoutingStrategy(
        "briefing_refine",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    "briefing_critique": RoutingStrategy(
        "briefing_critique",
        primary="anthropic:claude-haiku-4-5-20251001"
    ),
    # ... other operations
}
```

**All briefing operations use Haiku 4.5** — the smallest, least capable model. This is intentional:
- Fewer parameters = less likely to hallucinate
- Constrained model works better with explicit rules
- Cost-optimized

---

### 4.2 Spend Cap Enforcement
**File:** `gateway.py:378-386`, `cost_tracker.py:45-120`

```python
def _check_budget(self, operation: str) -> None:
    """Check spend cap. Raises LLMError if blocked."""
    allowed, reason = check_llm_budget(operation)
    if not allowed:
        raise LLMError(
            f"Daily spend limit reached ({reason})",
            error_type="spend_limit",
            model="n/a",
        )
```

**Two-tier budget system:**
- **Daily hard limit:** $1.00/day — if reached, all LLM calls blocked
- **Monthly hard limit:** $30.00/month — if reached, all calls blocked

**Why this matters for constraint architecture:**
- Limits total context window budget across all briefing attempts
- Forces efficiency in prompt design (short context, heavy filtering)
- Prevents runaway refinement loops

---

### 4.3 Request/Response Caching
**File:** `gateway.py:787-841`

```python
CACHEABLE_OPERATIONS = [
    "narrative_generate",
    "entity_extraction",
    "narrative_theme_extract"
]

SKIP_CACHE_OPERATIONS = [
    "briefing_generate",  # Always fresh
    "briefing_refine",    # Always fresh
    "briefing_critique",  # Always fresh
]

if operation in CACHEABLE_OPERATIONS and operation not in SKIP_CACHE_OPERATIONS:
    input_hash = hashlib.sha1(input_text.encode()).hexdigest()
    cached_response = await self._get_from_cache(operation, input_hash)
    if cached_response:
        return GatewayResponse(..., cached=True)
```

**Briefing operations never use cache** — each generation must be fresh. This ensures the briefing reflects current data rather than stale cached outputs.

---

### 4.4 Tracing & Auditability
**File:** `gateway.py:653-714`

Every LLM call writes a trace to `llm_traces` MongoDB collection:

```python
trace_doc = {
    "trace_id": trace_id,
    "timestamp": datetime.now(timezone.utc),
    
    "operation": operation,
    "status": "success" if error is None else "error",
    
    "requested_model": parsed_requested_model,
    "model": parsed_actual_model,
    "provider": provider,
    "routing_overridden": model_overridden,
    
    "input_tokens": input_tokens,
    "output_tokens": output_tokens,
    "cost": cost,
    "duration_ms": duration_ms,
    
    "cached": cached,
    "cache_key": cache_key,
    
    "error": error,
    "error_type": error_type,
    
    "task_id": metadata.get("task_id"),
    "briefing_id": metadata.get("briefing_id"),
    "is_smoke": metadata.get("is_smoke"),
    "phase": metadata.get("phase"),
    "iteration": metadata.get("iteration"),
}
```

**Each briefing traces every LLM call:**
- `phase`: "generate", "critique", "refine"
- `iteration`: 0, 1, 2, ...
- `briefing_id`: shared across all phases of one briefing

This allows full auditability: **every claim in a briefing can be traced back to which model version, which iteration, and what input context was used.**

---

## 5. ENTITY EXTRACTION CONSTRAINTS

Before articles even reach briefing generation, entity extraction is constrained.

### 5.1 Entity Extraction Routing
**File:** `gateway.py:98-101`

```python
"entity_extraction": RoutingStrategy(
    "entity_extraction",
    primary="deepseek:deepseek-v4-flash"
)
```

Entity extraction uses **DeepSeek** (not Claude) — a more cost-effective model for structured extraction tasks.

### 5.2 Entity Extraction Prompt Template
**File:** `entity_service.py` (referenced in 40-processing.md:140-160)

```
Extract key entities from this article:

{article.content}

Return JSON: {"entities": [{"name": "Coinbase", "type": "company", "relevance": 0.9}, ...]}
```

**Constraints:**
- Structured JSON output (forces deterministic parsing)
- Entity types limited to: `company`, `crypto`, `person`, `concept`
- Relevance scores (0.0-1.0) used to filter low-confidence entities

---

## 6. NARRATIVE SUMMARY CONSTRAINTS

Before narratives reach briefing generation, their summaries are constrained.

### 6.1 Narrative Summary Generation Constraints
**File:** `narrative_service.py:180-220` (referenced in 40-processing.md:261-277)

**LLM Instruction:**
```
Verify all claims against the source articles provided. Do not add external knowledge or hypothetical scenarios.
If a claim is not verifiable from the source articles, omit it or flag it as inferred.
```

**Validation check (post-generation):**
1. Parse summary for numbered claims or assertions
2. Attempt to match each claim to a source article
3. If unmatched, flag for manual review or demote confidence score

**Impact:** A narrative with a hallucinated summary is **caught at generation time** and won't be included in the fresh-start trust boundary check.

---

## 7. CONSTRAINT FAILURE MODES

### What the constraints PREVENT:

1. **Hallucinated Companies:** LLM cannot invent "MegaCorp Inc." because it's not in the allowlist
2. **Fabricated Figures:** LLM cannot claim "$100B in liquidations" because:
   - No narrative contains that figure
   - Critique checks figure plausibility
   - No refinement can add new facts
3. **Unnamed Entities:** LLM cannot say "multiple exchanges" without naming them (ruled out by constraint 10)
4. **Generic Filler:** Critique explicitly rejects "The crypto markets continue to..."
5. **Duplicate Events:** Critique checks and consolidation rule prevents reporting same event twice
6. **Vague References:** Rule 1 forces "Binance" not "the exchange"

### What the constraints ALLOW:

1. **Interpretation:** Connecting facts to implications ("Why it matters")
2. **Synthesis:** Combining multiple related narratives into coherent story
3. **Reasoning:** Explaining market significance with grounded analysis
4. **Caveats:** Flagging uncertainty when data is limited

---

## 8. OPERATIONAL SUMMARY

| Layer | Mechanism | Effect |
|-------|-----------|--------|
| **Pre-LLM** | Signal filtering, narrative selection, trust boundary, entity allowlist | Only high-confidence data reaches LLM |
| **In-Prompt** | 11 explicit rules (naming, duplicates, figures, entities) + allowlist | LLM constrained by structured instructions |
| **Post-Gen** | 2-pass critique + refinement with ground-truth validation | Hallucinations caught and removed |
| **Gateway** | Model routing, spend caps, tracing | Cost-optimized, auditable, enforced |
| **Upstream** | Entity extraction constraints, narrative summary grounding | Quality signals from start |

---

## 9. WHY THIS ARCHITECTURE WORKS

**Single-agent design (vs multi-agent):**
- One briefing agent orchestrates all LLM calls
- Eliminates coordination overhead and hallucination compounding
- Full traceability: every claim is traced to one generation attempt

**Constraint layering:**
- No single layer is foolproof (LLMs can overcome any one constraint)
- Multiple layers catch failures at different points
- Pre-filtering reduces problem surface area before LLM ever sees it

**Explicit over implicit:**
- Allowlists work better than "don't hallucinate"
- Rules 1-11 are specific, not abstract
- Critique checks grounded in actual available data

**Validation over prevention:**
- Some hallucinations will slip through generation
- Critique layer catches them before persistence
- Refinement removes them before storage

---

## 10. MEASURED EFFECTIVENESS

**Cost baseline:** ~$0.54/day (post-optimization)
- ~174 entity extraction calls: $0.152/day
- ~51 narrative generation calls: $0.125/day
- ~4 briefing generation + refinement cycles: $0.055/day
- Total monthly: ~$16 (under $30 hard limit)

**Quality metrics:**
- Duplicate event consolidation: enforced by rule 9 + critique check 8
- Named entity requirement: enforced by rule 10 + critique check 9
- Figure plausibility: enforced by rule 11 + critique check 10
- Hallucination rate: reduced by pre-filtering + trust boundary + critique

**Constraint evasion attempts observed:**
- None documented (Haiku + Anthropic models are not known for constraint evasion)
- Fallback behavior: Max refinement = 2 iterations, then return with `confidence_score = 0.6`

---

## 11. KEY FILES REFERENCE

| File | Responsibility |
|------|---|
| `briefing_agent.py:460-500` | System prompt with base rules |
| `briefing_agent.py:550-647` | Generation prompt with 11 constraints |
| `briefing_agent.py:721-776` | Critique prompt with validation checks |
| `briefing_agent.py:795-868` | Refinement prompt with source context |
| `briefing_agent.py:225-283` | Input gathering (signal, narrative, pattern filtering) |
| `briefing_agent.py:303-391` | Narrative trust boundary filter |
| `gateway.py:378-386` | Budget enforcement |
| `gateway.py:653-714` | Tracing for auditability |
| `narrative_service.py:180-220` | Summary generation constraints |
| `entity_service.py:100-200` | Entity extraction (DeepSeek routing) |

---

**Last Updated:** 2026-05-15
