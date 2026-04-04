import { NextResponse } from "next/server";
import { runCypher } from "@/lib/neo4j/queries";
import { serpLive } from "@/lib/dataforseo/client";

// Vercel Cron: runs weekly for broader SERP feature analysis
// Configure in vercel.json: { "crons": [{ "path": "/api/cron/serp-snapshot", "schedule": "0 7 * * 1" }] }

export async function GET() {
  try {
    // Get all content with published URLs for SERP monitoring
    const content = await runCypher(
      `MATCH (c:ContentPiece)-[:IN_STAGE]->(s:PipelineStage)
       WHERE s.name IN ["published", "monitor"] AND c.url IS NOT NULL
       MATCH (c)-[:TARGETS]->(k:Keyword)
       RETURN c.id AS contentId, c.url AS url, collect(k { .id, .term }) AS keywords`
    );

    if (content.length === 0) {
      return NextResponse.json({
        message: "No published content to snapshot",
        updated: 0,
      });
    }

    let updated = 0;

    for (const piece of content) {
      const keywords = piece.keywords as { id: string; term: string }[];

      for (const kw of keywords) {
        const data = await serpLive(kw.term).catch(() => null);
        const task = data?.tasks?.[0];
        if (!task?.result?.[0]?.items) continue;

        const items = task.result[0].items;
        const match = items.find(
          (item: { url?: string }) =>
            item.url && piece.url && (item.url as string).includes(piece.url as string)
        );

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
            contentId: piece.contentId,
            keywordId: kw.id,
            position: match?.rank_absolute ?? match?.rank_group ?? 0,
            features: task.result[0].item_types ?? [],
            aiOverviewCited: (task.result[0].item_types ?? []).includes(
              "ai_overview"
            ),
          }
        );
        updated++;
      }
    }

    return NextResponse.json({ message: "SERP snapshot complete", updated });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
