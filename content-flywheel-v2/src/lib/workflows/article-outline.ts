import { z } from "zod";
import { runCypher, moveContentToStage } from "@/lib/neo4j/queries";
import { generateStructured } from "@/lib/ai/claude";
import { createWorkflowRun, completeWorkflowRun, failWorkflowRun } from "@/lib/workflows/helpers";
import type { CacheableSystemMessage } from "@/lib/ai/claude";
import type { WorkflowRun, Outline } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ArticleOutlineInput {
  contentId: string;
}

interface ArticleOutlineResult {
  workflowRun: WorkflowRun;
  outline: Outline;
}

// ---------------------------------------------------------------------------
// Outline schema for structured output
// ---------------------------------------------------------------------------

const outlineSchema = z.object({
  title: z.string(),
  metaDescription: z.string(),
  sections: z.array(
    z.object({
      heading: z.string(),
      bullets: z.array(z.string()),
      targetWordCount: z.number(),
    })
  ),
  faqTopics: z.array(z.string()),
  internalLinks: z.array(z.string()),
});

// ---------------------------------------------------------------------------
// System prompt (cached for cost savings)
// ---------------------------------------------------------------------------

const SYSTEM_PROMPT: CacheableSystemMessage[] = [
  {
    type: "text",
    text: `You are an expert content strategist and SEO specialist. Generate a comprehensive article outline optimized for search engines and reader engagement.

Guidelines:
- Title should be compelling and include the primary keyword naturally
- Meta description should be 150-160 characters, action-oriented
- Each section (H2) should target a specific aspect of the topic
- Include 5-8 H2 sections with 3-5 bullet points each
- Target word counts should sum to 1500-3000 words total
- FAQ topics should address common questions (featured snippet opportunities)
- Internal links should reference related content by title
- Write for expertise, experience, authoritativeness, and trustworthiness (E-E-A-T)`,
    cache_control: { type: "ephemeral" },
  },
];

// ---------------------------------------------------------------------------
// Main workflow
// ---------------------------------------------------------------------------

export async function runArticleOutline(
  input: ArticleOutlineInput
): Promise<ArticleOutlineResult> {
  const { contentId } = input;

  // Create workflow run
  const runId = await createWorkflowRun("article-outline", contentId, {
    requireContent: true,
  });

  try {
    // 1. Load content context from Neo4j
    const contentResult = await runCypher(
      `MATCH (c:ContentPiece {id: $contentId})
       OPTIONAL MATCH (c)-[:TARGETS]->(k:Keyword)
       OPTIONAL MATCH (c)-[:HAS_THEME]->(t:Theme)
       RETURN c.title AS title, c.summary AS summary, c.url AS url,
              collect(DISTINCT k.term) AS keywords,
              collect(DISTINCT t.name) AS themes`,
      { contentId }
    );

    if (contentResult.length === 0) {
      throw new Error(`Content piece ${contentId} not found`);
    }

    const content = contentResult[0];
    const title = content.title as string;
    const keywords = content.keywords as string[];
    const themes = content.themes as string[];
    const summary = content.summary as string | null;

    // 2. Load competitor SERP data for target keywords
    const serpResult = await runCypher(
      `MATCH (c:ContentPiece {id: $contentId})-[:TARGETS]->(k:Keyword)
       OPTIONAL MATCH (ss:SERPSnapshot)-[:FOR_KEYWORD]->(k)
       RETURN k.term AS keyword, ss.position AS position
       ORDER BY k.volume DESC
       LIMIT 10`,
      { contentId }
    );

    // 3. Load internal linking opportunities (other published content)
    const internalResult = await runCypher(
      `MATCH (other:ContentPiece)-[:IN_STAGE]->(:PipelineStage {name: "published"})
       WHERE other.id <> $contentId
       RETURN other.title AS title, other.slug AS slug
       LIMIT 10`,
      { contentId }
    );

    const publishedContent = internalResult.map(
      (r) => `${r.title} (/blog/${r.slug})`
    );

    // 4. Generate outline via Sonnet (with cached system prompt)
    const userMessage = buildUserPrompt({
      title,
      summary,
      keywords,
      themes,
      serpData: serpResult.map((r) => ({
        keyword: r.keyword as string,
        position: r.position as number | null,
      })),
      internalLinks: publishedContent,
    });

    const { data } = await generateStructured({
      model: "sonnet",
      system: SYSTEM_PROMPT,
      messages: [{ role: "user", content: userMessage }],
      schema: outlineSchema,
      maxTokens: 4096,
      contentId,
    });

    // 5. Store Outline node in Neo4j
    const outlineResult = await runCypher(
      `CREATE (o:Outline {
        id: randomUUID(),
        contentId: $contentId,
        title: $title,
        metaDescription: $metaDescription,
        sections: $sections,
        faqTopics: $faqTopics,
        internalLinks: $internalLinks,
        createdAt: datetime()
      })
      WITH o
      MATCH (c:ContentPiece {id: $contentId})
      CREATE (c)-[:HAS_OUTLINE]->(o)
      RETURN o.id AS outlineId`,
      {
        contentId,
        title: data.title,
        metaDescription: data.metaDescription,
        sections: JSON.stringify(data.sections),
        faqTopics: data.faqTopics,
        internalLinks: data.internalLinks,
      }
    );

    const outlineId = outlineResult[0].outlineId as string;

    // 6. Move content to draft stage
    await moveContentToStage(contentId, "draft");

    // Mark workflow complete
    const summaryText = `Generated outline "${data.title}" — ${data.sections.length} sections, ${data.faqTopics.length} FAQs`;
    await completeWorkflowRun(runId, summaryText);

    return {
      workflowRun: {
        id: runId,
        type: "article-outline",
        contentId,
        status: "completed",
        startedAt: new Date().toISOString(),
        summary: summaryText,
      },
      outline: {
        id: outlineId,
        contentId,
        title: data.title,
        metaDescription: data.metaDescription,
        sections: data.sections,
        faqTopics: data.faqTopics,
        internalLinks: data.internalLinks,
        createdAt: new Date().toISOString(),
      },
    };
  } catch (error) {
    await failWorkflowRun(runId, error);
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Build user prompt with context
// ---------------------------------------------------------------------------

function buildUserPrompt(ctx: {
  title: string;
  summary: string | null;
  keywords: string[];
  themes: string[];
  serpData: { keyword: string; position: number | null }[];
  internalLinks: string[];
}): string {
  const parts: string[] = [`Topic: ${ctx.title}`];

  if (ctx.summary) {
    parts.push(`Summary: ${ctx.summary}`);
  }

  if (ctx.keywords.length > 0) {
    parts.push(`Target keywords: ${ctx.keywords.join(", ")}`);
  }

  if (ctx.themes.length > 0) {
    parts.push(`Themes: ${ctx.themes.join(", ")}`);
  }

  if (ctx.serpData.length > 0) {
    const serpInfo = ctx.serpData
      .filter((s) => s.position != null)
      .map((s) => `"${s.keyword}" (current position: ${s.position})`)
      .join(", ");
    if (serpInfo) {
      parts.push(`Current SERP positions: ${serpInfo}`);
    }
  }

  if (ctx.internalLinks.length > 0) {
    parts.push(
      `Available internal links:\n${ctx.internalLinks.map((l) => `- ${l}`).join("\n")}`
    );
  }

  parts.push(
    "\nGenerate a comprehensive article outline optimized for these keywords and themes."
  );

  return parts.join("\n\n");
}
