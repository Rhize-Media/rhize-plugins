import { runCypher } from "@/lib/neo4j/queries";
import { aiOptimizationBrandMentions } from "@/lib/dataforseo/client";
import type { WorkflowRun } from "@/types";

interface AIVisibilityInput {
  contentId?: string;
  brand: string;
  queries?: string[];
  locationCode?: number;
  languageCode?: string;
}

interface AIVisibilityResult {
  workflowRun: WorkflowRun;
  snapshots: AISnapshot[];
  overallMentionRate: number;
  overallAccuracy: number;
}

interface AISnapshot {
  query: string;
  llm: string;
  mentioned: boolean;
  accuracy: number;
  citationCount: number;
  position?: number;
}

export async function runAIVisibility(
  input: AIVisibilityInput
): Promise<AIVisibilityResult> {
  const { contentId, brand, queries: inputQueries } = input;

  const runResult = await runCypher(
    `CREATE (w:WorkflowRun {
      id: randomUUID(), type: "ai-visibility",
      contentId: $contentId, status: "running",
      startedAt: datetime()
    }) RETURN w.id AS runId`,
    { contentId: contentId ?? null }
  );
  const runId = runResult[0].runId as string;

  try {
    // Determine queries to check
    let queries: string[] = inputQueries ?? [];

    if (queries.length === 0 && contentId) {
      // Use keywords linked to content as queries
      const rows = await runCypher(
        `MATCH (c:ContentPiece {id: $contentId})-[:TARGETS]->(k:Keyword)
         RETURN k.term AS term ORDER BY k.volume DESC LIMIT 10`,
        { contentId }
      );
      queries = rows.map((r) => r.term as string);
    }

    if (queries.length === 0) {
      // Fall back to brand-related queries
      queries = [
        `what is ${brand}`,
        `${brand} review`,
        `best ${brand} alternatives`,
        `${brand} vs competitors`,
      ];
    }

    const snapshots: AISnapshot[] = [];
    let totalMentions = 0;
    let totalAccuracy = 0;
    let totalChecks = 0;

    // Check brand mentions via DataForSEO AI Optimization
    for (const query of queries) {
      const res = await aiOptimizationBrandMentions(brand, [query]).catch(() => null);

      const tasks = res?.tasks ?? [];
      for (const task of tasks) {
        const items = task.result?.[0]?.items ?? [];

        if (items.length === 0) {
          // No results — record as not mentioned
          snapshots.push({
            query,
            llm: "unknown",
            mentioned: false,
            accuracy: 0,
            citationCount: 0,
          });
          totalChecks++;
          continue;
        }

        for (const item of items) {
          const mentioned = (item.is_mentioned as boolean) ?? false;
          const accuracy = (item.accuracy as number) ?? 0;
          const citationCount = (item.citation_count as number) ?? 0;
          const llm = (item.llm as string) ?? "unknown";
          const position = item.position as number | undefined;

          snapshots.push({
            query,
            llm,
            mentioned,
            accuracy,
            citationCount,
            position,
          });

          if (mentioned) totalMentions++;
          totalAccuracy += accuracy;
          totalChecks++;
        }
      }
    }

    const overallMentionRate = totalChecks > 0 ? Math.round((totalMentions / totalChecks) * 100) : 0;
    const overallAccuracy = totalChecks > 0 ? Math.round(totalAccuracy / totalChecks) : 0;

    // Persist snapshots to Neo4j
    for (const snap of snapshots) {
      await runCypher(
        `CREATE (a:AIVisibilitySnapshot {
           id: randomUUID(),
           contentId: $contentId,
           query: $query,
           llm: $llm,
           mentioned: $mentioned,
           mentionRate: $mentionRate,
           accuracy: $accuracy,
           citationCount: $citationCount,
           date: datetime()
         })`,
        {
          contentId: contentId ?? null,
          query: snap.query,
          llm: snap.llm,
          mentioned: snap.mentioned,
          mentionRate: snap.mentioned ? 100 : 0,
          accuracy: snap.accuracy,
          citationCount: snap.citationCount,
        }
      );

      // Link to content if provided
      if (contentId) {
        await runCypher(
          `MATCH (c:ContentPiece {id: $contentId}),
                 (a:AIVisibilitySnapshot {contentId: $contentId})
           WHERE a.query = $query AND a.llm = $llm
           MERGE (c)-[:HAS_AI_VISIBILITY]->(a)`,
          { contentId, query: snap.query, llm: snap.llm }
        );
      }
    }

    const summaryText = `AI Visibility: ${overallMentionRate}% mention rate, ${overallAccuracy}% accuracy across ${totalChecks} checks. ${totalMentions}/${totalChecks} queries mention the brand.`;

    await runCypher(
      `MATCH (w:WorkflowRun {id: $runId})
       SET w.status = "completed", w.completedAt = datetime(), w.summary = $summary`,
      { runId, summary: summaryText }
    );

    return {
      workflowRun: {
        id: runId,
        type: "ai-visibility",
        contentId,
        status: "completed",
        startedAt: new Date().toISOString(),
        summary: summaryText,
      },
      snapshots,
      overallMentionRate,
      overallAccuracy,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    await runCypher(
      `MATCH (w:WorkflowRun {id: $runId})
       SET w.status = "failed", w.completedAt = datetime(), w.error = $error`,
      { runId, error: message }
    );
    throw error;
  }
}
