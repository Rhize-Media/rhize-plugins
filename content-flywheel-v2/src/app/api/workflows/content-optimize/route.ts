import { NextRequest, NextResponse } from "next/server";
import { runContentOptimize } from "@/lib/workflows/content-optimize";

export async function POST(req: NextRequest) {
  try {
    const { contentId, url, primaryKeyword, locationCode, languageCode } = await req.json();

    if (!contentId || !url) {
      return NextResponse.json(
        { error: "Missing required fields: 'contentId' and 'url'" },
        { status: 400 }
      );
    }

    const result = await runContentOptimize({
      contentId,
      url,
      primaryKeyword,
      locationCode,
      languageCode,
    });

    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
