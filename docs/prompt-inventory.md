 # Crypto News Aggregator - Complete Prompt Inventory

   ## 1. BRIEFING GENERATION PROMPTS

   ### 1.1 System Prompt (briefing_agent.py:465-???)
   **Location:**
   `src/crypto_news_aggregator/services/briefing_agent.py:_get_system_prompt()`
   **Type:** System message for LLM context
   **Models:** Claude Haiku (primary), Claude Sonnet (fallback)
   **Key Features:**
   - Zero tolerance for hallucination
   - Requires entity-specific references (no "the exchange")
   - Mandatory "why it matters" explanations
   - Based on briefing_type (morning/evening)

   ### 1.2 Generation Prompt
   **Location:**
   `src/crypto_news_aggregator/services/briefing_agent.py:_build_generation_prompt()`
   **Type:** Main briefing content generation
   **Used by:** `_generate_with_llm()`
   **Key Requirements:**
   - Synthesis of ONLY provided narratives
   - No hallucinations
   - Include reasoning for recommendations

   ### 1.3 Critique Prompt
   **Location:**
   `src/crypto_news_aggregator/services/briefing_agent.py:_build_critique_prompt()`
   **Type:** Self-critique for quality assurance
   **Used by:** `_self_refine()` for iterative quality checks
   **Key Features:**
   - Evaluates briefing quality
   - Checks for hallucinations
   - Identifies issues for refinement

   ### 1.4 Refinement Prompt
   **Location:**
   `src/crypto_news_aggregator/services/briefing_agent.py:_build_refinement_prompt()`
   **Type:** Quality improvement iteration
   **Used by:** `_self_refine()` after critique identifies issues
   **Key Features:**
   - Implements multi-pass self-refine pattern
   - Improves on critique feedback
   - Max 2 iterations default

   ---

   ## 2. ENTITY EXTRACTION PROMPTS

   ### 2.1 Entity Extraction (optimized_anthropic.py)
   **Location:** `src/crypto_news_aggregator/llm/optimized_anthropic.py:_build_entity_extr
   action_prompt()`
   **Model:** Claude Haiku (cheap & fast, 12x cheaper than Sonnet)
   **Operation:** `entity_extraction`
   **Input:** Article title + text (truncated to 2000 chars)
   **Output Format:** JSON with:
   ```json
   {
     "entities": [
       {
         "name": "Bitcoin",
         "type": "cryptocurrency|protocol|company|person|event|regulation",
         "confidence": 0.95,
         "is_primary": true
       }
     ]
   }
   ```
   **Key Instructions:**
   - Extract crypto-related entities only
   - Normalize names (BTC → Bitcoin)
   - Only entities explicitly mentioned in text
   - Return ONLY valid JSON (no markdown)

   ---

   ## 3. NARRATIVE EXTRACTION & ANALYSIS PROMPTS

   ### 3.1 Narrative Elements Extraction (optimized_anthropic.py)
   **Location:** `src/crypto_news_aggregator/llm/optimized_anthropic.py:_build_narrative_e
   xtraction_prompt()`
   **Model:** Claude Haiku
   **Operation:** `narrative_extraction`
   **Input:** Article title + text
   **Output Format:** JSON with:
   ```json
   {
     "nucleus_entity": "Bitcoin",
     "actors": ["Bitcoin", "SEC", "Michael Saylor"],
     "actor_salience": {"Bitcoin": 5, "SEC": 4, "Michael Saylor": 3},
     "tensions": ["regulatory uncertainty"],
     "actions": ["filed lawsuit", "price surge"]
   }
   ```
   **Key Concepts:**
   - Nucleus entity: Primary subject
   - Actors: Key entities in story
   - Actor salience: Importance 1-5
   - Tensions: Conflicts/themes
   - Actions: Key events/verbs

   ### 3.2 Narrative Summary Generation
   **Location:**
   `src/crypto_news_aggregator/llm/optimized_anthropic.py:_build_summary_prompt()`
   **Model:** Claude Haiku
   **Operation:** `narrative_summary`
   **Input:** Multiple articles (up to 10)
   **Output:** 2-3 sentence summary
   **Critical Constraints:**
   - Describe ONLY events explicitly in articles
   - No inference or speculation
   - Note conflicting perspectives
   - Verify financial figures consistency
   - Do not introduce events not in source text
   - Only describe what's explicitly stated

   ### 3.3 Theme Analysis (narrative_themes.py)
   **Location:** `src/crypto_news_aggregator/services/narrative_themes.py:530`
   **Model:** Claude Haiku
   **Operation:** `theme_analysis`
   **Input:** Crypto news article
   **Output:** Primary themes identification
   **Used by:** Theme detection pipeline

   ### 3.4 Theme Summarization (narrative_themes.py)
   **Location:** `src/crypto_news_aggregator/services/narrative_themes.py:1007`
   **Input:** Articles sharing a common theme
   **Output:** Theme-based narrative summary
   **Key Feature:** Relates multiple articles to same theme

   ### 3.5 Narrative Summary Polish (narrative_themes.py)
   **Location:** `src/crypto_news_aggregator/services/narrative_themes.py:1466`
   **Input:** Summary text
   **Output:** 1-2 punchy sentences suitable for dashboard
   **Purpose:** Polish narrative summaries for UI display

   ### 3.6 Narrative System Prompt (narrative_themes.py)
   **Location:** `src/crypto_news_aggregator/services/narrative_themes.py:726`
   **Constant:** `NARRATIVE_SYSTEM_PROMPT`
   **Type:** System context for narrative analysis operations
   **Key Role:** Provides consistent context for narrative processing

   ---

   ## 4. SENTIMENT & SCORING PROMPTS

   ### 4.1 Sentiment Analysis (anthropic.py)
   **Location:** `src/crypto_news_aggregator/llm/anthropic.py:125`
   **Model:** Claude Haiku
   **Input:** Crypto text
   **Output:** Single number -1.0 (bearish) to 1.0 (bullish)
   **Format:** ONLY the number, no explanation
   **Operation:** `sentiment_analysis`

   ### 4.2 Theme Extraction (anthropic.py)
   **Location:** `src/crypto_news_aggregator/llm/anthropic.py:144`
   **Model:** Claude Haiku
   **Input:** Combined texts from articles
   **Output:** Comma-separated keywords (e.g., "Bitcoin, DeFi, Regulation")
   **Format:** No preamble, no markdown
   **Operation:** `theme_extraction`

   ### 4.3 Market Insight Generation (anthropic.py)
   **Location:** `src/crypto_news_aggregator/llm/anthropic.py:158`
   **Model:** Claude Haiku
   **Input:** Sentiment score + themes
   **Output:** 2-3 sentences for traders
   **Operation:** `market_insight`

   ### 4.4 Relevance Scoring (anthropic.py)
   **Location:** `src/crypto_news_aggregator/llm/anthropic.py:163`
   **Model:** Claude Haiku
   **Input:** Text
   **Output:** Float 0.0-1.0 (relevance to crypto market movements)
   **Format:** ONLY the number, no explanation
   **Operation:** `relevance_score`

   ---

   ## 5. BATCH PROCESSING PROMPTS

   ### 5.1 Batch Entity Extraction (anthropic.py)
   **Location:** `src/crypto_news_aggregator/llm/anthropic.py:238`
   **Model:** Claude Haiku
   **Input:** Multiple crypto news articles
   **Output:** ONLY valid JSON (no markdown)
   **Operation:** `batch_entity_extraction`
   **Optimization:** Batches reduce API calls

   ### 5.2 Batch Narrative Analysis (anthropic.py)
   **Location:** `src/crypto_news_aggregator/llm/anthropic.py:526`
   **Model:** Claude Haiku
   **Input:** Multiple cryptocurrency articles
   **Output:** ONLY valid JSON
   **Operation:** `batch_narrative_analysis`

   ---

   ## 6. LEGACY/UTILITY PROMPTS

   ### 6.1 Duplicate Sentiment Analysis (anthropic.py:692)
   **Note:** Duplicate of sentiment analysis at line 125
   **Location:** `src/crypto_news_aggregator/llm/anthropic.py:692`

   ### 6.2 Duplicate Theme Extraction (anthropic.py:755)
   **Note:** Duplicate of theme extraction at line 144
   **Location:** `src/crypto_news_aggregator/llm/anthropic.py:755`

   ### 6.3 Duplicate Relevance Scoring (anthropic.py:630)
   **Note:** Duplicate of relevance scoring at line 163
   **Location:** `src/crypto_news_aggregator/llm/anthropic.py:630`

   ---

   ## 7. MEMORY & PATTERN CONTEXT FORMATTING

   ### 7.1 Memory Prompt Context (memory_manager.py)
   **Location:**
   `src/crypto_news_aggregator/services/memory_manager.py:to_prompt_context()`
   **Type:** Format memory for LLM inclusion
   **Used by:** Briefing agent for context
   **Output:** Formatted string suitable for prompt injection

   ### 7.2 Pattern Detector Prompt Context (pattern_detector.py)
   **Location:**
   `src/crypto_news_aggregator/services/pattern_detector.py:to_prompt_context()`
   **Type:** Format detected patterns for LLM inclusion
   **Used by:** Briefing agent for pattern context
   **Output:** Formatted string for prompt injection

   ---

   ## 8. MODEL ROUTING & CONFIGURATION

   ### 8.1 Primary Model
   **Model ID:** `claude-haiku-4-5-20251001`
   **Used for:**
   - Entity extraction
   - Narrative extraction
   - Sentiment analysis
   - Theme extraction
   - Batch processing
   - All cost-sensitive operations

   ### 8.2 Fallback Model
   **Model ID:** `claude-sonnet-4-5-20250929`
   **Used for:**
   - Briefing generation (primary fallback)
   - Critique and refinement
   - High-quality synthesis tasks
   - Only when Haiku unavailable

   ### 8.3 Model Routing
   **Location:** LLM Gateway (`llm/gateway.py`)
   **Method:** Operation-based routing via `_OPERATION_MODEL_ROUTING`
   **Cost Tracking:** Gateway handles all cost attribution
   **Budget Enforcement:** Spend cap checks at provider level

   ---

   ## 9. KEY PROMPT PATTERNS & CONSTRAINTS

   ### Zero Hallucination Pattern
   **Used in:** Briefing generation, narrative summaries
   **Implementation:**
   - Explicit "ONLY discuss provided data" instruction
   - "NEVER mention entities unless they appear" constraints
   - "Do not infer or speculate" warnings

   ### JSON Output Pattern
   **Format:** Require "ONLY valid JSON with no markdown"
   **Used in:** Entity extraction, narrative extraction, batch processing
   **Parsing:** Custom JSON parsers handle extraction

   ### Output Format Control Pattern
   **Examples:**
   - Sentiment: "ONLY a single number"
   - Theme extraction: "Comma-separated list"
   - Relevance: "ONLY a single floating-point number"
   - Insight: "2-3 sentences"

   ### Model Cost Optimization
   **Strategy:** Haiku for simple tasks, Sonnet only for complex synthesis
   **Implementation:** 12x cost reduction vs. all-Sonnet baseline

   ---

   ## 10. PROMPT QUALITY REQUIREMENTS

   ### Hallucination Prevention
   - Every prompt includes constraints on source data
   - Fact-checking in critique phase
   - Self-refinement to catch issues

   ### Entity Specificity
   - No "the exchange" or "the platform"
   - Full entity names required
   - Normalization rules (BTC → Bitcoin)

   ### Output Validation
   - JSON parsing validation
   - Format checking (number ranges, string lengths)
   - Consistency checks across multi-pass workflows

   ### Token Efficiency
   - Text truncation to 2000 chars (~500 tokens)
   - Batch processing to reduce API calls
   - Response caching for identical prompts

   ---

   ## 11. OPERATION NAMES FOR COST TRACKING

   All prompts use operation names for cost attribution:
   - `briefing_generate` - Main briefing generation
   - `briefing_critique` - Self-critique pass
   - `briefing_refine` - Refinement pass
   - `entity_extraction` - Entity extraction
   - `narrative_extraction` - Narrative element extraction
   - `narrative_summary` - Summary generation
   - `theme_analysis` - Theme identification
   - `sentiment_analysis` - Sentiment scoring
   - `theme_extraction` - Theme keyword extraction
   - `market_insight` - Market insight generation
   - `relevance_score` - Relevance scoring
   - `batch_entity_extraction` - Batch entity processing
   - `batch_narrative_analysis` - Batch narrative processing


   Here are the actual prompt strings from your app:                                          
                                                                                             
  1. Entity Extraction (optimized_anthropic.py)                                              
                                                                                             
  Extract cryptocurrency-related entities from this article.                                 
                                                                                             
  Title: {article['title']}                                                                  
  Text: {text}                                                                               
                                                                                             
  Return a JSON object with this structure:                                                  
  {
    "entities": [                                                                            
      {           
        "name": "Bitcoin",
        "type": "cryptocurrency",
        "confidence": 0.95,
        "is_primary": true
      }                                                                                      
    ]
  }                                                                                          
                  
  Entity types: cryptocurrency, protocol, company, person, event, regulation                 
  Only include entities mentioned in the text. Normalize crypto names (BTC → Bitcoin).
                                                                                             
  2. Sentiment Analysis (anthropic.py:125)
                                                                                             
  Analyze the sentiment of this crypto text. Return ONLY a single number from -1.0 (very
  bearish) to 1.0 (very bullish). Do not include any explanation or additional text. Just the
   number:
                                                                                             
  {text}          

  3. Theme Extraction (anthropic.py:144)                                                     
   
  Extract the key crypto themes from the following texts. Respond with ONLY a comma-separated
   list of keywords (e.g., 'Bitcoin, DeFi, Regulation'). Do not include any preamble.        
   
  Texts:                                                                                     
  {combined_texts}

  4. Narrative Elements Extraction (optimized_anthropic.py)                                  
   
  Analyze this crypto news article and extract narrative elements.                           
                                                                                             
  Title: {article['title']}
  Text: {text}                                                                               
                  
  Return JSON:
  {
    "nucleus_entity": "Bitcoin",
    "actors": ["Bitcoin", "SEC", "Michael Saylor"],                                          
    "actor_salience": {"Bitcoin": 5, "SEC": 4, "Michael Saylor": 3},
    "tensions": ["regulatory uncertainty", "market volatility"],                             
    "actions": ["filed lawsuit", "price surge"]                                              
  }                                                                                          
                                                                                             
  Nucleus entity: The primary subject (most important entity)                                
  Actors: Key entities in the story
  Actor salience: Importance score 1-5 (5 = most important)                                  
  Tensions: Conflicts, themes, or concerns                                                   
  Actions: Key events or verbs
                                                                                             
  5. Narrative Summary (optimized_anthropic.py:299-319)                                      
                                                                                             
  Summarize these related crypto news articles.                                              
                  
  {articles_text}                                                                            
   
  Write a 2-3 sentence summary that:                                                         
  1. Identifies the main story or theme based ONLY on events explicitly described in the
  articles above                                                                             
  2. Explains why it matters
  3. Notes any conflicting perspectives                                                      
  4. Verifies financial figures are consistent across articles — if sources disagree on a    
  number, note the discrepancy rather than picking one                                       
                                                                                             
  CRITICAL: Your summary must describe only events, facts, and claims that are explicitly    
  stated in the provided articles. Do not infer, speculate, or add events not present in the
  source text. If the articles describe an IPO filing, summarize the IPO filing — do not     
  introduce security breaches, hacks, lawsuits, or other events unless they are explicitly
  described in the articles.

  Be concise and informative.                                                                
   
  6. Briefing System Prompt (briefing_agent.py:469-579)                                      
                  
  You are a senior crypto market analyst writing a {time_context} briefing memo.             
                                                                                             
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
                  
  WRITING RULES:

  1. SPECIFIC ENTITY REFERENCES (NEW - CRITICAL)                                             
     - ALWAYS use full entity names: "Binance", "BlackRock", "Cardano"
     - NEVER use vague references: "the platform", "the exchange", "the network"             
     - If an entity is mentioned multiple times, use its name each time                      
     - Example GOOD: "Binance has expanded its stablecoin offerings..."                      
     - Example BAD: "The exchange is expanding..." (which exchange?)                         
                                                                                             
  2. EXPLAIN "WHY IT MATTERS" (MANDATORY)                                                    
     - Every significant development MUST include its implications                           
     - Use phrases like:                                                                     
       * "The significance lies in..."                                                       
       * "This matters because..."
       * "The immediate impact is..."                                                        
       * "This represents..."
     - Connect events to broader market trends or investor decisions                         
     - Example GOOD: "BlackRock's Bitcoin ETF positioning represents material institutional
  endorsement that could drive Q1 capital flows despite regulatory uncertainty."             
     - Example BAD: "BlackRock designated Bitcoin ETF as key theme." (so what?)
                                                                                             
  3. ONLY COVER NARRATIVES FROM THE DATA
     - Read the "Active Narratives" section carefully                                        
     - Each narrative you discuss MUST match one of the titles listed                        
     - Do not add stories that aren't in the list
                                                                                             
  4. USE EXACT DETAILS FROM SUMMARIES                                                        
     - The narrative summaries contain the facts you should use                              
     - Copy specific details (names, amounts, events) from the summaries                     
     - If a summary lacks details, say so rather than inventing them                         
                                                                                             
  5. NO GENERIC FILLER                                                                       
     - BANNED: "The crypto markets continue to...", "In a mix of developments..."            
     - BANNED: "Looking ahead, the industry will be shaped by..."                            
     - BANNED: "Navigating challenges", "Amid uncertainty", "In the evolving landscape"      
     - Start directly with your most important story                                         
     - End with specific actionable focus areas                                              
                                                                                             
  6. PROFESSIONAL ANALYST TONE                                                               
     - Write as flowing memo, not bullet points
     - Connect related developments with causal reasoning                                    
     - Be direct about uncertainty when data is limited                                      
     - Use informed opinion with clear reasoning
                                                                                             
  7. STRUCTURE    
     - Each paragraph = one narrative or connected set of narratives
     - Open with most significant development                                                
     - End with specific "immediate focus" areas                                             
                                                                                             
  8. RECOMMENDATIONS (CRITICAL)                                                              
     - Include 2-3 recommendations for further reading
     - ONLY recommend narratives from the "ALLOWED NARRATIVES" list above                    
     - Use the EXACT narrative title as the recommendation title (matching case)
     - For theme, use the topic/category the narrative falls under (e.g., "Regulation",      
  "Trading", "Infrastructure")                                                               
     - Example: {"title": "Binance Expands in South Korea", "theme": "Regulatory Expansion"}
     - NEVER create recommendation titles that aren't in the allowed list                    
     - NEVER suggest topics or narratives that weren't provided
                                                                                             
  9. CONSOLIDATE DUPLICATE EVENTS                                                            
     - If multiple narratives clearly describe the same underlying event from different      
  angles, synthesize them into a single coherent account                                     
     - Do NOT present the same event twice with different framing
     - Look for overlapping entities, similar dollar amounts, or the same                    
  infrastructure/platform involved                                                           
     - Example: Two narratives about a Polkadot bridge exploit should become one consolidated
   paragraph, not two separate sections                                                      
                  
  10. NO UNNAMED ENTITIES                                                                    
      - If you cannot name a specific platform, exchange, or entity from the provided
  narratives, do not reference it                                                            
      - NEVER use phrases like "two platforms", "multiple exchanges", or "several protocols"
  unless you can name each one explicitly                                                    
      - NEVER imply a count of affected parties you cannot enumerate by name
      - If a narrative lacks specific details, acknowledge the limitation rather than        
  implying unnamed actors                                                                    
                                                                                             
  11. VERIFY FIGURE PLAUSIBILITY                                                             
      - Before citing any financial figure, consider whether it is plausible given the total
  crypto market cap (~$2-3T)                                                                 
      - A single-event liquidation exceeding $50B, a hack exceeding $10B, or similar extremes
   are almost certainly errors in the source data                                            
      - If a figure seems implausible, flag the uncertainty: "reported figures suggest $X,
  though this would be historically unprecedented"                                           
      - When source articles disagree on a figure, note the discrepancy rather than picking
  the most dramatic number                                                                   
                  
  GOOD EXAMPLE:                                                                              
  "Binance has expanded its stablecoin offerings with the listing of a Kyrgyzstan som-pegged
  stablecoin, marking a strategic move into Central Asian markets. The exchange is           
  simultaneously addressing security concerns through its anti-scam initiatives, though the
  specific technical measures remain undisclosed in available reporting. This parallel focus 
  on market expansion and security infrastructure reflects the operational priorities of
  centralized exchanges navigating growth and trust simultaneously."

  BAD EXAMPLE:
  "The exchange continues to navigate the evolving landscape with new offerings. They are
  also working on security. This shows how platforms are adapting."                          
  (Why bad? Vague "the exchange", generic filler "evolving landscape", no specific names, no
  "why it matters")                                                                          
                  
  Output Format:                                                                             
  Return valid JSON:
  {                                                                                          
      "narrative": "The briefing text...",
      "key_insights": ["insight1", "insight2", "insight3"],                                  
      "entities_mentioned": ["Entity1", "Entity2"],  // Full names only                      
      "detected_patterns": ["pattern1", "pattern2"],                                         
      "recommendations": [{"title": "...", "theme": "..."}],                                 
      "confidence_score": 0.85
  }                                                                                          
                  
  7. Briefing Critique Prompt (briefing_agent.py:667-708)                                    
   
  Review this crypto briefing for quality issues:                                            
                  
  BRIEFING NARRATIVE:
  {generated.narrative}
                                                                                             
  KEY INSIGHTS:
  {json.dumps(generated.key_insights, indent=2)}                                             
                  
  AVAILABLE NARRATIVES (the only valid sources):                                             
  {json.dumps(narrative_titles, indent=2)}
                                                                                             
  AVAILABLE ENTITIES (the only entities that can be mentioned):
  {json.dumps(list(narrative_entities), indent=2)}                                           
                                                                                             
  Check for these issues:
                                                                                             
  1. HALLUCINATION: Does the briefing mention facts, companies, events, or numbers that are  
  NOT from the provided narratives? This is the most critical issue.
                                                                                             
  2. VAGUE ENTITY REFERENCES (NEW - CRITICAL): Does the briefing use vague references like   
  "the platform", "the exchange", "the network", "the protocol" instead of specific entity
  names? Every entity must be named explicitly.                                              
                  
  3. MISSING "WHY IT MATTERS": Are events mentioned without explaining their significance or 
  implications? Each development needs clear reasoning for its importance.
                                                                                             
  4. VAGUE CLAIMS: Are there statements like "X is navigating challenges" without specific   
  details? Each claim needs specifics.
                                                                                             
  5. MISSING CONTEXT: Are numbers mentioned without baselines or comparisons?

  6. GENERIC FILLER: Does it start with "The crypto markets continue to..." or end with      
  generic forward-looking statements? Check for banned phrases like "amid uncertainty",
  "navigating challenges", "evolving landscape".                                             
                  
  7. ABRUPT TRANSITIONS: Does it switch topics mid-paragraph without logical connection?     
   
  8. DUPLICATE EVENTS: Does the briefing describe the same underlying event more than once   
  with different framing? Look for overlapping entities, similar figures, or the same
  infrastructure involved. If two sections cover the same incident, this is a critical issue 
  — they must be consolidated into one account.

  9. UNNAMED ENTITIES: Does the briefing reference unnamed platforms, exchanges, or entities?
   Phrases like "two platforms", "multiple exchanges", or "several protocols" without naming
  each one are NOT acceptable. Every referenced entity must be explicitly named from the     
  provided narratives.

  10. IMPLAUSIBLE FIGURES: Are any cited figures implausible relative to the total crypto    
  market (~$2-3T)? A single-event liquidation exceeding $50B, a hack exceeding $10B, or
  similar extremes would be historically unprecedented and likely an error. Flag any such    
  figures.        

  Respond with:                                                                              
  {
      "needs_refinement": true/false,                                                        
      "issues": ["issue1", "issue2"],
      "suggestions": ["suggestion1", "suggestion2"]                                          
  }
                                                                                             
  8. Briefing Refinement Prompt (briefing_agent.py:734-748)                                  
   
  Refine this crypto briefing based on the critique feedback:                                
                  
  ORIGINAL BRIEFING:
  {generated.narrative}

  CRITIQUE FEEDBACK:
  {critique}

  AVAILABLE DATA:                                                                            
  - Signals: {len(briefing_input.signals)} trending entities
  - Narratives: {len(briefing_input.narratives)} active narratives                           
  - Patterns: {len(briefing_input.patterns.all_patterns())} detected patterns
                                                                                             
  Address the issues identified in the critique and generate an improved briefing.
  Return ONLY valid JSON in the same format as before.                                       
                  
  9. Market Insight Generation (anthropic.py:158)                                            
   
  Given a sentiment score of {sentiment_score} and the themes {', '.join(themes)}, generate a
   concise market insight for cryptocurrency traders. The response must be a maximum of 2-3  
  sentences.
                                                                                             
  10. Relevance Scoring (anthropic.py:163)                                                   
   
  On a scale from 0.0 to 1.0, how relevant is this text to cryptocurrency market movements?  
  Return ONLY a single floating-point number with no explanation: 