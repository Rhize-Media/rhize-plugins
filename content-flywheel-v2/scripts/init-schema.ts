import { readFileSync } from "node:fs";
import { join } from "node:path";
import neo4j from "neo4j-driver";

async function initSchema() {
  const uri = process.env.NEO4J_URI;
  const user = process.env.NEO4J_USERNAME;
  const password = process.env.NEO4J_PASSWORD;
  const database = process.env.NEO4J_DATABASE ?? "neo4j";

  if (!uri || !user || !password) {
    throw new Error("Missing NEO4J_URI, NEO4J_USERNAME, or NEO4J_PASSWORD");
  }

  const driver = neo4j.driver(uri, neo4j.auth.basic(user, password));

  try {
    await driver.verifyConnectivity();
    console.log(`✓ Connected to ${uri}`);
  } catch (err) {
    console.error("✗ Failed to connect:", err);
    await driver.close();
    process.exit(1);
  }

  const schemaPath = join(process.cwd(), "cypher", "schema.cypher");
  const schemaContent = readFileSync(schemaPath, "utf-8");

  // Split on semicolons, filter out empty statements and pure comment blocks
  const statements = schemaContent
    .split(";")
    .map((s) => s.trim())
    .filter((s) => {
      if (!s) return false;
      // Remove comment-only lines
      const nonComment = s
        .split("\n")
        .filter((line) => !line.trim().startsWith("//"))
        .join("\n")
        .trim();
      return nonComment.length > 0;
    });

  console.log(`Executing ${statements.length} statements...`);

  const session = driver.session({ database });
  let success = 0;
  let failed = 0;
  try {
    for (const stmt of statements) {
      try {
        await session.run(stmt);
        const firstLine = stmt.split("\n").find((l) => l.trim() && !l.trim().startsWith("//")) ?? stmt;
        console.log(`  ✓ ${firstLine.trim().slice(0, 80)}`);
        success++;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        console.error(`  ✗ FAILED: ${stmt.slice(0, 80)}\n    ${msg}`);
        failed++;
      }
    }
  } finally {
    await session.close();
  }

  console.log(`\nResult: ${success} succeeded, ${failed} failed`);

  // Verify
  const verifySession = driver.session({ database });
  try {
    const stages = await verifySession.run(
      "MATCH (s:PipelineStage) RETURN s.name AS name, s.order AS ord ORDER BY s.order"
    );
    console.log(`\nPipeline stages (${stages.records.length}):`);
    for (const r of stages.records) {
      console.log(`  ${r.get("ord")}. ${r.get("name")}`);
    }

    const constraints = await verifySession.run("SHOW CONSTRAINTS");
    console.log(`\nConstraints: ${constraints.records.length}`);
  } finally {
    await verifySession.close();
  }

  await driver.close();
  if (failed > 0) process.exit(1);
}

initSchema().catch((err) => {
  console.error(err);
  process.exit(1);
});
