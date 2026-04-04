import { NextRequest, NextResponse } from "next/server";
import { runCypher } from "@/lib/neo4j/queries";

export async function POST(req: NextRequest) {
  try {
    const { query, params } = await req.json();

    if (!query || typeof query !== "string") {
      return NextResponse.json(
        { error: "Missing or invalid 'query' field" },
        { status: 400 }
      );
    }

    const results = await runCypher(query, params ?? {});
    return NextResponse.json({ results });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
