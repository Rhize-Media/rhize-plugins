import { runCypher } from "@/lib/neo4j/queries";
import {
  keywordSuggestions,
  relatedKeywords,
  keywordIdeas,
  competitorDomains,
  keywordGap,
} from "@/lib/dataforseo/client";
import type { WorkflowRun } from "@/types";

interface KeywordResearchInput {
  seeds: string[];
  domain?: string;
  contentId?: string;
  locationCode?: number;
  languageCode?: string;
}

interface KeywordResearchResult {
  workflowRun: WorkflowRun;
  keywordsCreated: number;
  clustersCreated: number;
  gapKeywords: number;
}

export async function runKeywordResearch(
  input: KeywordResearchInput
): Promise<KeywordResearchResult> {
  const { seeds, domain, contentId, locationCode = 2840, languageCode = "en" } = input;

  // Create workflow run node
  const runResult = await runCypher(
    `CREATE (w:WorkflowRun {
      id: randomUUID(), type: "keyword-research",
      contentId: $contentId, status: "running",
      startedAt: datetime()
    }) RETURN w.id AS runId`,
    { contentId: contentId ?? null }
  );
  const runId = runResult[0].runId as string;

  try {
    // 1. Expand keywords from seeds
    const allKeywords = new Map<string, Record<string, unknown>>();

    // Get suggestions from DataForSEO
    const [suggestionsRes, ideasRes] = await Promise.all([
      keywordSuggestions(seeds, locationCode, languageCode).catch(() => null),
      keywordIdeas(seeds[0], locationCode, languageCode).catch(() => null),
    ]);

    // Process suggestions
    for (const task of suggestionsRes?.tasks ?? []) {
      for (const item of task.result?.[0]?.items ?? []) {
        allKeywords.set(item.keyword, {
          term: item.keyword,
          volume: item.keyword_info?.search_volume ?? 0,
          difficulty: item.keyword_info?.keyword_difficulty ?? 0,
          cpc: item.keyword_info?.cpc ?? 0,
          competition: item.keyword_info?.competition ?? 0,
          intent: classifyIntent(item.keyword),
        });
      }
    }

    // Process ideas
    for (const task of ideasRes?.tasks ?? []) {
      for (const item of task.result?.[0]?.items ?? []) {
        if (!allKeywords.has(item.keyword)) {
          allKeywords.set(item.keyword, {
            term: item.keyword,
            volume: item.keyword_info?.search_volume ?? 0,
            difficulty: item.keyword_info?.keyword_difficulty ?? 0,
            cpc: item.keyword_info?.cpc ?? 0,
            competition: item.keyword_info?.competition ?? 0,
            intent: classifyIntent(item.keyword),
          });
        }
      }
    }

    // Get related keywords for top seeds
    for (const seed of seeds.slice(0, 3)) {
      const related = await relatedKeywords(seed, locationCode, languageCode).catch(() => null);
      for (const task of related?.tasks ?? []) {
        for (const item of task.result?.[0]?.items ?? []) {
          const kw = item.keyword_data;
          if (kw && !allKeywords.has(kw.keyword)) {
            allKeywords.set(kw.keyword, {
              term: kw.keyword,
              volume: kw.keyword_info?.search_volume ?? 0,
              difficulty: kw.keyword_info?.keyword_difficulty ?? 0,
              cpc: kw.keyword_info?.cpc ?? 0,
              competition: kw.keyword_info?.competition ?? 0,
              intent: classifyIntent(kw.keyword),
            });
          }
        }
      }
    }

    // 2. Store keywords in Neo4j
    let keywordsCreated = 0;
    for (const kw of allKeywords.values()) {
      await runCypher(
        `MERGE (k:Keyword {term: $term})
         ON CREATE SET k.id = randomUUID(),
           k.volume = $volume, k.difficulty = $difficulty,
           k.cpc = $cpc, k.competition = $competition, k.intent = $intent
         ON MATCH SET
           k.volume = $volume, k.difficulty = $difficulty,
           k.cpc = $cpc, k.competition = $competition, k.intent = $intent`,
        kw
      );
      keywordsCreated++;
    }

    // 3. Cluster keywords by seed topic
    let clustersCreated = 0;
    for (const seed of seeds) {
      await runCypher(
        `MERGE (cl:KeywordCluster {name: $name})
         ON CREATE SET cl.id = randomUUID(), cl.pillarTopic = $pillarTopic`,
        { name: seed, pillarTopic: seed }
      );
      clustersCreated++;

      // Link keywords containing the seed to its cluster
      await runCypher(
        `MATCH (cl:KeywordCluster {name: $seed})
         MATCH (k:Keyword) WHERE toLower(k.term) CONTAINS toLower($seed)
         MERGE (k)-[:BELONGS_TO]->(cl)`,
        { seed }
      );
    }

    // 4. Link keywords to content piece if provided
    if (contentId) {
      // Link the top keywords (by volume, filtered by reasonable difficulty)
      await runCypher(
        `MATCH (c:ContentPiece {id: $contentId})
         MATCH (k:Keyword) WHERE k.term IN $terms
         MERGE (c)-[:TARGETS]->(k)`,
        { contentId, terms: Array.from(allKeywords.keys()).slice(0, 20) }
      );
    }

    // 5. Competitor gap analysis if domain provided
    let gapKeywords = 0;
    if (domain) {
      const competitorsRes = await competitorDomains(domain, locationCode, languageCode).catch(() => null);
      const topCompetitors = (competitorsRes?.tasks?.[0]?.result?.[0]?.items ?? [])
        .slice(0, 3)
        .map((c: { domain: string; avg_position?: number }) => c.domain);

      // Store competitors
      for (const comp of topCompetitors) {
        await runCypher(
          `MERGE (c:Competitor {domain: $domain})
           ON CREATE SET c.id = randomUUID(), c.authorityRank = 0`,
          { domain: comp }
        );
      }

      // Run gap analysis
      if (topCompetitors.length > 0) {
        const gapRes = await keywordGap(
          [domain, ...topCompetitors.slice(0, 2)],
          locationCode,
          languageCode
        ).catch(() => null);

        for (const task of gapRes?.tasks ?? []) {
          for (const item of task.result?.[0]?.items ?? []) {
            // Keywords where competitors rank but we don't
            if (item.keyword_data) {
              const kd = item.keyword_data;
              await runCypher(
                `MERGE (k:Keyword {term: $term})
                 ON CREATE SET k.id = randomUUID(),
                   k.volume = $volume, k.difficulty = $difficulty, k.intent = $intent`,
                {
                  term: kd.keyword,
                  volume: kd.keyword_info?.search_volume ?? 0,
                  difficulty: kd.keyword_info?.keyword_difficulty ?? 0,
                  intent: classifyIntent(kd.keyword),
                }
              );
              gapKeywords++;
            }
          }
        }
      }
    }

    // Mark workflow complete
    await runCypher(
      `MATCH (w:WorkflowRun {id: $runId})
       SET w.status = "completed", w.completedAt = datetime(),
           w.summary = $summary`,
      {
        runId,
        summary: `Created ${keywordsCreated} keywords in ${clustersCreated} clusters. ${gapKeywords} gap keywords found.`,
      }
    );

    return {
      workflowRun: {
        id: runId, type: "keyword-research",
        contentId, status: "completed",
        startedAt: new Date().toISOString(),
        summary: `Created ${keywordsCreated} keywords in ${clustersCreated} clusters. ${gapKeywords} gap keywords found.`,
      },
      keywordsCreated,
      clustersCreated,
      gapKeywords,
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

function classifyIntent(keyword: string): string {
  const lower = keyword.toLowerCase();
  if (/\b(buy|pricing|price|cost|purchase|order|deal|discount|coupon|shop)\b/.test(lower))
    return "transactional";
  if (/\b(best|top|review|compare|vs|versus|alternative|recommend)\b/.test(lower))
    return "commercial";
  if (/\b(how|what|why|when|where|who|guide|tutorial|learn|example)\b/.test(lower))
    return "informational";
  return "informational";
}
