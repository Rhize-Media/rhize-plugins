import Firecrawl from "firecrawl";
import { z } from "zod";
import { runCypher } from "@/lib/neo4j/queries";
import { generateStructured } from "@/lib/ai/claude";
import { embedBatch } from "@/lib/ai/embeddings";
import { createWorkflowRun, completeWorkflowRun, failWorkflowRun } from "@/lib/workflows/helpers";
import type { WorkflowRun, ContentPiece } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ContentIngestInput {
  url: string;
  contentId?: string;
}

interface ContentIngestResult {
  workflowRun: WorkflowRun;
  contentPiece: ContentPiece;
  themes: string[];
}

// ---------------------------------------------------------------------------
// Firecrawl client singleton
// ---------------------------------------------------------------------------

let firecrawlClient: Firecrawl | null = null;

function getFirecrawl(): Firecrawl {
  if (firecrawlClient) return firecrawlClient;
  const apiKey = process.env.FIRECRAWL_API_KEY;
  if (!apiKey) {
    throw new Error(
      "Missing FIRECRAWL_API_KEY. Set it in .env.local or Vercel environment variables."
    );
  }
  firecrawlClient = new Firecrawl({ apiKey });
  return firecrawlClient;
}

// Exported for testing
export function _setFirecrawl(mock: Firecrawl | null): void {
  firecrawlClient = mock;
}

// ---------------------------------------------------------------------------
// Theme extraction schema
// ---------------------------------------------------------------------------

const themeSchema = z.object({
  themes: z.array(z.string()).min(3).max(10),
  summary: z.string(),
  title: z.string(),
  author: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Main workflow
// ---------------------------------------------------------------------------

const MAX_CONTENT_TOKENS = 8000; // Truncate scraped content to fit Haiku context

export async function runContentIngest(
  input: ContentIngestInput
): Promise<ContentIngestResult> {
  const { url, contentId } = input;

  // Create workflow run
  const runId = await createWorkflowRun("content-ingest", contentId ?? null);

  try {
    // 1. Scrape URL via Firecrawl
    const fc = getFirecrawl();
    const doc = await fc.scrape(url, { formats: ["markdown"] });

    const markdown = (doc.markdown ?? "").slice(0, MAX_CONTENT_TOKENS * 4); // ~4 chars per token
    const metadata = doc.metadata ?? {};

    // 2. Extract themes + summary via Haiku
    const { data } = await generateStructured({
      model: "haiku",
      system:
        "Extract the main themes, a 2-sentence summary, the article title, and author (if present) from this content.",
      messages: [
        {
          role: "user",
          content: markdown || `Content from ${url} (metadata: ${JSON.stringify(metadata)})`,
        },
      ],
      schema: themeSchema,
      maxTokens: 1024,
    });

    const title = data.title || metadata.title || url;
    const author = data.author || String(metadata.author ?? "") || "Unknown";
    const slug = title
      .toLowerCase()
      .replace(/[^a-z0-9\s-]/g, "")
      .replace(/\s+/g, "-")
      .replace(/-+/g, "-")
      .slice(0, 80);

    // 3. Create or update ContentPiece
    let pieceId = contentId;
    if (!pieceId) {
      const createResult = await runCypher(
        `CREATE (c:ContentPiece {
          id: randomUUID(), title: $title, slug: $slug,
          author: $author, url: $url, stage: "inspiration",
          createdAt: datetime(), updatedAt: datetime()
        })
        WITH c
        MATCH (s:PipelineStage {name: "inspiration"})
        CREATE (c)-[:IN_STAGE {enteredAt: datetime()}]->(s)
        WITH c
        MERGE (a:Author {name: $author})
        ON CREATE SET a.id = randomUUID()
        CREATE (a)-[:WROTE]->(c)
        RETURN c.id AS id`,
        { title, slug, author, url }
      );
      pieceId = createResult[0].id as string;
    } else {
      // Update existing piece with scraped data
      await runCypher(
        `MATCH (c:ContentPiece {id: $id})
         SET c.url = $url, c.updatedAt = datetime()`,
        { id: pieceId, url }
      );
    }

    // 4. Store summary on content piece
    await runCypher(
      `MATCH (c:ContentPiece {id: $id})
       SET c.summary = $summary`,
      { id: pieceId, summary: data.summary }
    );

    // 5. Create Theme nodes + HAS_THEME relationships
    for (const themeName of data.themes) {
      await runCypher(
        `MERGE (t:Theme {name: $name})
         ON CREATE SET t.id = randomUUID()
         WITH t
         MATCH (c:ContentPiece {id: $contentId})
         MERGE (c)-[:HAS_THEME]->(t)`,
        { name: themeName, contentId: pieceId }
      );
    }

    // 6. Embed summary for similarity search
    const vectors = await embedBatch([data.summary]);
    if (vectors.length > 0) {
      await runCypher(
        `MATCH (c:ContentPiece {id: $id})
         SET c.summaryEmbedding = $vector`,
        { id: pieceId, vector: vectors[0] }
      );
    }

    // Link workflow run to content piece (if we just created it)
    if (!contentId) {
      await runCypher(
        `MATCH (w:WorkflowRun {id: $runId})
         MATCH (c:ContentPiece {id: $contentId})
         CREATE (c)-[:HAS_WORKFLOW_RUN]->(w)`,
        { runId, contentId: pieceId }
      );
    }

    // Mark workflow complete
    const summaryText = `Ingested "${title}" — ${data.themes.length} themes extracted`;
    await completeWorkflowRun(runId, summaryText);

    return {
      workflowRun: {
        id: runId,
        type: "content-ingest",
        contentId: pieceId,
        status: "completed",
        startedAt: new Date().toISOString(),
        summary: summaryText,
      },
      contentPiece: {
        id: pieceId!,
        title,
        slug,
        author,
        url,
        stage: "inspiration",
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
      themes: data.themes,
    };
  } catch (error) {
    await failWorkflowRun(runId, error);
    throw error;
  }
}
