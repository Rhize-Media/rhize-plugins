import { NextRequest, NextResponse } from "next/server";
import { runSERPAnalysis } from "@/lib/workflows/serp-analysis";

export const maxDuration = 300;

export async function POST(req: NextRequest) {
  try {
    const { contentId, keywords, domain, locationCode, languageCode } = await req.json();

    if (!contentId && !keywords && !domain) {
      return NextResponse.json(
        { error: "Provide 'contentId', 'keywords' with 'domain', or 'domain' alone" },
        { status: 400 }
      );
    }

    const result = await runSERPAnalysis({
      contentId,
      keywords,
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
