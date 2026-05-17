# Prompt Reliability & Predictability Guide

## Overview

This system uses **constraint-based prompts** designed for **reliability and predictability**, not just "getting a good output once." Each prompt is engineered to produce consistent, repeatable results across millions of API calls and edge cases.

The distinction is critical: **One-shot prompts** chase quality in isolation; **production prompts** optimize for *predictable minimum quality* across all conditions.

---

## Core Prompts in the System

### 1. **Briefing Generation System Prompt**
**Location:** `src/crypto_news_aggregator/services/briefing_agent.py:533-633`

#### Purpose
Generate a daily crypto market briefing that synthesizes narratives without hallucination.

#### Reliability Features

**A. ZERO TOLERANCE HALLUCINATION GUARD**
```
✓ ONLY discuss narratives explicitly listed in the data below
✓ ONLY use facts, names, and details that appear in those narratives
✗ NEVER add companies, people, events, or facts from your training knowledge
✗ NEVER mention entities unless they appear in the narratives below
```

**Why this works:** The prompt doesn't just ask for "no hallucination"—it's **specific about what defines hallucination** (facts from training, unstated entities). This transforms a fuzzy goal ("be accurate") into a measurable constraint ("only these entities, only these narratives").

**B. MANDATORY ENTITY NAMING**
```
1. SPECIFIC ENTITY REFERENCES (NEW - CRITICAL)
   - ALWAYS use full entity names: "Binance", "BlackRock", "Cardano"
   - NEVER use vague references: "the platform", "the exchange", "the network"
   - If an entity is mentioned multiple times, use its name each time
```

**Why this works:** Vague references like "the platform" create ambiguity—readers can't verify facts, and subsequent models can't route correctly. Forcing **every entity to be named explicitly** makes the briefing:
- Verifiable against source narratives
- Parseable by downstream systems
- Resistant to entity confusion in follow-up operations

**C. "WHY IT MATTERS" REQUIREMENT**
```
2. EXPLAIN "WHY IT MATTERS" (MANDATORY)
   - Every significant development MUST include its implications
   - Connect events to broader market trends or investor decisions
```

**Why this works:** Without this, the model generates factually correct but useless briefings like "Binance expanded stablecoin offerings" (correct, but so what?). The requirement forces causal reasoning, making the output both **more useful and more predictable** (the model can't bury important implications in vague language).

**D. FIGURE PLAUSIBILITY CHECK**
```
11. VERIFY FIGURE PLAUSIBILITY
    - Before citing any financial figure, consider whether it is plausible given the total crypto market cap (~$2-3T)
    - A single-event liquidation exceeding $50B, a hack exceeding $10B, or similar extremes are almost certainly errors in the source data
```

**Why this works:** This catches hallucinations **by proxy**—if the LLM cites a $100B hack from source articles that only mention $1M, it's a sign of confusion or data error. The plausibility anchor grounds the model in reality without requiring it to reject data outright.

---

### 2. **Self-Critique Prompt**
**Location:** `src/crypto_news_aggregator/services/briefing_agent.py:721-776`

#### Purpose
Review generated briefings for 10 specific quality issues before refinement.

#### Reliability Features

**A. EXPLICIT ISSUE CATEGORIES**
Rather than "review for quality," the prompt lists exactly 10 things to check:
1. Hallucination
2. Vague entity references
3. Missing "why it matters"
4. Vague claims
5. Missing context
6. Generic filler
7. Abrupt transitions
8. Duplicate events
9. Unnamed entities
10. Implausible figures

**Why this works:** Each category is **measurable and specific**. The model doesn't have to guess what "quality" means—it compares the briefing against concrete criteria. This turns critique from art ("is this good?") into engineering ("does it pass these 10 tests?").

**B. PROVIDED REFERENCE MATERIALS**
```
AVAILABLE NARRATIVES (the only valid sources):
[list of narrative titles]

AVAILABLE ENTITIES (the only entities that can be mentioned):
[set of entities from narratives]
```

**Why this works:** By providing the valid set of entities and narratives, the critique model can **objectively verify** whether the briefing stayed in bounds. It doesn't have to infer what was available—it has the ground truth.

**C. STRUCTURED OUTPUT**
```json
{
  "needs_refinement": true/false,
  "issues": ["issue1", "issue2"],
  "suggestions": ["suggestion1", "suggestion2"]
}
```

**Why this works:** Forcing JSON output makes the result **machine-parseable** and removes ambiguity. The calling code can definitively check `needs_refinement` without parsing English.

---

### 3. **Refinement Prompt**
**Location:** `src/crypto_news_aggregator/services/briefing_agent.py:795-868`

#### Purpose
Fix issues identified by critique using full source context (narratives, signals, patterns).

#### Reliability Features

**A. PROVIDE FULL SOURCE CONTEXT IN PROMPT**
```
Narratives (facts you may reference):
1. Bitcoin Hits New ATH
   Articles: 47
   Summary: [full summary text]
   Entities: Bitcoin, Michael Saylor, Marathon Digital

2. SEC Delays Bitcoin ETF Decision
   ...
```

**Why this works:** The refinement model doesn't ask for "please fix the hallucination"—it gets **all the facts it needs to fix it** inline. The model can't cite a missing article because all articles are provided. It can't invent entities because all valid entities are listed.

**B. EXPLICIT CONSTRAINTS**
```
REFINEMENT INSTRUCTIONS:
- Return ONLY valid JSON in the same format as the original briefing
- Do NOT ask for additional data or context
- Use ONLY the source context provided above
- If a claim is not supported by the source context, REMOVE it
```

**Why this works:** These constraints prevent **hedging and excuse-making**. The model can't say "I need more data"—all data is present. It can't add caveats—only use provided sources. This forces a **deterministic refinement** where quality improves predictably.

---

### 4. **Entity Extraction Prompt**
**Location:** `src/crypto_news_aggregator/llm/optimized_anthropic.py:127-167`

#### Purpose
Extract only primary entities relevant to an article's core narrative.

#### Reliability Features

**A. EXPLICIT EXCLUSION RULES**
```
CRITICAL: Extract only entities relevant to the article's core narrative. Ignore:
- Entities mentioned in passing or as background context
- Tangential references (e.g., "Bitcoin fell, and also interest rates rose")
- Infrastructure/supporting entities not central to the story
```

**Why this works:** This prevents the model from doing "mention-level extraction" (list every entity mentioned) and forces **relevance-weighted extraction** (only entities central to the story). A model with this constraint will extract 3-5 entities from a complex article; a model without it will extract 15-20 and pollute downstream systems.

**B. WORKED EXAMPLE WITH ANTI-PATTERN**
```
EXAMPLE:
Article: "Solv Protocol integrated with Utexo to launch bitcoin-native yield with atomic swaps... uses RGB protocol and Lightning Network..."

WRONG (mention-level): [Bitcoin, Solv Protocol, Utexo, USDT, RGB protocol, Lightning Network]
CORRECT (relevance-weighted): [Bitcoin, Solv Protocol, Utexo]
   (RGB protocol and Lightning Network are supporting infrastructure, not primary entities)
```

**Why this works:** Showing both the wrong answer and the right answer, with reasoning, **trains the model's judgment** about what "relevant" means. It doesn't just say "be relevant"—it demonstrates the threshold.

---

### 5. **Narrative Extraction Prompt**
**Location:** `src/crypto_news_aggregator/llm/optimized_anthropic.py:229-252`

#### Purpose
Extract narrative structure (nucleus entity, actors, tensions, actions) from articles.

#### Reliability Features

**A. STRUCTURED DEFINITIONS**
```
Nucleus entity: The primary subject (most important entity)
Actors: Key entities in the story
Actor salience: Importance score 1-5 (5 = most important)
Tensions: Conflicts, themes, or concerns
Actions: Key events or verbs
```

**Why this works:** Each field has a **precise definition** that's easy to verify. If the nucleus entity is "Interest Rates" for an article about Bitcoin mining, that's clearly wrong. Definitions make the output **testable**.

---

### 6. **Narrative Summary Prompt**
**Location:** `src/crypto_news_aggregator/llm/optimized_anthropic.py:313-333`

#### Purpose
Summarize 10 related articles into a coherent narrative.

#### Reliability Features

**A. EXPLICIT GROUNDING CONSTRAINTS**
```
CRITICAL: Your summary must describe only events, facts, and claims that are 
explicitly stated in the provided articles. Do not infer, speculate, or add 
events not present in the source text. If the articles describe an IPO filing, 
summarize the IPO filing — do not introduce security breaches, hacks, lawsuits, 
or other events unless they are explicitly described in the articles.
```

**Why this works:** This is ultra-specific—it gives examples of what NOT to do ("don't introduce hacks unless explicitly described"). The model can't justify inference by claiming it's "inferring broader context"; only explicit facts are allowed.

**B. FIGURE VERIFICATION REQUIREMENT**
```
Verifies financial figures are consistent across articles — if sources disagree 
on a number, note the discrepancy rather than picking one
```

**Why this works:** Instead of asking the model to "verify accuracy," it tells it **what to do with conflicts**. If three articles cite different acquisition prices, the prompt doesn't let the model pick the most dramatic one—it forces disclosure of disagreement. This produces **conservative, traceable summaries**.

**C. DETECTION IN CODE (Defense in Depth)**
After the prompt, the code also does:
```python
for match in re.finditer(r'\$(\d[\d,.]*)\s*(billion|B|trillion|T)\b', summary):
    if value > 50:
        logger.warning(f"SUSPICIOUS FIGURE in narrative summary: {match.group(0)}")
```

**Why this works:** The prompt constrains the model; the code catches failures. This is **defense in depth**—if the model hallucinates a $100B hack despite the prompt, the system logs it for investigation.

---

## Principles Behind Reliable Prompts

### 1. **Specificity Over Generality**
- ❌ "Don't hallucinate" (vague, unmeasurable)
- ✅ "ONLY use facts from the provided narratives; if you cite something not listed here, the output is invalid" (measurable, bounded)

### 2. **Constraints as Features**
- ❌ "Write a good briefing" (open-ended)
- ✅ "Write a briefing with mandatory entity naming, mandatory 'why it matters' sections, and no unnamed entities" (constrained, verifiable)

### 3. **Worked Examples for Judgment**
- ❌ "Extract relevant entities" (model must infer relevance)
- ✅ "Extract relevant entities. WRONG example shows mention-level extraction. CORRECT example shows relevance-weighted extraction" (model learns by contrast)

### 4. **Layered Verification**
- Prompt constraints: Model is instructed to validate
- Code-level checks: Post-processing flags anomalies (e.g., $50B+ figures)
- Schema enforcement: JSON must parse; required fields must exist
- Human-in-the-loop: For critical operations (refinement), humans can review traces

### 5. **No Open-Ended Requests**
- ❌ "Feel free to add context if it helps"
- ✅ "Do NOT ask for additional data or context; use ONLY what is provided"

Explicitly forbidding extensions makes the model **predictable**. It can't hedge, speculate, or exceed bounds.

---

## How These Principles Enable Reliability

### Scenario: Entity Hallucination

**Without constraints:**
```
Original briefing: "Bitcoin rallied 15% as institutional investors shifted portfolios"
Model hallucinates: "Bitcoin rallied 15% as BlackRock and Grayscale shifted portfolios"
  (Training says BlackRock often invests in Bitcoin, so the model adds it)
```

**With constraints:**
```
Original briefing: "Bitcoin rallied 15% as institutional investors shifted portfolios"
Model sees constraint: "ONLY use facts, names, and details that appear in the provided narratives"
Model checks: Is "BlackRock" in the narrative list? No.
Model rejects: Cannot mention BlackRock.
Output: "Bitcoin rallied 15% as institutional investors shifted portfolios" ✓
```

### Scenario: Vague References

**Without constraints:**
```
Generated: "The platform expanded its offerings to compete with competitors"
(Reader: Which platform? Binance? Kraken? Gemini?)
```

**With constraint:**
```
Generated: "Binance expanded its stablecoin offerings; Kraken began supporting USDC withdrawals"
(Specific entities; verifiable against narratives)
```

### Scenario: Unsupported Claims

**Without constraints:**
```
Briefing: "The market showed strong recovery as institutions capitalized on the dip"
(This sounds right, but is there evidence in the source articles?)
```

**With constraints:**
```
Refinement model receives full narrative text.
Claims must reference facts from provided summaries.
If summaries don't mention "dip" or "recovery," the claim can't be made.
```

---

## Implementation in Code

### Briefing Agent Flow
1. **Generate:** System prompt constraints → Haiku produces initial briefing
2. **Critique:** 10-point rubric → Critique model identifies issues
3. **Refine:** Full source context + constraints → Refined briefing
4. **Validate:** Schema check (JSON parses) + plausibility check (no $100B+ figures) + human review (if smoke test)

### Entity Extraction Flow
1. **Extract:** Relevance constraint + worked example → Haiku extracts primary entities only
2. **Normalize:** Code-level mapping (BTC → Bitcoin)
3. **Deduplicate:** Downstream service removes redundant extractions

### Narrative Summary Flow
1. **Summarize:** Grounding constraint + figure verification requirement → Haiku generates summary
2. **Detect:** Code-level regex checks for implausible figures
3. **Log:** Flagged figures go to observability for investigation

---

## Measuring Reliability

These prompts enable:

1. **Consistency:** Same article → Same entities across 100 API calls (caching + deterministic constraints)
2. **Boundary Respect:** Briefing can only mention entities in the provided narrative list (verifiable)
3. **Traceability:** Every claim in briefing maps to a source narrative (due to constraints)
4. **Debuggability:** If briefing is wrong, we know which stage failed (generate/critique/refine) and can review the prompt vs. output

---

## Key Takeaway

**Production prompts optimize for reliability and predictability:**
- **Reliability:** Same inputs → reliably similar outputs (due to constraints, not luck)
- **Predictability:** Failures are detectable (plausibility checks, schema validation, explicit constraints)
- **Debuggability:** When things go wrong, we can trace why (prompt constraint violated? Schema error? Thresholds exceeded?)

Compare with one-shot quality optimization, which optimizes for "best-case output" but is fragile to edge cases, distribution shifts, and model updates. These prompts are **robust to variation** because they enforce **specific, measurable constraints at every step**.
