/**
 * One-time script to prune irrelevant TARGETS relationships.
 *
 * For each ContentPiece, embeds the title, computes cosine similarity against
 * each targeted keyword's embedding, and removes TARGETS relationships where
 * the keyword is semantically irrelevant to the content topic.
 *
 * Run with: npx tsx --env-file=.env.local scripts/prune-irrelevant-keywords.ts
 *
 * Optional flags:
 *   --dry-run        Show what would be removed without deleting (default)
 *   --apply          Actually delete irrelevant relationships
 *   --threshold=0.65 Cosine similarity cutoff (default 0.65)
 */

import neo4j from "neo4j-driver";
import { GoogleGenAI } from "@google/genai";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const args = process.argv.slice(2);
const dryRun = !args.includes("--apply");
const thresholdArg = args.find((a) => a.startsWith("--threshold="));
const RELEVANCE_THRESHOLD = thresholdArg
  ? parseFloat(thresholdArg.split("=")[1])
  : 0.65;

// ---------------------------------------------------------------------------
// Embedding helpers (standalone — no app imports to avoid Next.js resolution)
// ---------------------------------------------------------------------------

function cosineSimilarity(a: number[], b: number[]): number {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB);
  return denom === 0 ? 0 : dot / denom;
}

async function embedText(
  genai: GoogleGenAI,
  text: string
): Promise<number[]> {
  const response = await genai.models.embedContent({
    model: "gemini-embedding-001",
    contents: [text],
    config: { outputDimensionality: 256 },
  });
  return response.embeddings?.[0]?.values ?? [];
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

async function main() {
  const uri = process.env.NEO4J_URI;
  const user = process.env.NEO4J_USERNAME;
  const password = process.env.NEO4J_PASSWORD;
  const geminiKey = process.env.GEMINI_API_KEY;

  if (!uri || !user || !password) {
    console.error(
      "Missing NEO4J_URI, NEO4J_USERNAME, or NEO4J_PASSWORD in .env.local"
    );
    process.exit(1);
  }
  if (!geminiKey) {
    console.error("Missing GEMINI_API_KEY in .env.local");
    process.exit(1);
  }

  const driver = neo4j.driver(uri, neo4j.auth.basic(user, password));
  const session = driver.session({
    database: process.env.NEO4J_DATABASE ?? "neo4j",
  });
  const genai = new GoogleGenAI({ apiKey: geminiKey });

  console.log(
    `\n${dryRun ? "🔍 DRY RUN" : "🗑️  APPLY MODE"} — threshold: ${RELEVANCE_THRESHOLD}\n`
  );

  try {
    // 1. Find all content pieces that have TARGETS relationships
    const contentResult = await session.run(
      `MATCH (c:ContentPiece)-[:TARGETS]->(k:Keyword)
       RETURN c.id AS id, c.title AS title, collect(k.term) AS keywords`
    );

    if (contentResult.records.length === 0) {
      console.log("No content pieces with TARGETS relationships found.");
      return;
    }

    let totalKept = 0;
    let totalPruned = 0;

    for (const record of contentResult.records) {
      const contentId = record.get("id") as string;
      const title = record.get("title") as string;
      const keywords = record.get("keywords") as string[];

      console.log(`\n📄 "${title}" (${keywords.length} keywords)`);

      // 2. Embed the content topic
      const topicVector = await embedText(genai, title);
      if (topicVector.length === 0) {
        console.log("   ⚠️  Could not embed title, skipping");
        continue;
      }

      // 3. Get keyword embeddings from Neo4j
      const kwResult = await session.run(
        `MATCH (k:Keyword)
         WHERE k.term IN $terms
         RETURN k.term AS term, k.embedding AS embedding`,
        { terms: keywords }
      );

      const toRemove: string[] = [];
      const toKeep: string[] = [];

      for (const kwRecord of kwResult.records) {
        const term = kwRecord.get("term") as string;
        const embedding = kwRecord.get("embedding") as number[] | null;

        // Embed on-the-fly if missing, then score
        let vector = embedding;
        if (!vector || vector.length === 0) {
          vector = await embedText(genai, term);
          if (vector.length > 0) {
            await session.run(
              `MATCH (k:Keyword {term: $term}) SET k.embedding = $vector`,
              { term, vector }
            );
          }
        }

        const sim = vector.length > 0 ? cosineSimilarity(topicVector, vector) : 0;
        if (sim < RELEVANCE_THRESHOLD) {
          toRemove.push(term);
          console.log(`   ❌ ${sim.toFixed(3)} — "${term}"`);
        } else {
          toKeep.push(term);
          console.log(`   ✅ ${sim.toFixed(3)} — "${term}"`);
        }
      }

      // Also check keywords that had no Neo4j node match (shouldn't happen, but safe)
      const matchedTerms = new Set(
        kwResult.records.map((r) => r.get("term") as string)
      );
      for (const kw of keywords) {
        if (!matchedTerms.has(kw)) {
          toRemove.push(kw);
          console.log(`   ❌ N/A  — "${kw}" (keyword node not found)`);
        }
      }

      console.log(
        `   → Keep: ${toKeep.length} | Remove: ${toRemove.length}`
      );
      totalKept += toKeep.length;
      totalPruned += toRemove.length;

      // 4. Delete irrelevant TARGETS relationships
      if (toRemove.length > 0 && !dryRun) {
        await session.run(
          `MATCH (c:ContentPiece {id: $contentId})-[r:TARGETS]->(k:Keyword)
           WHERE k.term IN $terms
           DELETE r`,
          { contentId, terms: toRemove }
        );
        console.log(`   🗑️  Deleted ${toRemove.length} TARGETS relationships`);
      }
    }

    console.log(`\n${"─".repeat(50)}`);
    console.log(`Total kept:   ${totalKept}`);
    console.log(`Total pruned: ${totalPruned}`);
    if (dryRun && totalPruned > 0) {
      console.log(`\nRe-run with --apply to delete irrelevant relationships.`);
    }
    console.log();
  } finally {
    await session.close();
    await driver.close();
  }
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});
