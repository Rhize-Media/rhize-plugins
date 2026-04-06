import { GoogleGenAI } from "@google/genai";
import { getDriver } from "@/lib/neo4j/driver";

// ---------------------------------------------------------------------------
// Client singleton
// ---------------------------------------------------------------------------

const DEFAULT_DIMENSIONS = 256;
const BATCH_SIZE = 100; // Gemini API limit per request

let genai: GoogleGenAI | null = null;

function getGenAI(): GoogleGenAI {
  if (genai) return genai;
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error(
      "Missing GEMINI_API_KEY. Set it in .env.local or Vercel environment variables."
    );
  }
  genai = new GoogleGenAI({ apiKey });
  return genai;
}

// Exported for testing — allows injecting a mock
export function _setGenAI(mock: GoogleGenAI | null): void {
  genai = mock;
}

// ---------------------------------------------------------------------------
// embedBatch — embed an array of texts via Gemini text-embedding-004
// ---------------------------------------------------------------------------

export async function embedBatch(
  texts: string[],
  options?: { dimensions?: number }
): Promise<number[][]> {
  if (texts.length === 0) return [];

  const ai = getGenAI();
  const dimensions = options?.dimensions ?? DEFAULT_DIMENSIONS;
  const results: number[][] = [];

  // Chunk into batches of BATCH_SIZE
  for (let i = 0; i < texts.length; i += BATCH_SIZE) {
    const chunk = texts.slice(i, i + BATCH_SIZE);
    const response = await ai.models.embedContent({
      model: "text-embedding-004",
      contents: chunk,
      config: { outputDimensionality: dimensions },
    });

    for (const embedding of response.embeddings ?? []) {
      results.push(embedding.values ?? []);
    }
  }

  return results;
}

// ---------------------------------------------------------------------------
// embedAndCacheKeywords — embed keywords and store vectors in Neo4j
// ---------------------------------------------------------------------------

export async function embedAndCacheKeywords(
  terms: string[],
  options?: { dimensions?: number }
): Promise<{ embedded: number; skipped: number }> {
  if (terms.length === 0) return { embedded: 0, skipped: 0 };

  const driver = getDriver();
  const session = driver.session();

  try {
    // Find keywords that need embedding
    const result = await session.run(
      `MATCH (k:Keyword)
       WHERE k.term IN $terms AND k.embedding IS NULL
       RETURN k.term AS term`,
      { terms }
    );

    const needsEmbedding = result.records.map(
      (r) => r.get("term") as string
    );

    if (needsEmbedding.length === 0) {
      return { embedded: 0, skipped: terms.length };
    }

    // Embed the missing keywords
    const vectors = await embedBatch(needsEmbedding, options);

    // Write embeddings back to Neo4j in a single batched query
    const entries = needsEmbedding.map((term, i) => ({
      term,
      vector: vectors[i],
    }));
    await session.run(
      `UNWIND $entries AS entry
       MATCH (k:Keyword {term: entry.term})
       SET k.embedding = entry.vector`,
      { entries }
    );

    return {
      embedded: needsEmbedding.length,
      skipped: terms.length - needsEmbedding.length,
    };
  } finally {
    await session.close();
  }
}
