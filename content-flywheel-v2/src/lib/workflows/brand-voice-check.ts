import { z } from "zod";
import { runCypher } from "@/lib/neo4j/queries";
import { generateStructured } from "@/lib/ai/claude";
import {
  createWorkflowRun,
  completeWorkflowRun,
  failWorkflowRun,
} from "@/lib/workflows/helpers";
import type { WorkflowRun, BrandVoiceScore } from "@/types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BrandVoiceCheckInput {
  contentId: string;
}

interface BrandVoiceCheckResult {
  workflowRun: WorkflowRun;
  brandVoiceScore: BrandVoiceScore;
}

// ---------------------------------------------------------------------------
// Scoring schema
// ---------------------------------------------------------------------------

const brandVoiceSchema = z.object({
  score: z.number().min(0).max(100),
  issues: z.array(
    z.object({
      section: z.string(),
      issue: z.string(),
      suggestion: z.string(),
    })
  ),
});

// ---------------------------------------------------------------------------
// Main workflow
// ---------------------------------------------------------------------------

export async function runBrandVoiceCheck(
  input: BrandVoiceCheckInput
): Promise<BrandVoiceCheckResult> {
  const { contentId } = input;

  const runId = await createWorkflowRun("brand-voice-check", contentId, {
    requireContent: true,
  });

  try {
    // 1. Load draft content from Neo4j
    const draftResult = await runCypher(
      `MATCH (c:ContentPiece {id: $contentId})-[:HAS_DRAFT]->(d:Draft)
       RETURN d.content AS content, c.title AS title
       ORDER BY d.createdAt DESC
       LIMIT 1`,
      { contentId }
    );

    if (draftResult.length === 0) {
      throw new Error(
        `No draft found for content ${contentId}. Generate a draft first.`
      );
    }

    const draftContent = draftResult[0].content as string;
    const title = draftResult[0].title as string;

    // 2. Score via Haiku
    const { data } = await generateStructured({
      model: "haiku",
      system: `You are a brand voice editor. Evaluate the following article draft against professional content standards.

Score from 0-100 based on:
- Tone consistency (professional, engaging, authoritative)
- Clarity and readability (short paragraphs, active voice)
- SEO-friendly structure (headings, formatting, keyword usage)
- E-E-A-T signals (expertise, citations, credibility markers)
- Brand alignment (no jargon, consistent terminology)

For each issue found, identify the section heading, describe the issue, and provide a specific suggestion.
A score of 80+ means the draft is ready for publishing with minor edits.
A score of 60-79 means significant revision is needed.
A score below 60 means a rewrite is recommended.`,
      messages: [
        {
          role: "user",
          content: `Evaluate this article draft:\n\nTitle: ${title}\n\n${draftContent}`,
        },
      ],
      schema: brandVoiceSchema,
      maxTokens: 2048,
      contentId,
    });

    // 3. Create BrandVoiceScore node
    const scoreResult = await runCypher(
      `CREATE (b:BrandVoiceScore {
        id: randomUUID(),
        contentId: $contentId,
        score: $score,
        issues: $issues,
        createdAt: datetime()
      })
      WITH b
      MATCH (c:ContentPiece {id: $contentId})
      CREATE (c)-[:HAS_BRAND_VOICE_SCORE]->(b)
      RETURN b.id AS scoreId`,
      {
        contentId,
        score: data.score,
        issues: JSON.stringify(data.issues),
      }
    );

    const scoreId = scoreResult[0].scoreId as string;

    // Mark workflow complete
    const summaryText = `Brand voice score: ${data.score}/100 — ${data.issues.length} issues found`;
    await completeWorkflowRun(runId, summaryText);

    return {
      workflowRun: {
        id: runId,
        type: "brand-voice-check",
        contentId,
        status: "completed",
        startedAt: new Date().toISOString(),
        summary: summaryText,
      },
      brandVoiceScore: {
        id: scoreId,
        contentId,
        score: data.score,
        issues: data.issues,
        createdAt: new Date().toISOString(),
      },
    };
  } catch (error) {
    await failWorkflowRun(runId, error);
    throw error;
  }
}
