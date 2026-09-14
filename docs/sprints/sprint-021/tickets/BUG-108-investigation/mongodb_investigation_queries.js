// ============================================================================
// BUG-108 MongoDB Investigation Queries
//
// These queries are designed to be run in mongosh with the production MongoDB URI
// They use read-only operations only and return metadata without exposing content
//
// USAGE:
//   mongosh "$MONGODB_URI" --quiet
//   Then paste each query block below
// ============================================================================

// ============================================================================
// 1. ARTICLE FRESHNESS AND INGESTION VOLUME
//
// This confirms articles ARE being ingested by counting by source and age window
// ============================================================================

print("\n=== QUERY 1: Article freshness by source (last 24h, 7d, 30d) ===\n");
const now = new Date();
for (const hours of [24, 168, 720]) {
  const since = new Date(now.getTime() - hours * 60 * 60 * 1000);
  print(`\n--- Articles ingested in last ${hours}h (since ${since.toISOString()}) ---`);
  printjson(db.articles.aggregate([
    { $match: { created_at: { $gte: since } } },
    { $group: {
      _id: "$source",
      count: { $sum: 1 },
      earliest: { $min: "$created_at" },
      latest: { $max: "$created_at" }
    } },
    { $sort: { count: -1 } },
    { $limit: 30 }
  ]).toArray());
}

// ============================================================================
// 2. ENTITY MENTION VOLUME AND RECENCY
//
// This is the CRITICAL query for Signals display
// If entity_mentions is empty or has no recent is_primary:true records,
// that explains why Signals page shows "No signals detected"
// ============================================================================

print("\n=== QUERY 2: Entity mention counts by primary flag, type, source (last 24h, 7d, 30d) ===\n");
const now2 = new Date();
for (const hours of [24, 168, 720]) {
  const since = new Date(now2.getTime() - hours * 60 * 60 * 1000);
  print(`\n--- Entity mentions created in last ${hours}h (since ${since.toISOString()}) ---`);
  printjson(db.entity_mentions.aggregate([
    { $match: { created_at: { $gte: since } } },
    { $group: {
      _id: { primary: "$is_primary", type: "$entity_type", source: "$source" },
      count: { $sum: 1 },
      earliest: { $min: "$created_at" },
      latest: { $max: "$created_at" },
      entities: { $addToSet: "$entity" }
    } },
    { $project: {
      _id: 1,
      count: 1,
      earliest: 1,
      latest: 1,
      entities: { $slice: ["$entities", 30] }
    } },
    { $sort: { count: -1 } },
    { $limit: 100 }
  ]).toArray());
}

// ============================================================================
// 3. ENRICHMENT BACKLOG ANALYSIS
//
// Shows how many articles are waiting for enrichment, broken down by age band
// Large numbers here indicate a backlog; articles older than 30d suggest
// the enrichment process hasn't run or completed in a long time
// ============================================================================

print("\n=== QUERY 3: Enrichment backlog by age band ===\n");
const since_30d = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
const since_7d = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
const since_1d = new Date(Date.now() - 1 * 24 * 60 * 60 * 1000);

print(`\nCurrent time: ${new Date().toISOString()}`);
print(`30 days ago:  ${since_30d.toISOString()}`);
print(`7 days ago:   ${since_7d.toISOString()}`);
print(`1 day ago:    ${since_1d.toISOString()}\n`);

printjson(db.articles.aggregate([
  {
    $match: {
      $or: [
        { relevance_score: { $exists: false } },
        { relevance_score: null },
        { relevance_score: 0.0 },
        { sentiment_score: { $exists: false } },
        { sentiment_score: null },
        { sentiment_score: 0.0 },
        { sentiment: { $exists: false } },
        { relevance_tier: { $exists: false } },
        { relevance_tier: null }
      ]
    }
  },
  {
    $group: {
      _id: null,
      total_unenriched: { $sum: 1 },
      last_1d: { $sum: { $cond: [{ $gte: ["$created_at", since_1d] }, 1, 0] } },
      last_7d: { $sum: { $cond: [{ $gte: ["$created_at", since_7d] }, 1, 0] } },
      last_30d: { $sum: { $cond: [{ $gte: ["$created_at", since_30d] }, 1, 0] } },
      older_30d: { $sum: { $cond: [{ $lt: ["$created_at", since_30d] }, 1, 0] } },
      oldest_created_at: { $min: "$created_at" },
      newest_created_at: { $max: "$created_at" }
    }
  }
]).toArray());

// ============================================================================
// 4. ENRICHMENT QUALITY DISTRIBUTION
//
// Shows what fraction of unenriched articles are missing which fields
// Helps identify if enrichment is partial (some fields set, others missing)
// ============================================================================

print("\n=== QUERY 4: Enrichment field completion status ===\n");

const fieldStatuses = [
  { field: "relevance_score", exists: true },
  { field: "relevance_tier", exists: true },
  { field: "sentiment_score", exists: true },
  { field: "sentiment", exists: true },
  { field: "entities", exists: true }
];

for (const fs of fieldStatuses) {
  const query = { [fs.field]: { [fs.exists ? "$exists" : "$ne"]: fs.exists } };
  const count = db.articles.countDocuments(query);
  const unenrichedCount = db.articles.countDocuments({
    ...query,
    $or: [
      { relevance_score: { $exists: false } },
      { relevance_tier: { $exists: false } },
      { sentiment_score: { $exists: false } }
    ]
  });
  print(`${fs.field} (${fs.exists ? "exists" : "missing"}): ${count} articles`);
}

// ============================================================================
// 5. ARTICLE-TO-MENTION LINKAGE VALIDATION
//
// Confirms that entity_mentions have valid article_id references
// If most mentions have unmatched article_ids, that's a data quality issue
// ============================================================================

print("\n=== QUERY 5: Article linkage validation for recent primary mentions ===\n");

const since_30d_v5 = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000);
printjson(db.entity_mentions.aggregate([
  { $match: { created_at: { $gte: since_30d_v5 }, is_primary: true } },
  {
    $set: {
      article_oid: {
        $convert: { input: "$article_id", to: "objectId", onError: null, onNull: null }
      }
    }
  },
  {
    $lookup: {
      from: "articles",
      localField: "article_oid",
      foreignField: "_id",
      as: "article_match"
    }
  },
  {
    $group: {
      _id: {
        mention_article_id_type: { $type: "$article_id" },
        matched_article: { $gt: [{ $size: "$article_match" }, 0] },
        entity_type: "$entity_type",
        source: "$source"
      },
      count: { $sum: 1 },
      latest: { $max: "$created_at" },
      sample_entities: { $addToSet: "$entity" }
    }
  },
  { $sort: { count: -1 } },
  { $limit: 100 }
]).toArray());

// ============================================================================
// 6. TRENDING SIGNALS ENDPOINT SIMULATION
//
// This mimics the exact computation that the /api/v1/signals/trending endpoint uses
// If this returns empty or low counts, that's the root cause
// ============================================================================

print("\n=== QUERY 6: Trending signals (endpoint simulation, 24h/7d/30d windows) ===\n");

const now6 = new Date();
for (const [label, hours] of [["24h", 24], ["7d", 168], ["30d", 720]]) {
  const currentStart = new Date(now6.getTime() - hours * 60 * 60 * 1000);
  const previousStart = new Date(now6.getTime() - 2 * hours * 60 * 60 * 1000);

  print(`\n--- ${label} window (current: since ${currentStart.toISOString()}, previous: since ${previousStart.toISOString()}) ---`);

  printjson(db.entity_mentions.aggregate([
    { $match: { is_primary: true, created_at: { $gte: previousStart } } },
    {
      $group: {
        _id: "$entity",
        types: { $addToSet: "$entity_type" },
        previous_mentions: { $sum: { $cond: [{ $lt: ["$created_at", currentStart] }, 1, 0] } },
        current_mentions: { $sum: { $cond: [{ $gte: ["$created_at", currentStart] }, 1, 0] } },
        latest_mention: { $max: "$created_at" },
        sources: { $addToSet: "$source" }
      }
    },
    { $match: { current_mentions: { $gte: 1 } } },  // ← Only entities with current-period mentions
    {
      $project: {
        entity: "$_id",
        _id: 0,
        types: 1,
        previous_mentions: 1,
        current_mentions: 1,
        latest_mention: 1,
        source_count: { $size: "$sources" }
      }
    },
    { $sort: { current_mentions: -1, latest_mention: -1 } },
    { $limit: 100 }
  ]).toArray());
}

print("\n=== Investigation complete ===\n");
print("KEY INTERPRETATION:");
print("- If Query 2 returns empty for is_primary=true, that's the root cause (no mentions created)");
print("- If Query 3 shows large 'total_unenriched' (>1000), that's the backlog issue");
print("- If Query 6 returns empty results for 24h/7d, that explains the empty Signals page");
