import { NextRequest, NextResponse } from "next/server";
import { moveContentToStage } from "@/lib/neo4j/queries";
import type { PipelineStage } from "@/types";

const VALID_STAGES: PipelineStage[] = [
  "inspiration",
  "research",
  "draft",
  "optimize",
  "review",
  "published",
  "monitor",
  "refresh",
];

export async function POST(req: NextRequest) {
  try {
    const { contentId, newStage } = await req.json();

    if (!contentId || typeof contentId !== "string") {
      return NextResponse.json(
        { error: "Missing or invalid 'contentId'" },
        { status: 400 }
      );
    }

    if (!newStage || !VALID_STAGES.includes(newStage)) {
      return NextResponse.json(
        { error: `Invalid 'newStage'. Must be one of: ${VALID_STAGES.join(", ")}` },
        { status: 400 }
      );
    }

    await moveContentToStage(contentId, newStage as PipelineStage);
    return NextResponse.json({ success: true });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
