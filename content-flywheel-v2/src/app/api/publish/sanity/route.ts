import { NextRequest, NextResponse } from "next/server";
import { sanityAdapter } from "@/lib/adapters/cms/sanity";
import { getContentById, runCypher } from "@/lib/neo4j/queries";

export async function POST(req: NextRequest) {
  try {
    const { contentId, action } = await req.json();

    if (!contentId) {
      return NextResponse.json(
        { error: "Missing contentId" },
        { status: 400 }
      );
    }

    const content = await getContentById(contentId);
    if (!content) {
      return NextResponse.json(
        { error: "Content not found" },
        { status: 404 }
      );
    }

    switch (action) {
      case "create-draft": {
        const doc = await sanityAdapter.createDraft(content);
        return NextResponse.json({ doc });
      }
      case "publish": {
        const { sanityId } = await req.json().catch(() => ({}));
        if (!sanityId) {
          return NextResponse.json(
            { error: "Missing sanityId for publish" },
            { status: 400 }
          );
        }
        const result = await sanityAdapter.publish(sanityId);

        // Record PUBLISHED_TO relationship using contentId
        await runCypher(
          `MATCH (c:ContentPiece {id: $contentId})
           MERGE (t:CMSTarget {type: "sanity", projectId: $projectId})
           ON CREATE SET t.id = randomUUID(), t.dataset = $dataset
           MERGE (c)-[r:PUBLISHED_TO]->(t)
           SET r.publishedAt = datetime(), r.documentId = $documentId`,
          {
            contentId,
            projectId: process.env.SANITY_PROJECT_ID ?? "",
            dataset: process.env.SANITY_DATASET ?? "production",
            documentId: sanityId.replace(/^drafts\./, ""),
          }
        );

        return NextResponse.json({ result });
      }
      default:
        return NextResponse.json(
          { error: `Unknown action: ${action}` },
          { status: 400 }
        );
    }
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unknown error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
