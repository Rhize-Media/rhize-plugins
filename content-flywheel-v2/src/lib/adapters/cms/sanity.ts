import { createClient } from "@sanity/client";
import type { CMSAdapter, CMSDocument, ContentPiece } from "@/types";
import { runCypher } from "@/lib/neo4j/queries";

function getSanityClient() {
  const projectId = process.env.SANITY_PROJECT_ID;
  const dataset = process.env.SANITY_DATASET ?? "production";
  const token = process.env.SANITY_API_TOKEN;

  if (!projectId || !token) {
    throw new Error(
      "Missing Sanity credentials. Set SANITY_PROJECT_ID and SANITY_API_TOKEN."
    );
  }

  return createClient({
    projectId,
    dataset,
    token,
    apiVersion: "2024-01-01",
    useCdn: false,
  });
}

export const sanityAdapter: CMSAdapter = {
  async createDraft(content: ContentPiece): Promise<CMSDocument> {
    const client = getSanityClient();
    const doc = await client.create({
      _type: "article",
      title: content.title,
      slug: { _type: "slug", current: content.slug },
      author: content.author,
      seo: {
        metaTitle: content.title,
      },
    });
    return { id: doc._id, status: "draft" };
  },

  async updateDraft(
    id: string,
    content: Partial<ContentPiece>
  ): Promise<CMSDocument> {
    const client = getSanityClient();
    const patch = client.patch(id);
    if (content.title) patch.set({ title: content.title });
    if (content.slug) patch.set({ "slug.current": content.slug });
    await patch.commit();
    return { id, status: "draft" };
  },

  async publish(id: string): Promise<{ url: string }> {
    const client = getSanityClient();
    // Sanity uses draft. prefix — publishing means removing it
    const draftId = id.startsWith("drafts.") ? id : `drafts.${id}`;
    const publishedId = id.replace(/^drafts\./, "");

    const draft = await client.getDocument(draftId);
    if (draft) {
      await client.createOrReplace({ ...draft, _id: publishedId });
      await client.delete(draftId);
    }

    const slug = draft?.slug?.current ?? publishedId;

    // Record in graph
    const projectId = process.env.SANITY_PROJECT_ID;
    const dataset = process.env.SANITY_DATASET ?? "production";
    await runCypher(
      `MATCH (c:ContentPiece {slug: $slug})
       MERGE (t:CMSTarget {type: "sanity", projectId: $projectId})
       ON CREATE SET t.id = randomUUID(), t.dataset = $dataset
       MERGE (c)-[r:PUBLISHED_TO]->(t)
       SET r.publishedAt = datetime(), r.documentId = $documentId`,
      { slug, projectId: projectId ?? "", dataset, documentId: publishedId }
    );

    return { url: `/blog/${slug}` };
  },

  async unpublish(id: string): Promise<void> {
    const client = getSanityClient();
    const publishedId = id.replace(/^drafts\./, "");
    const doc = await client.getDocument(publishedId);
    if (doc) {
      await client.createOrReplace({ ...doc, _id: `drafts.${publishedId}` });
      await client.delete(publishedId);
    }
  },

  async getStatus(id: string): Promise<"draft" | "published" | "scheduled"> {
    const client = getSanityClient();
    const publishedId = id.replace(/^drafts\./, "");
    const published = await client.getDocument(publishedId);
    if (published) return "published";
    const draft = await client.getDocument(`drafts.${publishedId}`);
    if (draft) return "draft";
    return "draft";
  },
};
