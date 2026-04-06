import { runCypher } from "@/lib/neo4j/queries";
import { serpLive, historicalRankOverview } from "@/lib/dataforseo/client";
import type { WorkflowRun } from "@/types";

interface SERPAnalysisInput {
  contentId?: string;
  keywords?: string[];
  domain?: string;
  locationCode?: number;
  languageCode?: string;
}

interface SERPAnalysisResult {
  workflowRun: WorkflowRun;
  snapshotsCreated: number;
  rankChanges: RankChange[];
  serpFeatures: Record<string, string[]>;
}

interface RankChange {
  keyword: string;
  currentPosition: number;
  previousPosition: number | null;
  change: number | null;
  features: string[];
  aiOverviewCited: boolean;
}

export async function runSERPAnalysis(
  input: SERPAnalysisInput
): Promise<SERPAnalysisResult> {
  const { contentId, keywords: inputKeywords, domain, locationCode = 2840, languageCode = "en" } = input;

  const runResult = await runCypher(
    `CREATE (w:WorkflowRun {
      id: randomUUID(), type: "serp-analysis",
      contentId: $contentId, status: "running",
      startedAt: datetime()
    })
    WITH w
    OPTIONAL MATCH (c:ContentPiece {id: $contentId})
    FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
      CREATE (c)-[:HAS_WORKFLOW_RUN]->(w)
    )
    RETURN w.id AS runId`,
    { contentId: contentId ?? null }
  );
  const runId = runResult[0].runId as string;

  try {
    // Determine which keywords to check
    let trackedKeywords: { term: string; keywordId: string; contentId: string; url: string }[] = [];

    if (contentId) {
      // Get keywords linked to specific content
      const rows = await runCypher(
        `MATCH (c:ContentPiece {id: $contentId})-[:TARGETS]->(k:Keyword)
         WHERE c.url IS NOT NULL
         RETURN k.term AS term, k.id AS keywordId, c.url AS url, c.id AS contentId`,
        { contentId }
      );
      trackedKeywords = rows as typeof trackedKeywords;
    } else if (inputKeywords && domain) {
      // Ad-hoc keywords + domain
      trackedKeywords = inputKeywords.map((term) => ({
        term,
        keywordId: "",
        contentId: "",
        url: domain,
      }));
    } else {
      // All tracked keywords
      const rows = await runCypher(
        `MATCH (c:ContentPiece)-[:TARGETS]->(k:Keyword)
         WHERE c.url IS NOT NULL
         RETURN DISTINCT k.term AS term, k.id AS keywordId, c.url AS url, c.id AS contentId`
      );
      trackedKeywords = rows as typeof trackedKeywords;
    }

    if (trackedKeywords.length === 0) {
      await markComplete(runId, "No keywords to analyze.");
      return {
        workflowRun: buildRun(runId, contentId, "No keywords to analyze."),
        snapshotsCreated: 0,
        rankChanges: [],
        serpFeatures: {},
      };
    }

    // Fetch SERP data
    let snapshotsCreated = 0;
    const rankChanges: RankChange[] = [];
    const serpFeatures: Record<string, string[]> = {};

    // Process in batches of 10
    for (let i = 0; i < trackedKeywords.length; i += 10) {
      const batch = trackedKeywords.slice(i, i + 10);

      for (const kw of batch) {
        const serpRes = await serpLive(kw.term, locationCode, languageCode).catch(() => null);
        const task = serpRes?.tasks?.[0];
        const items = task?.result?.[0]?.items ?? [];
        const itemTypes = task?.result?.[0]?.item_types ?? [];

        serpFeatures[kw.term] = itemTypes;

        // Find our position
        const match = items.find(
          (item: Record<string, unknown>) =>
            item.url && kw.url && (item.url as string).includes(kw.url)
        );

        const position = match?.rank_absolute ?? match?.rank_group ?? 0;
        const aiOverviewCited = itemTypes.includes("ai_overview");

        // Get previous position for comparison
        let previousPosition: number | null = null;
        if (kw.contentId && kw.keywordId) {
          const prev = await runCypher(
            `MATCH (snap:SERPSnapshot {contentId: $contentId, keywordId: $keywordId})
             RETURN snap.position AS position
             ORDER BY snap.date DESC LIMIT 1`,
            { contentId: kw.contentId, keywordId: kw.keywordId }
          );
          previousPosition = (prev[0]?.position as number) ?? null;
        }

        rankChanges.push({
          keyword: kw.term,
          currentPosition: position as number,
          previousPosition,
          change: previousPosition !== null ? (previousPosition as number) - (position as number) : null,
          features: itemTypes,
          aiOverviewCited,
        });

        // Store snapshot
        if (kw.contentId) {
          await runCypher(
            `MATCH (c:ContentPiece {id: $contentId})
             CREATE (snap:SERPSnapshot {
               id: randomUUID(),
               contentId: $contentId,
               keywordId: $keywordId,
               position: $position,
               date: date(),
               features: $features,
               aiOverviewCited: $aiOverviewCited
             })
             CREATE (c)-[:RANKS_FOR]->(snap)
             WITH snap
             OPTIONAL MATCH (k:Keyword {id: $keywordId})
             FOREACH (_ IN CASE WHEN k IS NOT NULL THEN [1] ELSE [] END |
               CREATE (snap)-[:FOR_KEYWORD]->(k)
             )`,
            {
              contentId: kw.contentId,
              keywordId: kw.keywordId,
              position,
              features: itemTypes,
              aiOverviewCited,
            }
          );
          snapshotsCreated++;
        }
      }
    }

    // Historical rank data for domain if provided
    if (domain) {
      const histRes = await historicalRankOverview(domain, locationCode, languageCode).catch(() => null);
      if (histRes?.tasks?.[0]?.result?.[0]) {
        const hist = histRes.tasks[0].result[0];
        await runCypher(
          `MERGE (c:Competitor {domain: $domain})
           SET c.organicCount = $organicCount, c.etv = $etv, c.updatedAt = datetime()`,
          {
            domain,
            organicCount: hist.metrics?.organic?.count ?? 0,
            etv: hist.metrics?.organic?.etv ?? 0,
          }
        );
      }
    }

    const summary = `${snapshotsCreated} snapshots created. ${rankChanges.filter((r) => r.change !== null && r.change > 0).length} improved, ${rankChanges.filter((r) => r.change !== null && r.change < 0).length} declined.`;
    await markComplete(runId, summary);

    return {
      workflowRun: buildRun(runId, contentId, summary),
      snapshotsCreated,
      rankChanges,
      serpFeatures,
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

async function markComplete(runId: string, summary: string) {
  await runCypher(
    `MATCH (w:WorkflowRun {id: $runId})
     SET w.status = "completed", w.completedAt = datetime(), w.summary = $summary`,
    { runId, summary }
  );
}

function buildRun(runId: string, contentId?: string, summary?: string): WorkflowRun {
  return {
    id: runId,
    type: "serp-analysis",
    contentId,
    status: "completed",
    startedAt: new Date().toISOString(),
    summary,
  };
}
