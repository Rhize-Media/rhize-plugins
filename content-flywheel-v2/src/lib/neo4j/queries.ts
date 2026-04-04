import { getDriver } from "./driver";
import type { ContentPiece, PipelineStage, Keyword, SERPSnapshot } from "@/types";

// --- Content CRUD ---

export async function createContent(
  content: Omit<ContentPiece, "id" | "createdAt" | "updatedAt">
): Promise<ContentPiece> {
  const driver = getDriver();
  const session = driver.session();
  try {
    const result = await session.run(
      `CREATE (c:ContentPiece {
        id: randomUUID(),
        title: $title,
        slug: $slug,
        author: $author,
        url: $url,
        createdAt: datetime(),
        updatedAt: datetime()
      })
      WITH c
      MATCH (s:PipelineStage {name: $stage})
      CREATE (c)-[:IN_STAGE]->(s)
      RETURN c { .* } AS content`,
      content
    );
    return result.records[0].get("content") as ContentPiece;
  } finally {
    await session.close();
  }
}

export async function moveContentToStage(
  contentId: string,
  newStage: PipelineStage
): Promise<void> {
  const driver = getDriver();
  const session = driver.session();
  try {
    await session.run(
      `MATCH (c:ContentPiece {id: $contentId})-[r:IN_STAGE]->()
       DELETE r
       WITH c
       MATCH (s:PipelineStage {name: $newStage})
       CREATE (c)-[:IN_STAGE]->(s)
       SET c.updatedAt = datetime()`,
      { contentId, newStage }
    );
  } finally {
    await session.close();
  }
}

export async function getContentByStage(): Promise<
  Record<PipelineStage, ContentPiece[]>
> {
  const driver = getDriver();
  const session = driver.session();
  try {
    const result = await session.run(
      `MATCH (c:ContentPiece)-[:IN_STAGE]->(s:PipelineStage)
       RETURN s.name AS stage, collect(c { .* }) AS pieces
       ORDER BY s.order`
    );
    const grouped = {} as Record<PipelineStage, ContentPiece[]>;
    for (const record of result.records) {
      grouped[record.get("stage") as PipelineStage] = record.get("pieces");
    }
    return grouped;
  } finally {
    await session.close();
  }
}

export async function getContentById(id: string): Promise<ContentPiece | null> {
  const driver = getDriver();
  const session = driver.session();
  try {
    const result = await session.run(
      `MATCH (c:ContentPiece {id: $id})-[:IN_STAGE]->(s:PipelineStage)
       RETURN c { .*, stage: s.name } AS content`,
      { id }
    );
    if (result.records.length === 0) return null;
    return result.records[0].get("content") as ContentPiece;
  } finally {
    await session.close();
  }
}

// --- Keywords ---

export async function getKeywordsForContent(
  contentId: string
): Promise<Keyword[]> {
  const driver = getDriver();
  const session = driver.session();
  try {
    const result = await session.run(
      `MATCH (c:ContentPiece {id: $contentId})-[:TARGETS]->(k:Keyword)
       RETURN collect(k { .* }) AS keywords`,
      { contentId }
    );
    return result.records[0]?.get("keywords") ?? [];
  } finally {
    await session.close();
  }
}

export async function linkKeywordToContent(
  contentId: string,
  keywordId: string
): Promise<void> {
  const driver = getDriver();
  const session = driver.session();
  try {
    await session.run(
      `MATCH (c:ContentPiece {id: $contentId}), (k:Keyword {id: $keywordId})
       MERGE (c)-[:TARGETS]->(k)`,
      { contentId, keywordId }
    );
  } finally {
    await session.close();
  }
}

// --- SERP Snapshots ---

export async function getSERPHistory(
  contentId: string,
  keywordId: string
): Promise<SERPSnapshot[]> {
  const driver = getDriver();
  const session = driver.session();
  try {
    const result = await session.run(
      `MATCH (c:ContentPiece {id: $contentId})-[:RANKS_FOR]->(snap:SERPSnapshot)
       WHERE snap.keywordId = $keywordId
       RETURN collect(snap { .* }) AS snapshots
       ORDER BY snap.date DESC`,
      { contentId, keywordId }
    );
    return result.records[0]?.get("snapshots") ?? [];
  } finally {
    await session.close();
  }
}

// --- Generic Cypher ---

export async function runCypher(
  query: string,
  params: Record<string, unknown> = {}
): Promise<Record<string, unknown>[]> {
  const driver = getDriver();
  const session = driver.session();
  try {
    const result = await session.run(query, params);
    return result.records.map((r) => r.toObject());
  } finally {
    await session.close();
  }
}
