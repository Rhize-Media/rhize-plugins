import neo4j from "neo4j-driver";

const SAMPLES = [
  {
    title: "The Ultimate Guide to Content Flywheels",
    slug: "ultimate-guide-content-flywheels",
    author: "Jim Deola",
    url: "https://rhize.media/guides/content-flywheels",
    stage: "inspiration",
  },
  {
    title: "How Neo4j Powers Our Content Graph",
    slug: "neo4j-content-graph",
    author: "Jim Deola",
    url: null,
    stage: "research",
  },
  {
    title: "AEO vs SEO: What's Changing in 2026",
    slug: "aeo-vs-seo-2026",
    author: "Jim Deola",
    url: null,
    stage: "draft",
  },
  {
    title: "DataForSEO API: Complete Integration Guide",
    slug: "dataforseo-integration-guide",
    author: "Jim Deola",
    url: "https://rhize.media/guides/dataforseo",
    stage: "optimize",
  },
  {
    title: "The State of AI Search Optimization",
    slug: "state-of-ai-search",
    author: "Jim Deola",
    url: "https://rhize.media/blog/ai-search",
    stage: "published",
  },
];

async function seed() {
  const uri = process.env.NEO4J_URI;
  const user = process.env.NEO4J_USERNAME;
  const password = process.env.NEO4J_PASSWORD;
  const database = process.env.NEO4J_DATABASE ?? "neo4j";

  if (!uri || !user || !password) {
    throw new Error("Missing NEO4J_URI, NEO4J_USERNAME, or NEO4J_PASSWORD");
  }

  const driver = neo4j.driver(uri, neo4j.auth.basic(user, password));
  const session = driver.session({ database });

  try {
    for (const sample of SAMPLES) {
      const result = await session.run(
        `MERGE (c:ContentPiece {slug: $slug})
         ON CREATE SET c.id = randomUUID(),
           c.title = $title,
           c.author = $author,
           c.url = $url,
           c.createdAt = datetime(),
           c.updatedAt = datetime()
         ON MATCH SET c.title = $title, c.author = $author, c.url = $url, c.updatedAt = datetime()
         WITH c
         OPTIONAL MATCH (c)-[r:IN_STAGE]->()
         DELETE r
         WITH c
         MATCH (s:PipelineStage {name: $stage})
         CREATE (c)-[:IN_STAGE]->(s)
         RETURN c.id AS id, c.title AS title`,
        sample
      );
      const row = result.records[0];
      console.log(`  ✓ ${sample.stage.padEnd(12)} ${row.get("title")} (${row.get("id")})`);
    }

    // Summary
    const summary = await session.run(
      `MATCH (c:ContentPiece)-[:IN_STAGE]->(s:PipelineStage)
       RETURN s.name AS stage, s.order AS ord, count(c) AS count
       ORDER BY ord`
    );
    console.log("\nPipeline:");
    for (const r of summary.records) {
      console.log(`  ${r.get("stage").padEnd(12)} ${r.get("count").toString()}`);
    }
  } finally {
    await session.close();
    await driver.close();
  }
}

seed().catch((err) => {
  console.error(err);
  process.exit(1);
});
