import neo4j from "neo4j-driver";
import { getDriver } from "./driver";
import type { ContentPiece, PipelineStage, Keyword, SERPSnapshot } from "@/types";

/**
 * Convert Neo4j driver types (Integer, DateTime, Date, Node, Relationship, Point, Duration)
 * into plain JS values so results can safely cross the JSON boundary.
 */
export function toPlain(value: unknown): unknown {
  if (value == null) return value;
  if (neo4j.isInt(value)) {
    const i = value as { toNumber: () => number; toString: () => string };
    const n = i.toNumber();
    return Number.isSafeInteger(n) ? n : i.toString();
  }
  if (
    neo4j.isDateTime(value) ||
    neo4j.isDate(value) ||
    neo4j.isLocalDateTime(value) ||
    neo4j.isLocalTime(value) ||
    neo4j.isTime(value)
  ) {
    return (value as { toString: () => string }).toString();
  }
  if (neo4j.isDuration(value)) {
    return (value as { toString: () => string }).toString();
  }
  if (neo4j.isNode(value) || neo4j.isRelationship(value)) {
    const entity = value as { properties: Record<string, unknown> };
    return toPlain(entity.properties);
  }
  if (Array.isArray(value)) {
    return value.map(toPlain);
  }
  if (typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      out[k] = toPlain(v);
    }
    return out;
  }
  return value;
}

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
    return toPlain(result.records[0].get("content")) as ContentPiece;
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
       RETURN s.name AS stage, s.order AS ord, collect(c { .* }) AS pieces
       ORDER BY ord`
    );
    const grouped = {} as Record<PipelineStage, ContentPiece[]>;
    for (const record of result.records) {
      grouped[record.get("stage") as PipelineStage] = toPlain(
        record.get("pieces")
      ) as ContentPiece[];
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
    return toPlain(result.records[0].get("content")) as ContentPiece;
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
    return toPlain(result.records[0]?.get("keywords") ?? []) as Keyword[];
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
       WITH snap ORDER BY snap.date DESC
       RETURN collect(snap { .* }) AS snapshots`,
      { contentId, keywordId }
    );
    return toPlain(result.records[0]?.get("snapshots") ?? []) as SERPSnapshot[];
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
    return result.records.map(
      (r) => toPlain(r.toObject()) as Record<string, unknown>
    );
  } finally {
    await session.close();
  }
}
