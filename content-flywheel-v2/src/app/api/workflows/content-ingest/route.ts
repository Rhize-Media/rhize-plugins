import { NextRequest, NextResponse } from "next/server";
import { runContentIngest } from "@/lib/workflows/content-ingest";

export const maxDuration = 300;

export async function POST(req: NextRequest) {
  try {
    const { url, contentId } = await req.json();

    if (!url || typeof url !== "string") {
      return NextResponse.json(
        { error: "Missing or invalid 'url' string" },
        { status: 400 }
      );
    }

    const result = await runContentIngest({ url, contentId });

    return NextResponse.json(result);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
