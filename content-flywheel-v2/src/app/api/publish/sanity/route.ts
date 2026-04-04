import { NextRequest, NextResponse } from "next/server";
import { sanityAdapter } from "@/lib/adapters/cms/sanity";
import { getContentById } from "@/lib/neo4j/queries";

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
