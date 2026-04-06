import { NextRequest, NextResponse } from "next/server";
import { runBrandVoiceCheck } from "@/lib/workflows/brand-voice-check";

export const maxDuration = 300;

export async function POST(req: NextRequest) {
  try {
    const { contentId } = await req.json();

    if (!contentId || typeof contentId !== "string") {
      return NextResponse.json(
        { error: "Missing or invalid 'contentId' string" },
        { status: 400 }
      );
    }

    const result = await runBrandVoiceCheck({ contentId });

    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
