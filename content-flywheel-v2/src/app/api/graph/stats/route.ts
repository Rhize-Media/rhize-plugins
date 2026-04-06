import { NextResponse } from "next/server";
import { getGraphStats, getCostStats } from "@/lib/neo4j/queries";

export async function GET() {
  try {
    const [stats, costStats] = await Promise.all([
      getGraphStats(),
      getCostStats(),
    ]);
    return NextResponse.json({ ...stats, costStats });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
