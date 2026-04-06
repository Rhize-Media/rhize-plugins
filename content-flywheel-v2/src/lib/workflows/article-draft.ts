import { runCypher, moveContentToStage } from "@/lib/neo4j/queries";
import { generateText } from "@/lib/ai/claude";
import type { CacheableSystemMessage, TokenUsage } from "@/lib/ai/claude";
import {
  createWorkflowRun,
  completeWorkflowRun,
  failWorkflowRun,
} from "@/lib/workflows/helpers";
import type { WorkflowRun, Draft, OutlineSection } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ArticleDraftInput {
  contentId: string;
}

interface ArticleDraftResult {
  workflowRun: WorkflowRun;
  draft: Draft;
  totalCost: number;
}

// ---------------------------------------------------------------------------
// Concurrency limiter
// ---------------------------------------------------------------------------

const MAX_CONCURRENT = 3;

async function mapWithConcurrency<T, R>(
  items: T[],
  fn: (item: T, index: number) => Promise<R>
): Promise<R[]> {
  const results: R[] = new Array(items.length);
  let nextIndex = 0;

  async function worker(): Promise<void> {
    while (nextIndex < items.length) {
      const i = nextIndex++;
      results[i] = await fn(items[i], i);
    }
  }

  const workers = Array.from(
    { length: Math.min(MAX_CONCURRENT, items.length) },
    () => worker()
  );
  await Promise.all(workers);
  return results;
}

// ---------------------------------------------------------------------------
// System prompt (cached across all section generations)
// ---------------------------------------------------------------------------

const SYSTEM_PROMPT: CacheableSystemMessage[] = [
  {
    type: "text",
    text: `You are an expert content writer producing high-quality, SEO-optimized article sections.

Guidelines:
- Write in a clear, engaging, professional tone
- Use short paragraphs (2-3 sentences) for readability
- Include relevant examples and data points where appropriate
- Use transition sentences to connect ideas smoothly
- Write for expertise, experience, authoritativeness, and trustworthiness (E-E-A-T)
- Use markdown formatting: ## for H2 headings, ### for H3 subheadings, **bold** for emphasis
- Target the specified word count for each section
- Do NOT include the H2 heading itself — it will be added programmatically`,
    cache_control: { type: "ephemeral" },
  },
];

// ---------------------------------------------------------------------------
// Main workflow
// ---------------------------------------------------------------------------

export async function runArticleDraft(
  input: ArticleDraftInput
): Promise<ArticleDraftResult> {
  const { contentId } = input;

  const runId = await createWorkflowRun("article-draft", contentId, {
    requireContent: true,
  });

  try {
    // 1. Load outline from Neo4j
    const outlineResult = await runCypher(
      `MATCH (c:ContentPiece {id: $contentId})-[:HAS_OUTLINE]->(o:Outline)
       RETURN o.title AS title, o.metaDescription AS metaDescription,
              o.sections AS sections, o.faqTopics AS faqTopics
       ORDER BY o.createdAt DESC
       LIMIT 1`,
      { contentId }
    );

    if (outlineResult.length === 0) {
      throw new Error(
        `No outline found for content ${contentId}. Generate an outline first.`
      );
    }

    const outline = outlineResult[0];
    const title = outline.title as string;
    const sections: OutlineSection[] = JSON.parse(
      outline.sections as string
    );
    const faqTopics = outline.faqTopics as string[];

    // 2. Generate each section in parallel (max 3 concurrent)
    const usages: TokenUsage[] = [];

    const sectionContents = await mapWithConcurrency(
      sections,
      async (section, index) => {
        const result = await generateText({
          model: "sonnet",
          system: SYSTEM_PROMPT,
          messages: [
            {
              role: "user",
              content: `Write section ${index + 1} of ${sections.length} for the article "${title}".

## ${section.heading}

Key points to cover:
${section.bullets.map((b) => `- ${b}`).join("\n")}

Target word count: ${section.targetWordCount} words.`,
            },
          ],
          maxTokens: section.targetWordCount * 2, // Generous token budget
          temperature: 0.7,
          contentId,
        });

        usages.push(result.usage);
        return result.text;
      }
    );

    // 3. Assemble full article markdown
    const articleParts: string[] = [`# ${title}\n`];

    for (let i = 0; i < sections.length; i++) {
      articleParts.push(`## ${sections[i].heading}\n`);
      articleParts.push(sectionContents[i]);
      articleParts.push(""); // blank line between sections
    }

    // Add FAQ section if topics exist
    if (faqTopics.length > 0) {
      articleParts.push("## Frequently Asked Questions\n");
      for (const topic of faqTopics) {
        articleParts.push(`### ${topic}\n`);
      }
    }

    const content = articleParts.join("\n");
    const wordCount = content
      .split(/\s+/)
      .filter((w) => w.length > 0).length;

    // 4. Calculate total cost
    const totalCost = usages.reduce((sum, u) => sum + u.cost, 0);

    // 5. Create Draft node
    const draftResult = await runCypher(
      `CREATE (d:Draft {
        id: randomUUID(),
        contentId: $contentId,
        content: $content,
        wordCount: $wordCount,
        createdAt: datetime()
      })
      WITH d
      MATCH (c:ContentPiece {id: $contentId})
      CREATE (c)-[:HAS_DRAFT]->(d)
      RETURN d.id AS draftId`,
      { contentId, content, wordCount }
    );

    const draftId = draftResult[0].draftId as string;

    // 6. Move to optimize stage
    await moveContentToStage(contentId, "optimize");

    // Mark workflow complete
    const summaryText = `Generated ${wordCount}-word draft — ${sections.length} sections, $${totalCost.toFixed(4)} total cost`;
    await completeWorkflowRun(runId, summaryText);

    return {
      workflowRun: {
        id: runId,
        type: "article-draft",
        contentId,
        status: "completed",
        startedAt: new Date().toISOString(),
        summary: summaryText,
      },
      draft: {
        id: draftId,
        contentId,
        content,
        wordCount,
        createdAt: new Date().toISOString(),
      },
      totalCost,
    };
  } catch (error) {
    await failWorkflowRun(runId, error);
    throw error;
  }
}
