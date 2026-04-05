import { NextResponse } from "next/server";
import { getGraphStats } from "@/lib/neo4j/queries";

export async function GET() {
  try {
    const stats = await getGraphStats();
    return NextResponse.json(stats);
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
