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
      CREATE (c)-[:IN_STAGE {enteredAt: datetime()}]->(s)
      WITH c
      MERGE (a:Author {name: $author})
      ON CREATE SET a.id = randomUUID(), a.expertise = []
      CREATE (a)-[:WROTE]->(c)
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
      `MATCH (c:ContentPiece {id: $contentId})-[r:IN_STAGE]->(oldStage:PipelineStage)
       CREATE (c)-[:WAS_IN_STAGE {stage: oldStage.name, enteredAt: coalesce(r.enteredAt, datetime()), leftAt: datetime()}]->(oldStage)
       DELETE r
       WITH c
       MATCH (s:PipelineStage {name: $newStage})
       CREATE (c)-[:IN_STAGE {enteredAt: datetime()}]->(s)
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

export async function getContentDetailById(id: string) {
  const driver = getDriver();
  const session = driver.session();
  try {
    const result = await session.run(
      `MATCH (c:ContentPiece {id: $id})-[:IN_STAGE]->(s:PipelineStage)
       OPTIONAL MATCH (c)-[:TARGETS]->(k:Keyword)
       OPTIONAL MATCH (c)-[:RANKS_FOR]->(snap:SERPSnapshot)
       OPTIONAL MATCH (c)-[:HAS_BACKLINK_FROM]->(b:BacklinkSource)
       OPTIONAL MATCH (c)-[:LINKS_TO]->(linked:ContentPiece)
       OPTIONAL MATCH (c)-[:HAS_SCORE]->(seo:SEOScore)
       OPTIONAL MATCH (c)-[:HAS_WORKFLOW_RUN]->(w:WorkflowRun)
       OPTIONAL MATCH (c)-[:HAS_AI_VISIBILITY]->(av:AIVisibilitySnapshot)
       OPTIONAL MATCH (c)-[wasIn:WAS_IN_STAGE]->(wasStage:PipelineStage)
       RETURN c { .*, stage: s.name } AS content,
              collect(DISTINCT k { .* }) AS keywords,
              collect(DISTINCT snap { .* }) AS serpSnapshots,
              collect(DISTINCT b { .domain, .authorityRank, .anchorText }) AS backlinks,
              collect(DISTINCT { targetTitle: linked.title, targetSlug: linked.slug }) AS internalLinks,
              head(collect(DISTINCT seo { .* })) AS seoScore,
              collect(DISTINCT w { .id, .type, .status, .summary, .startedAt, .completedAt }) AS workflowRuns,
              collect(DISTINCT av { .llm, .mentionRate, .accuracy, .citationCount, .date, .query }) AS aiVisibility,
              collect(DISTINCT { stage: wasStage.name, enteredAt: wasIn.enteredAt, leftAt: wasIn.leftAt }) AS stageHistory`,
      { id }
    );
    if (result.records.length === 0) return null;
    const row = result.records[0];
    const content = toPlain(row.get("content")) as Record<string, unknown>;
    return {
      ...content,
      keywords: toPlain(row.get("keywords") ?? []),
      serpSnapshots: toPlain(row.get("serpSnapshots") ?? []),
      backlinks: toPlain(row.get("backlinks") ?? []),
      internalLinks: (toPlain(row.get("internalLinks") ?? []) as Array<
        Record<string, unknown>
      >).filter((l) => l.targetSlug != null),
      seoScore: toPlain(row.get("seoScore")),
      workflowRuns: toPlain(row.get("workflowRuns") ?? []),
      aiVisibility: toPlain(row.get("aiVisibility") ?? []),
      stageHistory: (toPlain(row.get("stageHistory") ?? []) as Array<
        Record<string, unknown>
      >).filter((s) => s.stage != null),
    };
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

// --- Graph statistics ---

export interface GraphStats {
  nodeCounts: Record<string, number>;
  relationshipCounts: Record<string, number>;
  stageDistribution: Array<{ stage: string; order: number; count: number }>;
  recentWorkflows: Array<{
    id: string;
    type: string;
    status: string;
    summary: string | null;
    startedAt: string;
  }>;
  topClusters: Array<{ name: string; pillarTopic: string; keywordCount: number }>;
}

export async function getGraphStats(): Promise<GraphStats> {
  const driver = getDriver();
  const session = driver.session();
  try {
    // Node counts by label — single UNION query
    const nodeLabels = [
      "ContentPiece",
      "Keyword",
      "KeywordCluster",
      "SERPSnapshot",
      "BacklinkSource",
      "Competitor",
      "SEOScore",
      "AIVisibilitySnapshot",
      "WorkflowRun",
      "SiteAudit",
      "Author",
    ];
    const nodeCounts: Record<string, number> = {};
    const nodeCountRes = await session.run(
      nodeLabels
        .map((l) => `MATCH (n:\`${l}\`) RETURN "${l}" AS label, count(n) AS count`)
        .join(" UNION ALL ")
    );
    for (const record of nodeCountRes.records) {
      nodeCounts[record.get("label") as string] =
        (toPlain(record.get("count")) as number) ?? 0;
    }

    // Relationship counts by type — single UNION query
    const relTypes = [
      "IN_STAGE",
      "TARGETS",
      "BELONGS_TO",
      "RANKS_FOR",
      "HAS_BACKLINK_FROM",
      "LINKS_TO",
      "HAS_SCORE",
      "PUBLISHED_TO",
      "DISTRIBUTED_TO",
      "HAS_WORKFLOW_RUN",
      "HAS_AI_VISIBILITY",
      "WAS_IN_STAGE",
      "FOR_KEYWORD",
      "RELATED_TO",
      "AUDITS",
      "WROTE",
      "EXPERT_IN",
    ];
    const relationshipCounts: Record<string, number> = {};
    const relCountRes = await session.run(
      relTypes
        .map((t) => `MATCH ()-[r:\`${t}\`]->() RETURN "${t}" AS type, count(r) AS count`)
        .join(" UNION ALL ")
    );
    for (const record of relCountRes.records) {
      relationshipCounts[record.get("type") as string] =
        (toPlain(record.get("count")) as number) ?? 0;
    }

    // Stage distribution
    const stageRes = await session.run(
      `MATCH (s:PipelineStage)
       OPTIONAL MATCH (c:ContentPiece)-[:IN_STAGE]->(s)
       RETURN s.name AS stage, s.order AS ord, count(c) AS count
       ORDER BY ord`
    );
    const stageDistribution = stageRes.records.map((r) => ({
      stage: r.get("stage") as string,
      order: toPlain(r.get("ord")) as number,
      count: toPlain(r.get("count")) as number,
    }));

    // Recent workflow runs
    const workflowRes = await session.run(
      `MATCH (w:WorkflowRun)
       RETURN w.id AS id, w.type AS type, w.status AS status,
              w.summary AS summary, w.startedAt AS startedAt
       ORDER BY w.startedAt DESC LIMIT 10`
    );
    const recentWorkflows = workflowRes.records.map((r) => ({
      id: r.get("id") as string,
      type: r.get("type") as string,
      status: r.get("status") as string,
      summary: r.get("summary") as string | null,
      startedAt: (toPlain(r.get("startedAt")) as string) ?? "",
    }));

    // Top keyword clusters
    const clusterRes = await session.run(
      `MATCH (cl:KeywordCluster)
       OPTIONAL MATCH (k:Keyword)-[:BELONGS_TO]->(cl)
       WITH cl, count(k) AS keywordCount
       ORDER BY keywordCount DESC LIMIT 10
       RETURN cl.name AS name, cl.pillarTopic AS pillarTopic, keywordCount`
    );
    const topClusters = clusterRes.records.map((r) => ({
      name: r.get("name") as string,
      pillarTopic: r.get("pillarTopic") as string,
      keywordCount: toPlain(r.get("keywordCount")) as number,
    }));

    return {
      nodeCounts,
      relationshipCounts,
      stageDistribution,
      recentWorkflows,
      topClusters,
    };
  } finally {
    await session.close();
  }
}

// --- Author expertise ---

export async function linkAuthorExpertise(contentId: string): Promise<void> {
  const driver = getDriver();
  const session = driver.session();
  try {
    await session.run(
      `MATCH (a:Author)-[:WROTE]->(c:ContentPiece {id: $contentId})-[:TARGETS]->(k:Keyword)-[:BELONGS_TO]->(cl:KeywordCluster)
       MERGE (a)-[:EXPERT_IN]->(cl)`,
      { contentId }
    );
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
