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
    await runCypher(
      `MATCH (c:ContentPiece {id: $contentId})-[r:DISTRIBUTED_TO]->(ch:DistributionChannel {platform: $platform})
       SET r.status = $status, r.postId = $postId, r.updatedAt = datetime()`,
      { contentId, platform: platform ?? "unknown", status: status ?? "posted", postId: postId ?? "" }
    );

    return NextResponse.json({ processed: true, contentId, status });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
