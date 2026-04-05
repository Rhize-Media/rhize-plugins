import { NextResponse } from "next/server";
import { getContentByStage } from "@/lib/neo4j/queries";

export async function GET() {
  try {
    const board = await getContentByStage();
    return NextResponse.json({ board });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
