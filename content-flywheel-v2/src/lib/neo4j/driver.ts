import neo4j, { type Driver } from "neo4j-driver";

let driver: Driver | null = null;

export function getDriver(): Driver {
  if (driver) return driver;

  const uri = process.env.NEO4J_URI;
  const user = process.env.NEO4J_USERNAME;
  const password = process.env.NEO4J_PASSWORD;

  if (!uri || !user || !password) {
    throw new Error(
      "Missing Neo4j credentials. Set NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD."
    );
  }

  driver = neo4j.driver(uri, neo4j.auth.basic(user, password));
  return driver;
}

export async function closeDriver(): Promise<void> {
  if (driver) {
    await driver.close();
    driver = null;
  }
}
