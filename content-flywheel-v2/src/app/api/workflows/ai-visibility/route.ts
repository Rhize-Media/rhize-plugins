import { NextRequest, NextResponse } from "next/server";
import { runAIVisibility } from "@/lib/workflows/ai-visibility";

export async function POST(req: NextRequest) {
  try {
    const { contentId, brand, queries, locationCode, languageCode } = await req.json();

    if (!brand) {
      return NextResponse.json(
        { error: "Missing required field: 'brand'" },
        { status: 400 }
      );
    }

    const result = await runAIVisibility({
      contentId,
      brand,
      queries,
      locationCode,
      languageCode,
    });

    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
