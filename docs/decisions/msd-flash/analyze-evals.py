"""
Eval analysis — run from the 2026-04-28 directory.
Usage: python analyze_evals.py

Prints a compact summary to paste back to Claude.
"""

import json
import statistics
from pathlib import Path
from collections import defaultdict

DIR = Path(".")

# ── Verified OpenRouter pricing (per 1M tokens, confirmed 2026-04-28) ────────
PRICING = {
    "haiku":    {"input": 1.00, "output": 5.00},
    "flash":    {"input": 0.30, "output": 2.50},
    "deepseek": {"input": 0.32, "output": 0.89},
    "qwen":     {"input": 0.26, "output": 0.78},
}

# Token counts from MSD files (avg per article)
TOKENS = {
    "entity":    {"haiku": (178,116), "flash": (178,116), "deepseek": (170,137), "qwen": (173,105)},
    "sentiment": {"haiku": (98,3),    "flash": (98,3),    "deepseek": (99,4),    "qwen": (107,3)},
    "theme":     {"haiku": (94,10),   "flash": (94,10),   "deepseek": (97,16),   "qwen": (101,10)},
}

ARTICLES_PER_DAY = 100
MODELS = ["flash", "deepseek", "qwen"]

def load_jsonl(path):
    with open(path) as f:
        return [json.loads(l) for l in f if l.strip()]

def load_scored(op, model):
    p = DIR / f"scored-{op}-{model}.jsonl"
    if not p.exists():
        print(f"  {model.upper()} | file missing: {p}")
        return None
    rows = load_jsonl(p)
    if not rows:
        print(f"  {model.upper()} | no data")
        return None
    return rows

def detect(keys, candidates):
    return next((k for k in candidates if k in keys), None)

def cost_per_article(model, op):
    inp, out = TOKENS[op][model]
    p = PRICING[model]
    return (inp * p["input"] + out * p["output"]) / 1_000_000

def vs_haiku(model, op):
    h = cost_per_article("haiku", op)
    m = cost_per_article(model, op)
    pct = ((m - h) / h) * 100
    return pct  # negative = cheaper

# ── 0. Schema check ──────────────────────────────────────────────────────────
print("=== SCHEMA CHECK ===")
for op in ["entity_extraction", "sentiment_analysis", "theme_extraction"]:
    for model in MODELS:
        p = DIR / f"scored-{op}-{model}.jsonl"
        if p.exists():
            rows = load_jsonl(p)
            if rows:
                print(f"  scored-{op}-{model}: {list(rows[0].keys())}")
            break

# ── 1. scoring-stats.json ────────────────────────────────────────────────────
print("\n=== SCORING STATS ===")
stats_path = DIR / "scoring-stats.json"
if stats_path.exists():
    print(json.dumps(json.loads(stats_path.read_text()), indent=2))
else:
    print("  not found")

# ── 2. Cost reality check (correct pricing) ──────────────────────────────────
print("\n=== COST ANALYSIS (verified OpenRouter pricing, 100 articles/day) ===")
print(f"\n  {'Model':<12} {'Input/1M':>10} {'Output/1M':>10}")
print(f"  {'-'*34}")
for m, p in PRICING.items():
    print(f"  {m:<12} ${p['input']:>8.2f}   ${p['output']:>8.2f}")

print(f"\n  Per-article cost breakdown:")
print(f"  {'Model':<12} {'Entity':>10} {'Sentiment':>10} {'Theme':>10} {'Total/art':>10} {'vs Haiku':>10}")
print(f"  {'-'*62}")

monthly = {}
for m in ["haiku"] + MODELS:
    e = cost_per_article(m, "entity")
    s = cost_per_article(m, "sentiment")
    t = cost_per_article(m, "theme")
    total = e + s + t
    mo = total * ARTICLES_PER_DAY * 30
    monthly[m] = mo
    if m == "haiku":
        print(f"  {m:<12} ${e:>9.5f}  ${s:>9.5f}  ${t:>9.5f}  ${total:>9.5f}  {'baseline':>10}")
    else:
        pct = ((total - cost_per_article("haiku","entity") - cost_per_article("haiku","sentiment") - cost_per_article("haiku","theme")) /
               (cost_per_article("haiku","entity") + cost_per_article("haiku","sentiment") + cost_per_article("haiku","theme"))) * 100
        print(f"  {m:<12} ${e:>9.5f}  ${s:>9.5f}  ${t:>9.5f}  ${total:>9.5f}  {pct:>+9.1f}%")

print(f"\n  Monthly cost (all 3 ops, {ARTICLES_PER_DAY} articles/day):")
haiku_mo = monthly["haiku"]
for m, mo in monthly.items():
    savings = haiku_mo - mo
    tag = "baseline" if m == "haiku" else f"saves ${savings:.2f}/mo"
    print(f"  {m:<12} ${mo:.2f}/mo   {tag}")

# ── 3. Entity extraction ─────────────────────────────────────────────────────
print("\n=== ENTITY EXTRACTION ===")
print("  NOTE: eval measures parity with Haiku (mention-level).")
print("  Manual validation = 30% agreement. Prompt fix needed in Sprint 17.")
print("  Distribution useful for clustering — not for swap decisions yet.\n")

entity_data = {}
for model in MODELS:
    rows = load_scored("entity_extraction", model)
    if rows is None:
        continue
    total = len(rows)
    flag_field = detect(rows[0].keys(), ["flagged", "regression", "flag"])

    def get_f1(r):
        s = r.get("score")
        if isinstance(s, dict): return s.get("f1")
        if isinstance(s, (int, float)): return s
        for k in ["f1", "f1_score"]:
            v = r.get(k)
            if isinstance(v, (int, float)): return v
        return None

    scores  = [v for r in rows for v in [get_f1(r)] if v is not None]
    flagged = sum(1 for r in rows if flag_field and r.get(flag_field)) if flag_field else "n/a"
    mean    = sum(scores) / len(scores) if scores else 0
    std     = statistics.pstdev(scores) if len(scores) > 1 else 0
    entity_data[model] = {"rows": rows, "scores": scores, "get_score": get_f1}
    buckets = {">=0.85": 0, "0.70-0.84": 0, "0.50-0.69": 0, "<0.50": 0}
    for s in scores:
        if   s >= 0.85: buckets[">=0.85"] += 1
        elif s >= 0.70: buckets["0.70-0.84"] += 1
        elif s >= 0.50: buckets["0.50-0.69"] += 1
        else:           buckets["<0.50"] += 1
    print(f"  {model.upper()} | n={total} | mean={mean:.3f} | std={std:.3f} | flagged={flagged}/{total}")
    print(f"  Distribution: {buckets}")
    worst = sorted(rows, key=lambda r: get_f1(r) if get_f1(r) is not None else 1)[:3]
    for w in worst:
        txt = w.get("text", w.get("input_text", ""))[:80]
        print(f"  worst: score={get_f1(w):.3f} | {txt}")
    print()

# Entity head-to-head
if len(entity_data) >= 2:
    print("  HEAD-TO-HEAD (per sample wins — informational only until prompt fix):")
    for a, b in [("flash","deepseek"), ("flash","qwen"), ("deepseek","qwen")]:
        if a not in entity_data or b not in entity_data:
            continue
        ga, gb = entity_data[a]["get_score"], entity_data[b]["get_score"]
        ra, rb = entity_data[a]["rows"], entity_data[b]["rows"]
        n = min(len(ra), len(rb))
        wins = {a: 0, b: 0, "tie": 0}
        for i in range(n):
            sa = ga(ra[i]) or 0
            sb = gb(rb[i]) or 0
            if sa > sb: wins[a] += 1
            elif sb > sa: wins[b] += 1
            else: wins["tie"] += 1
        print(f"  {a} vs {b}: {a}={wins[a]} {b}={wins[b]} tie={wins['tie']}")

# ── 4. Sentiment analysis ────────────────────────────────────────────────────
print("\n=== SENTIMENT ANALYSIS ===")
print("  NOTE: most trustworthy eval — baseline agreement 80%.")
print("  Flash cheaper than Haiku. CONDITIONAL decision actionable.\n")

sentiment_data = {}
for model in MODELS:
    rows = load_scored("sentiment_analysis", model)
    if rows is None:
        continue
    total  = len(rows)
    keys   = list(rows[0].keys())
    ref_field  = detect(keys, ["baseline_label","haiku_label","expected","label"])
    pred_field = detect(keys, ["challenger_label","predicted","model_label","output"])
    ok_field   = detect(keys, ["correct","match","score"])
    by_class   = defaultdict(lambda: {"correct": 0, "total": 0})
    mismatches = defaultdict(int)
    sample_scores = []

    # schema: score is nested dict with match, haiku_label, {model}_label
    def get_sent(r):
        s = r.get("score", {})
        bl = s.get("haiku_label", "?")
        cl = s.get(f"{model}_label", "?")
        ok = s.get("match", bl == cl)
        return bl, cl, ok

    for r in rows:
        bl, cl, ok = get_sent(r)
        sample_scores.append(1 if ok else 0)
        by_class[bl]["total"] += 1
        if ok: by_class[bl]["correct"] += 1
        else:  mismatches[f"{bl}->{cl}"] += 1

    acc = sum(sample_scores) / len(sample_scores) if sample_scores else 0
    std = statistics.pstdev(sample_scores) if len(sample_scores) > 1 else 0
    sentiment_data[model] = {"rows": rows, "scores": sample_scores, "get_sent": get_sent}

    print(f"  {model.upper()} | n={total} | accuracy={acc:.1%} | std={std:.3f}")
    for label in ["positive", "negative", "neutral"]:
        c = by_class.get(label, {"correct": 0, "total": 0})
        a = c["correct"] / c["total"] if c["total"] else 0
        print(f"    {label:10s}: {c['correct']}/{c['total']} ({a:.0%})")
    top = sorted(mismatches.items(), key=lambda x: -x[1])[:6]
    print(f"    Mismatches: {top}")

    # Haiku bias check: cases where Haiku=neutral but challenger=negative
    # Manual validation found Haiku gets crime/legal articles wrong this way
    haiku_neutral_challenger_neg = [
        r for r in rows
        if get_sent(r)[0] == "neutral" and get_sent(r)[1] == "negative"
    ]
    print(f"    Haiku=neutral, challenger=negative (possible Haiku bias): {len(haiku_neutral_challenger_neg)}")
    for w in haiku_neutral_challenger_neg[:2]:
        s = w.get("score", {})
        print(f"      id={w.get('_id')} haiku={s.get('haiku_label')} {model}={s.get(model+'_label')}")
    print()

# Sentiment head-to-head
if len(sentiment_data) >= 2:
    print("  HEAD-TO-HEAD (actionable — swap decisions live here):")
    for a, b in [("flash","deepseek"), ("flash","qwen"), ("deepseek","qwen")]:
        if a not in sentiment_data or b not in sentiment_data:
            continue
        ra, rb = sentiment_data[a], sentiment_data[b]
        n = min(len(ra["rows"]), len(rb["rows"]))
        wins = {a: 0, b: 0, "both_right": 0, "both_wrong": 0}
        for i in range(n):
            _, _, oa = ra["get_sent"](ra["rows"][i])
            _, _, ob = rb["get_sent"](rb["rows"][i])
            if   oa and ob:         wins["both_right"] += 1
            elif not oa and not ob: wins["both_wrong"] += 1
            elif oa:                wins[a] += 1
            else:                   wins[b] += 1
        print(f"  {a} vs {b}: {a}_only={wins[a]} {b}_only={wins[b]} "
              f"both_right={wins['both_right']} both_wrong={wins['both_wrong']}")

    # Cost-adjusted recommendation
    print(f"\n  Cost vs accuracy tradeoff (sentiment):")
    haiku_cost = cost_per_article("haiku", "sentiment") * ARTICLES_PER_DAY * 30
    for m in MODELS:
        rows = sentiment_data.get(m, {}).get("rows", [])
        if not rows:
            continue
        gs   = sentiment_data[m]["get_sent"]
        acc  = sum(1 for r in rows if gs(r)[2]) / len(rows)
        mo   = cost_per_article(m, "sentiment") * ARTICLES_PER_DAY * 30
        savings = haiku_cost - mo
        print(f"  {m:<12} accuracy={acc:.0%}  monthly=${mo:.3f}  saves=${savings:.3f}/mo vs Haiku")

# ── 5. Theme extraction ──────────────────────────────────────────────────────
print("\n=== THEME EXTRACTION ===")
print("  NOTE: eval unreliable — 10% manual agreement, Haiku includes entity")
print("  names as themes. Distribution shown for Sprint 17 prompt work only.\n")

theme_data = {}
for model in MODELS:
    rows = load_scored("theme_extraction", model)
    if rows is None:
        continue
    total = len(rows)

    def get_theme_f1(r):
        s = r.get("score")
        if isinstance(s, dict): return s.get("f1") or s.get("adjusted_f1")
        if isinstance(s, (int, float)): return s
        for k in ["adjusted_f1", "f1", "f1_score"]:
            v = r.get(k)
            if isinstance(v, (int, float)): return v
        return None

    scores = [v for r in rows for v in [get_theme_f1(r)] if v is not None]
    mean   = sum(scores) / len(scores) if scores else 0
    std    = statistics.pstdev(scores) if len(scores) > 1 else 0
    theme_data[model] = {"rows": rows, "scores": scores, "get_score": get_theme_f1}
    buckets = {">=0.80": 0, "0.60-0.79": 0, "0.40-0.59": 0, "<0.40": 0}
    for s in scores:
        if   s >= 0.80: buckets[">=0.80"] += 1
        elif s >= 0.60: buckets["0.60-0.79"] += 1
        elif s >= 0.40: buckets["0.40-0.59"] += 1
        else:           buckets["<0.40"] += 1
    print(f"  {model.upper()} | n={total} | mean={mean:.3f} | std={std:.3f}")
    print(f"  Distribution: {buckets}")
    if scores:
        worst = sorted(rows, key=lambda r: get_theme_f1(r) if get_theme_f1(r) is not None else 1)[:2]
        for w in worst:
            txt = w.get("text", w.get("input_text", ""))[:80]
            print(f"  worst: score={get_theme_f1(w):.3f} | {txt}")
    print()

print("\n=== SUMMARY ===")
print("""
  SENTIMENT  → Actionable now. Flash/DeepSeek/Qwen all cheaper than Haiku.
               Flash: 75% accuracy, saves ~57% cost. CONDITIONAL holds.
               Run head-to-head output to see if Haiku-neutral mismatches
               are actually closer to human judgment (crime/legal articles).

  ENTITY     → Not actionable until Sprint 17 prompt fix.
               Eval measured wrong thing (mention-level vs relevance-weighted).
               Distribution data useful for prompt design only.

  THEME      → Not actionable until Sprint 17 prompt fix.
               Single prompt change (exclude proper nouns) likely fixes baseline.
               Re-eval after fix before any model decision.

  FLASH      → Cheaper than Haiku on all ops. Back in play for sentiment.
               Not cheapest — Qwen/DeepSeek cheaper on input, cheaper on output
               except Flash vs Qwen output ($2.50 vs $0.78) favors Qwen heavily
               for high-output ops (entity). Use Flash for sentiment (3 output
               tokens — output price barely matters there).
""")

print("=== DONE — paste this output back to Claude ===")