import { NextRequest, NextResponse } from "next/server";
import { runCypher } from "@/lib/neo4j/queries";

// Sanity webhook receiver — fires when a document is published/unpublished.
// Configure in Sanity: Webhook URL = https://your-domain/api/webhooks/sanity

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const { _id, _type, slug, _rev } = body;

    if (_type !== "article") {
      return NextResponse.json({ skipped: true, reason: "not an article" });
    }

    const slugValue = slug?.current ?? slug;
    if (!slugValue) {
      return NextResponse.json({ skipped: true, reason: "no slug" });
    }

    // Determine if this is a publish or unpublish event
    const isPublished = !_id.startsWith("drafts.");

    if (isPublished) {
      // Update the content piece in Neo4j — move to "published" stage
      await runCypher(
        `MATCH (c:ContentPiece {slug: $slug})
         OPTIONAL MATCH (c)-[r:IN_STAGE]->()
         DELETE r
         WITH c
         MATCH (s:PipelineStage {name: "published"})
         CREATE (c)-[:IN_STAGE]->(s)
         SET c.publishedAt = datetime(), c.updatedAt = datetime(), c.sanityId = $sanityId, c.sanityRev = $rev`,
        { slug: slugValue, sanityId: _id, rev: _rev }
      );

      // Record PUBLISHED_TO relationship
      await runCypher(
        `MATCH (c:ContentPiece {slug: $slug})
         MERGE (t:CMSTarget {type: "sanity"})
         ON CREATE SET t.id = randomUUID()
         MERGE (c)-[r:PUBLISHED_TO]->(t)
         SET r.publishedAt = datetime()`,
        { slug: slugValue }
      );
    } else {
      // Unpublish — mark the PUBLISHED_TO relationship with unpublishedAt
      await runCypher(
        `MATCH (c:ContentPiece {slug: $slug})-[r:PUBLISHED_TO]->(t:CMSTarget {type: "sanity"})
         SET r.unpublishedAt = datetime()`,
        { slug: slugValue }
      );
    }

    return NextResponse.json({ processed: true, slug: slugValue, isPublished });
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
