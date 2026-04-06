import { NextRequest, NextResponse } from "next/server";
import { runCypher } from "@/lib/neo4j/queries";

// GoHighLevel webhook receiver — fires when a social post is published.
// Configure in GHL: Webhook URL = https://your-domain/api/webhooks/ghl

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const { postId, status, platform, contentId } = body;

    if (!contentId) {
      return NextResponse.json({
        skipped: true,
        reason: "no contentId in payload",
      });
    }

    // Update distribution status in Neo4j
    const resolvedStatus = status ?? "posted";
    await runCypher(
      `MATCH (c:ContentPiece {id: $contentId})-[r:DISTRIBUTED_TO]->(ch:DistributionChannel)
       WHERE r.postId = $postId
       SET r.status = $status, r.updatedAt = datetime()` +
        (resolvedStatus === "posted" ? `, r.postedAt = datetime()` : ``),
      { contentId, postId: postId ?? "", status: resolvedStatus }
    );

    return NextResponse.json({ processed: true, contentId, status });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
