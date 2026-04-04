import { NextResponse } from "next/server";
import { runCypher } from "@/lib/neo4j/queries";
import { serpLiveBatch } from "@/lib/dataforseo/client";

// Vercel Cron: runs daily to pull keyword ranking data from DataForSEO
// Configure in vercel.json: { "crons": [{ "path": "/api/cron/seo-pull", "schedule": "0 6 * * *" }] }

export async function GET() {
  try {
    // Get all keywords we're tracking
    const keywords = await runCypher(
      `MATCH (c:ContentPiece)-[:TARGETS]->(k:Keyword)
       WHERE c.url IS NOT NULL
       RETURN DISTINCT k.term AS term, k.id AS keywordId, c.url AS url, c.id AS contentId`
    );

    if (keywords.length === 0) {
      return NextResponse.json({ message: "No keywords to track", updated: 0 });
    }

    const tasks = keywords.map((kw) => ({
      keyword: kw.term as string,
      url: kw.url as string,
    }));
    const data = await serpLiveBatch(tasks);

    let updated = 0;

    // Store results as SERP snapshots in Neo4j
    const dataTasks = data.tasks ?? [];
    for (let i = 0; i < dataTasks.length; i++) {
      const task = dataTasks[i];
      const kw = keywords[i];
      if (!task?.result?.[0]?.items) continue;

      const items = task.result[0].items;
      const match = items.find(
        (item: { url?: string }) => item.url && kw.url && item.url.includes(kw.url as string)
      );

      if (match) {
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
           CREATE (c)-[:RANKS_FOR]->(snap)`,
          {
            contentId: kw.contentId,
            keywordId: kw.keywordId,
            position: match.rank_absolute ?? match.rank_group ?? 0,
            features: task.result[0].item_types ?? [],
            aiOverviewCited: (task.result[0].item_types ?? []).includes(
              "ai_overview"
            ),
          }
        );
        updated++;
      }
    }

    return NextResponse.json({ message: "SEO pull complete", updated });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
