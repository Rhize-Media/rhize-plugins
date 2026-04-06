import { runCypher } from "@/lib/neo4j/queries";
import {
  backlinksSummary,
  backlinksReferringDomains,
  backlinksAnchors,
  backlinksNewLost,
} from "@/lib/dataforseo/client";
import type { WorkflowRun } from "@/types";

interface BacklinkAnalysisInput {
  contentId?: string;
  domain: string;
  locationCode?: number;
  languageCode?: string;
}

interface BacklinkProfile {
  totalBacklinks: number;
  referringDomains: number;
  domainRank: number;
  dofollowRatio: number;
  topReferrers: { domain: string; rank: number; backlinks: number }[];
  topAnchors: { anchor: string; count: number; percentage: number }[];
  newLinks: number;
  lostLinks: number;
}

interface BacklinkAnalysisResult {
  workflowRun: WorkflowRun;
  profile: BacklinkProfile;
  backlinkNodesCreated: number;
}

export async function runBacklinkAnalysis(
  input: BacklinkAnalysisInput
): Promise<BacklinkAnalysisResult> {
  const { contentId, domain } = input;

  const runResult = await runCypher(
    `CREATE (w:WorkflowRun {
      id: randomUUID(), type: "backlink-analysis",
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
    // Fetch all backlink data in parallel
    const [summaryRes, referrersRes, anchorsRes, newLostRes] = await Promise.all([
      backlinksSummary(domain).catch(() => null),
      backlinksReferringDomains(domain).catch(() => null),
      backlinksAnchors(domain).catch(() => null),
      backlinksNewLost(domain).catch(() => null),
    ]);

    // Parse summary
    const summary = summaryRes?.tasks?.[0]?.result?.[0] ?? {};
    const totalBacklinks = (summary.total_backlinks as number) ?? 0;
    const referringDomains = (summary.referring_domains as number) ?? 0;
    const domainRank = (summary.rank as number) ?? 0;
    const dofollow = (summary.dofollow as number) ?? 0;
    const dofollowRatio = totalBacklinks > 0 ? dofollow / totalBacklinks : 0;

    // Parse referring domains
    const referrerItems = referrersRes?.tasks?.[0]?.result?.[0]?.items ?? [];
    const topReferrers = referrerItems.slice(0, 20).map(
      (r: Record<string, unknown>) => ({
        domain: (r.domain as string) ?? "",
        rank: (r.rank as number) ?? 0,
        backlinks: (r.backlinks as number) ?? 0,
      })
    );

    // Parse anchors
    const anchorItems = anchorsRes?.tasks?.[0]?.result?.[0]?.items ?? [];
    const totalAnchorBacklinks = anchorItems.reduce(
      (sum: number, a: Record<string, unknown>) => sum + ((a.backlinks as number) ?? 0),
      0
    );
    const topAnchors = anchorItems.slice(0, 20).map(
      (a: Record<string, unknown>) => ({
        anchor: (a.anchor as string) ?? "",
        count: (a.backlinks as number) ?? 0,
        percentage:
          totalAnchorBacklinks > 0
            ? Math.round(((a.backlinks as number) ?? 0) / totalAnchorBacklinks * 100)
            : 0,
      })
    );

    // Parse new/lost
    const newLostItems = newLostRes?.tasks?.[0]?.result?.[0]?.items ?? [];
    let newLinks = 0;
    let lostLinks = 0;
    for (const item of newLostItems) {
      if ((item as Record<string, unknown>).type === "new") newLinks++;
      else lostLinks++;
    }

    // Store backlink sources in Neo4j
    let backlinkNodesCreated = 0;
    for (const ref of topReferrers) {
      await runCypher(
        `MERGE (b:BacklinkSource {domain: $domain})
         ON CREATE SET b.id = randomUUID()
         SET b.authorityRank = $rank, b.backlinks = $backlinks, b.updatedAt = datetime()`,
        { domain: ref.domain, rank: ref.rank, backlinks: ref.backlinks }
      );

      // Link to content if provided
      if (contentId) {
        await runCypher(
          `MATCH (c:ContentPiece {id: $contentId}), (b:BacklinkSource {domain: $refDomain})
           MERGE (c)-[r:HAS_BACKLINK_FROM]->(b)
           SET r.discoveredAt = coalesce(r.discoveredAt, datetime()),
               r.lastSeenAt = datetime()`,
          { contentId, refDomain: ref.domain }
        );
      }
      backlinkNodesCreated++;
    }

    // Store domain-level metrics
    await runCypher(
      `MERGE (c:Competitor {domain: $domain})
       ON CREATE SET c.id = randomUUID()
       SET c.authorityRank = $domainRank, c.totalBacklinks = $totalBacklinks,
           c.referringDomains = $referringDomains, c.updatedAt = datetime()`,
      { domain, domainRank, totalBacklinks, referringDomains }
    );

    // Link competitor to its backlink sources
    for (const ref of topReferrers) {
      await runCypher(
        `MATCH (comp:Competitor {domain: $domain}), (b:BacklinkSource {domain: $refDomain})
         MERGE (comp)-[:HAS_BACKLINK_FROM]->(b)`,
        { domain, refDomain: ref.domain }
      );
    }

    const profile: BacklinkProfile = {
      totalBacklinks,
      referringDomains,
      domainRank,
      dofollowRatio: Math.round(dofollowRatio * 100) / 100,
      topReferrers,
      topAnchors,
      newLinks,
      lostLinks,
    };

    const summaryText = `Backlinks: ${totalBacklinks}, Referring domains: ${referringDomains}, Domain rank: ${domainRank}. ${newLinks} new, ${lostLinks} lost in last 30 days. ${backlinkNodesCreated} sources stored.`;

    await runCypher(
      `MATCH (w:WorkflowRun {id: $runId})
       SET w.status = "completed", w.completedAt = datetime(), w.summary = $summary`,
      { runId, summary: summaryText }
    );

    return {
      workflowRun: {
        id: runId,
        type: "backlink-analysis",
        contentId,
        status: "completed",
        startedAt: new Date().toISOString(),
        summary: summaryText,
      },
      profile,
      backlinkNodesCreated,
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
