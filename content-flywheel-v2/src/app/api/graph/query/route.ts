import { NextRequest, NextResponse } from "next/server";
import { runCypher } from "@/lib/neo4j/queries";

/**
 * Generic Cypher proxy. Protected by GRAPH_QUERY_SECRET header so it cannot
 * be called from the browser. Intended only for server-to-server debugging
 * and admin tooling. UI pages should use dedicated endpoints under /api/board,
 * /api/content, /api/graph/stats, etc.
 */
export async function POST(req: NextRequest) {
  try {
    const expected = process.env.GRAPH_QUERY_SECRET;
    if (!expected) {
      return NextResponse.json(
        { error: "GRAPH_QUERY_SECRET not configured — proxy disabled" },
        { status: 503 }
      );
    }

    const provided = req.headers.get("x-graph-secret");
    if (provided !== expected) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

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
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
