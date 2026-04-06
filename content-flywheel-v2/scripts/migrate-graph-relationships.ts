/**
 * One-time migration script to backfill graph relationships for existing data.
 *
 * Run with: npx tsx scripts/migrate-graph-relationships.ts
 *
 * This script:
 * 1. Links orphaned WorkflowRuns to their ContentPiece via HAS_WORKFLOW_RUN
 * 2. Links orphaned AIVisibilitySnapshots via HAS_AI_VISIBILITY
 * 3. Adds enteredAt to existing IN_STAGE relationships
 * 4. Creates Author nodes from existing ContentPiece.author strings
 * 5. Reports migration stats
 */

import neo4j from "neo4j-driver";

async function migrate() {
  const uri = process.env.NEO4J_URI;
  const user = process.env.NEO4J_USERNAME;
  const password = process.env.NEO4J_PASSWORD;

  if (!uri || !user || !password) {
    console.error("Missing NEO4J_URI, NEO4J_USERNAME, or NEO4J_PASSWORD in .env.local");
    process.exit(1);
  }

  const driver = neo4j.driver(uri, neo4j.auth.basic(user, password));
  const session = driver.session({ database: process.env.NEO4J_DATABASE ?? "neo4j" });

  try {
    console.log("Starting graph relationship migration...\n");

    // 1. Link orphaned WorkflowRuns
    const wfResult = await session.run(
      `MATCH (w:WorkflowRun)
       WHERE w.contentId IS NOT NULL AND NOT ()-[:HAS_WORKFLOW_RUN]->(w)
       MATCH (c:ContentPiece {id: w.contentId})
       CREATE (c)-[:HAS_WORKFLOW_RUN]->(w)
       RETURN count(w) AS linked`
    );
    const wfLinked = wfResult.records[0]?.get("linked")?.toNumber?.() ?? 0;
    console.log(`[1/5] WorkflowRun relationships: ${wfLinked} linked`);

    // 2. Link orphaned AIVisibilitySnapshots
    const avResult = await session.run(
      `MATCH (a:AIVisibilitySnapshot)
       WHERE a.contentId IS NOT NULL AND NOT ()-[:HAS_AI_VISIBILITY]->(a)
       MATCH (c:ContentPiece {id: a.contentId})
       CREATE (c)-[:HAS_AI_VISIBILITY]->(a)
       RETURN count(a) AS linked`
    );
    const avLinked = avResult.records[0]?.get("linked")?.toNumber?.() ?? 0;
    console.log(`[2/5] AIVisibilitySnapshot relationships: ${avLinked} linked`);

    // 3. Add enteredAt to existing IN_STAGE relationships
    const stageResult = await session.run(
      `MATCH ()-[r:IN_STAGE]->()
       WHERE r.enteredAt IS NULL
       SET r.enteredAt = datetime()
       RETURN count(r) AS updated`
    );
    const stageUpdated = stageResult.records[0]?.get("updated")?.toNumber?.() ?? 0;
    console.log(`[3/5] IN_STAGE enteredAt backfilled: ${stageUpdated} updated`);

    // 4. Create Author nodes from ContentPiece.author strings
    const authorResult = await session.run(
      `MATCH (c:ContentPiece)
       WHERE c.author IS NOT NULL AND NOT (:Author)-[:WROTE]->(c)
       MERGE (a:Author {name: c.author})
       ON CREATE SET a.id = randomUUID(), a.expertise = []
       CREATE (a)-[:WROTE]->(c)
       RETURN count(DISTINCT a) AS authors, count(c) AS linked`
    );
    const authorsCreated = authorResult.records[0]?.get("authors")?.toNumber?.() ?? 0;
    const contentLinked = authorResult.records[0]?.get("linked")?.toNumber?.() ?? 0;
    console.log(`[4/5] Authors created: ${authorsCreated}, content linked: ${contentLinked}`);

    // 5. Link SERPSnapshots to Keywords via FOR_KEYWORD
    const serpResult = await session.run(
      `MATCH (snap:SERPSnapshot)
       WHERE snap.keywordId IS NOT NULL AND NOT (snap)-[:FOR_KEYWORD]->()
       MATCH (k:Keyword {id: snap.keywordId})
       CREATE (snap)-[:FOR_KEYWORD]->(k)
       RETURN count(snap) AS linked`
    );
    const serpLinked = serpResult.records[0]?.get("linked")?.toNumber?.() ?? 0;
    console.log(`[5/5] SERPSnapshot->Keyword relationships: ${serpLinked} linked`);

    console.log("\nMigration complete.");
  } catch (error) {
    console.error("Migration failed:", error);
    process.exit(1);
  } finally {
    await session.close();
    await driver.close();
  }
}

migrate();
