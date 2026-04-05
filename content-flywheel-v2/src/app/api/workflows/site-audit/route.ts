import { NextRequest, NextResponse } from "next/server";
import { runSiteAudit } from "@/lib/workflows/site-audit";

export const maxDuration = 300;

export async function POST(req: NextRequest) {
  try {
    const { domain, maxPages, locationCode, languageCode } = await req.json();

    if (!domain) {
      return NextResponse.json(
        { error: "Missing required field: 'domain'" },
        { status: 400 }
      );
    }

    const result = await runSiteAudit({
      domain,
      maxPages,
      locationCode,
      languageCode,
    });

    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
