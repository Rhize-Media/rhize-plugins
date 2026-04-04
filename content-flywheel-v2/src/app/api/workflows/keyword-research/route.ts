import { NextRequest, NextResponse } from "next/server";
import { runKeywordResearch } from "@/lib/workflows/keyword-research";

export async function POST(req: NextRequest) {
  try {
    const { seeds, domain, contentId, locationCode, languageCode } = await req.json();

    if (!seeds || !Array.isArray(seeds) || seeds.length === 0) {
      return NextResponse.json(
        { error: "Missing or empty 'seeds' array" },
        { status: 400 }
      );
    }

    const result = await runKeywordResearch({
      seeds,
      domain,
      contentId,
      locationCode,
      languageCode,
    });

    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
