import { kmeans } from "ml-kmeans";
import { z } from "zod";
import { generateStructured } from "@/lib/ai/claude";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ClusterAssignment {
  term: string;
  clusterId: number;
}

export type IntentType =
  | "informational"
  | "navigational"
  | "commercial"
  | "transactional";

// ---------------------------------------------------------------------------
// clusterKeywords — k-means on embedding vectors
// ---------------------------------------------------------------------------

export function clusterKeywords(
  keywords: { term: string; embedding: number[] }[]
): ClusterAssignment[] {
  if (keywords.length < 5) {
    // Too few to cluster meaningfully — put all in cluster 0
    return keywords.map((kw) => ({ term: kw.term, clusterId: 0 }));
  }

  const vectors = keywords.map((kw) => kw.embedding);

  // Select k: between 2 and min(n/3, 20)
  const minK = 2;
  const maxK = Math.min(Math.floor(keywords.length / 3), 20);
  const k = Math.max(minK, Math.min(maxK, Math.round(Math.sqrt(keywords.length))));

  const result = kmeans(vectors, k, {
    initialization: "kmeans++",
    maxIterations: 100,
  });

  return keywords.map((kw, i) => ({
    term: kw.term,
    clusterId: result.clusters[i],
  }));
}

// ---------------------------------------------------------------------------
// classifyIntentAI — batch intent classification via Haiku
// ---------------------------------------------------------------------------

const INTENT_BATCH_SIZE = 50;

const intentSchema = z.object({
  classifications: z.array(
    z.object({
      term: z.string(),
      intent: z.enum([
        "informational",
        "navigational",
        "commercial",
        "transactional",
      ]),
    })
  ),
});

export async function classifyIntentAI(
  keywords: string[]
): Promise<Map<string, IntentType>> {
  const results = new Map<string, IntentType>();

  if (keywords.length === 0) return results;

  // Process in batches
  for (let i = 0; i < keywords.length; i += INTENT_BATCH_SIZE) {
    const batch = keywords.slice(i, i + INTENT_BATCH_SIZE);

    try {
      const { data } = await generateStructured({
        model: "haiku",
        system:
          "Classify each keyword by search intent. Respond with the exact keyword and its intent.",
        messages: [
          {
            role: "user",
            content: `Classify these keywords:\n${batch.map((k, j) => `${j + 1}. ${k}`).join("\n")}`,
          },
        ],
        schema: intentSchema,
        maxTokens: 2048,
      });

      for (const item of data.classifications) {
        results.set(item.term, item.intent);
      }

      // Fill in any keywords the model missed with fallback
      for (const kw of batch) {
        if (!results.has(kw)) {
          results.set(kw, classifyIntentRegex(kw));
        }
      }
    } catch {
      // Fallback to regex on API failure
      for (const kw of batch) {
        results.set(kw, classifyIntentRegex(kw));
      }
    }
  }

  return results;
}

// ---------------------------------------------------------------------------
// Regex fallback (original implementation, kept as safety net)
// ---------------------------------------------------------------------------

export function classifyIntentRegex(keyword: string): IntentType {
  const lower = keyword.toLowerCase();
  if (
    /\b(buy|pricing|price|cost|purchase|order|deal|discount|coupon|shop)\b/.test(
      lower
    )
  )
    return "transactional";
  if (
    /\b(best|top|review|compare|vs|versus|alternative|recommend)\b/.test(lower)
  )
    return "commercial";
  if (
    /\b(login|sign in|website|homepage|official|app|download)\b/.test(lower)
  )
    return "navigational";
  if (
    /\b(how|what|why|when|where|who|guide|tutorial|learn|example)\b/.test(
      lower
    )
  )
    return "informational";
  return "informational";
}

// ---------------------------------------------------------------------------
// nameCluster — generate a descriptive name for a keyword cluster
// ---------------------------------------------------------------------------

const clusterNameSchema = z.object({
  name: z.string(),
  pillarTopic: z.string(),
});

export async function nameCluster(
  keywords: string[]
): Promise<{ name: string; pillarTopic: string }> {
  try {
    const { data } = await generateStructured({
      model: "haiku",
      system:
        "Given a group of related keywords, generate a short descriptive cluster name (2-4 words) and a pillar topic (1-2 words) that represents the core theme.",
      messages: [
        {
          role: "user",
          content: `Keywords: ${keywords.join(", ")}`,
        },
      ],
      schema: clusterNameSchema,
      maxTokens: 256,
    });
    return data;
  } catch {
    // Fallback: use the shortest keyword as the name
    const shortest = keywords.reduce((a, b) =>
      a.length <= b.length ? a : b
    );
    return { name: shortest, pillarTopic: shortest };
  }
}
