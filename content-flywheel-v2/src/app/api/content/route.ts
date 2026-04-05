import { NextRequest, NextResponse } from "next/server";
import { createContent } from "@/lib/neo4j/queries";
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
    const body = await req.json();
    const { title, slug, author, url, stage } = body;

    if (!title || typeof title !== "string") {
      return NextResponse.json(
        { error: "Missing or invalid 'title'" },
        { status: 400 }
      );
    }
    if (!slug || typeof slug !== "string") {
      return NextResponse.json(
        { error: "Missing or invalid 'slug'" },
        { status: 400 }
      );
    }
    if (!author || typeof author !== "string") {
      return NextResponse.json(
        { error: "Missing or invalid 'author'" },
        { status: 400 }
      );
    }

    const resolvedStage: PipelineStage = VALID_STAGES.includes(stage)
      ? stage
      : "inspiration";

    const content = await createContent({
      title,
      slug,
      author,
      url: url ?? null,
      stage: resolvedStage,
    } as Parameters<typeof createContent>[0]);

    return NextResponse.json(content, { status: 201 });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
