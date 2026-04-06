import { NextRequest, NextResponse } from "next/server";
import { ghlAdapter } from "@/lib/adapters/distribution/ghl";
import { getContentById } from "@/lib/neo4j/queries";

export async function POST(req: NextRequest) {
  try {
    const { contentId, platform, text, mediaUrls, scheduledAt } =
      await req.json();

    if (!contentId || !platform || !text) {
      return NextResponse.json(
        { error: "Missing contentId, platform, or text" },
        { status: 400 }
      );
    }

    const content = await getContentById(contentId);
    if (!content) {
      return NextResponse.json(
        { error: "Content not found" },
        { status: 404 }
      );
    }

    const result = await ghlAdapter.schedulePost(
      { contentId, platform, text, mediaUrls },
      scheduledAt ? new Date(scheduledAt) : new Date()
    );

    // Graph write handled by ghlAdapter.schedulePost()

    return NextResponse.json({ result });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
