import { NextRequest, NextResponse } from "next/server";
import { runBacklinkAnalysis } from "@/lib/workflows/backlink-analysis";

export async function POST(req: NextRequest) {
  try {
    const { contentId, domain, locationCode, languageCode } = await req.json();

    if (!domain) {
      return NextResponse.json(
        { error: "Missing required field: 'domain'" },
        { status: 400 }
      );
    }

    const result = await runBacklinkAnalysis({
      contentId,
      domain,
      locationCode,
      languageCode,
    });

    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
