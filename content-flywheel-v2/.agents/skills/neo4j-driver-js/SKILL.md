---
name: neo4j-driver-js
description: Neo4j JavaScript driver 6.x — connection setup, session management, impersonation security, transaction functions, type handling, and result-to-UI data mapping.
---

# Neo4j JavaScript Driver

## When to Use

Use this skill when working with the `neo4j-driver` package in JavaScript/TypeScript. Covers driver initialization, session management, the impersonation security model, transaction functions with retries, Neo4j type handling (Integer, DateTime, Node, Relationship), and mapping driver results to UI-consumable shapes.

---

## 1. Installation

```bash
npm install neo4j-driver
```

---

## 2. Driver Initialization

Create a single driver instance for the application lifetime. The driver manages a connection pool internally.

```typescript
import neo4j, { Driver } from "neo4j-driver";

let driver: Driver | null = null;

export const initDriver = (
  uri: string,
  user: string,
  password: string,
): Driver => {
  driver = neo4j.driver(uri, neo4j.auth.basic(user, password), {
    maxConnectionPoolSize: 50,
    connectionAcquisitionTimeout: 60000, // 60s
    maxTransactionRetryTime: 30000, // 30s
  });
  return driver;
};

export const getDriver = (): Driver => {
  if (!driver)
    throw new Error("Driver not initialized. Call initDriver() first.");
  return driver;
};

export const closeDriver = async (): Promise<void> => {
  if (driver) {
    await driver.close();
    driver = null;
  }
};
```

### Environment Configuration

```typescript
export const NEO4J_CONFIG = {
  uri: import.meta.env.VITE_NEO4J_URI || "neo4j://localhost:7687",
  user: import.meta.env.VITE_NEO4J_USER || "neo4j",
  password: import.meta.env.VITE_NEO4J_PASSWORD || "password",
  database: import.meta.env.VITE_NEO4J_DATABASE || "neo4j",
};
```

### Verify Connectivity

```typescript
const driver = initDriver(config.uri, config.user, config.password);
await driver.verifyConnectivity();
console.log("Connected to Neo4j");
```

---

## 3. Session Management

Sessions are lightweight and should be created per unit of work, then closed.

```typescript
import { Session } from "neo4j-driver";

export const getSession = (mode: "READ" | "WRITE" = "READ"): Session => {
  return getDriver().session({
    database: NEO4J_CONFIG.database,
    defaultAccessMode:
      mode === "READ" ? neo4j.session.READ : neo4j.session.WRITE,
  });
};
```

### Session Helper (Auto-Close)

```typescript
export const withSession = async <T>(
  fn: (session: Session) => Promise<T>,
  mode: "READ" | "WRITE" = "READ",
): Promise<T> => {
  const session = getSession(mode);
  try {
    return await fn(session);
  } finally {
    await session.close();
  }
};
```

---

## 4. Impersonation (Two-Tier Security)

The application connects as a service account and impersonates the actual user. Neo4j RBAC enforces data-level permissions for the impersonated user.

```typescript
export const getImpersonatedSession = (userEmail: string): Session => {
  return getDriver().session({
    database: NEO4J_CONFIG.database,
    impersonatedUser: userEmail, // Executes as this user's Neo4j RBAC role
  });
};

export const withImpersonation = async <T>(
  userEmail: string,
  fn: (session: Session) => Promise<T>,
): Promise<T> => {
  const session = getImpersonatedSession(userEmail);
  try {
    return await fn(session);
  } finally {
    await session.close();
  }
};
```

### Usage

```typescript
// User only sees data their Neo4j role permits
const transactions = await withImpersonation(
  "john.smith@company.com",
  async (session) => {
    const result = await session.run(
      `MATCH (t:Transaction)
       WHERE t.timestamp >= $startDate
       RETURN t ORDER BY t.timestamp DESC LIMIT 100`,
      { startDate },
    );
    return result.records.map((r) => r.get("t").properties);
  },
);
```

### Prerequisites

- Neo4j Enterprise Edition 5.x
- Service account with `GRANT IMPERSONATE` privilege
- Users created in Neo4j mapped to IdP identities

---

## 5. Transaction Functions

Prefer `executeRead` / `executeWrite` over raw `session.run()`. They provide automatic retries for transient errors (network blips, leader changes).

```typescript
// Read transaction with automatic retries
const persons = await withSession(async (session) => {
  return session.executeRead(async (tx) => {
    const result = await tx.run(
      `MATCH (p:Person {id: $personId})-[:OWNS]->(a:Account)
       RETURN p, collect(a) AS accounts`,
      { personId },
    );
    return result.records.map((record) => ({
      person: record.get("p").properties,
      accounts: record.get("accounts").map((a: any) => a.properties),
    }));
  });
});

// Write transaction with automatic retries
await withSession(async (session) => {
  return session.executeWrite(async (tx) => {
    await tx.run(`CREATE (p:Person $props)`, {
      props: { id: crypto.randomUUID(), name: "Jane Doe" },
    });
  });
}, "WRITE");
```

---

## 6. Neo4j Type Handling

The driver returns Neo4j-specific types that must be converted before use in UI code.

### Integer

Neo4j integers are 64-bit. The driver wraps them in `neo4j.Integer` objects.

```typescript
import neo4j from "neo4j-driver";

// Check if a value is a Neo4j Integer
if (neo4j.isInt(value)) {
  const jsNumber = value.toNumber(); // Safe for values < Number.MAX_SAFE_INTEGER
  const jsString = value.toString(); // Safe for any value
  const jsBigInt = value.toBigInt(); // Native BigInt
}
```

### DateTime

```typescript
if (neo4j.isDateTime(value)) {
  const isoString = value.toString(); // ISO 8601 string
  const jsDate = value.toStandardDate(); // JavaScript Date object
}

if (neo4j.isDate(value)) {
  const isoString = value.toString(); // YYYY-MM-DD
}

if (neo4j.isDuration(value)) {
  const str = value.toString(); // ISO 8601 duration
}
```

### Node, Relationship, Path

```typescript
// Node
record.get("n").identity; // neo4j.Integer (internal ID)
record.get("n").elementId; // string (stable element ID — use this)
record.get("n").labels; // string[]
record.get("n").properties; // Record<string, any>

// Relationship
record.get("r").identity; // neo4j.Integer
record.get("r").elementId; // string
record.get("r").type; // string (relationship type)
record.get("r").startNodeElementId; // string
record.get("r").endNodeElementId; // string
record.get("r").properties; // Record<string, any>

// Path
record.get("path").start; // Node
record.get("path").end; // Node
record.get("path").segments; // Array<{ start, relationship, end }>
record.get("path").length; // number
```

---

## 7. Result-to-UI Data Mapping

Convert Neo4j driver results into shapes that Zustand stores and NVL components expect.

### Property Mapping (Handle Neo4j Types)

```typescript
function mapProperties(
  props: Record<string, unknown>,
): Record<string, unknown> {
  const mapped: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(props)) {
    if (neo4j.isInt(value)) {
      mapped[key] = value.toNumber();
    } else if (neo4j.isDateTime(value) || neo4j.isDate(value)) {
      mapped[key] = value.toString();
    } else if (neo4j.isDuration(value)) {
      mapped[key] = value.toString();
    } else {
      mapped[key] = value;
    }
  }
  return mapped;
}
```

### Neo4j Node → Application GraphNode

```typescript
interface GraphNode {
  id: string;
  labels: string[];
  properties: Record<string, unknown>;
}

function toGraphNode(neo4jNode: any): GraphNode {
  return {
    id: neo4jNode.elementId,
    labels: neo4jNode.labels,
    properties: mapProperties(neo4jNode.properties),
  };
}
```

### Neo4j Relationship → Application GraphRelationship

```typescript
interface GraphRelationship {
  id: string;
  type: string;
  source: string;
  target: string;
  properties: Record<string, unknown>;
}

function toGraphRelationship(neo4jRel: any): GraphRelationship {
  return {
    id: neo4jRel.elementId,
    type: neo4jRel.type,
    source: neo4jRel.startNodeElementId,
    target: neo4jRel.endNodeElementId,
    properties: mapProperties(neo4jRel.properties),
  };
}
```

### Full Query → Store Data

```typescript
export const expandNetwork = async (personId: string, hops: number = 2) => {
  return withSession(async (session) => {
    const result = await session.executeRead(async (tx) => {
      return tx.run(
        `MATCH path = (p:Person {id: $personId})-[*1..${hops}]-(connected)
         RETURN nodes(path) AS nodes, relationships(path) AS rels
         LIMIT 500`,
        { personId },
      );
    });

    const nodesMap = new Map<string, GraphNode>();
    const relsMap = new Map<string, GraphRelationship>();

    for (const record of result.records) {
      for (const node of record.get("nodes")) {
        nodesMap.set(node.elementId, toGraphNode(node));
      }
      for (const rel of record.get("rels")) {
        relsMap.set(rel.elementId, toGraphRelationship(rel));
      }
    }

    return {
      nodes: Array.from(nodesMap.values()),
      relationships: Array.from(relsMap.values()),
    };
  });
};
```

---

## 8. Parameterized Queries

Always use parameters. Never concatenate user input into Cypher strings.

```typescript
// ✅ Parameterized — safe, enables query plan caching
const result = await session.run(
  `MATCH (p:Person {id: $personId})-[r*1..2]-(connected)
   WHERE connected.timestamp >= $startDate
   RETURN p, r, connected
   LIMIT $limit`,
  { personId: id, startDate: startDate.toISOString(), limit: neo4j.int(100) },
);

// ❌ String interpolation — Cypher injection risk
const result = await session.run(
  `MATCH (p:Person {id: '${id}'})-[r*1..2]-(connected) RETURN p`,
);
```

---

## 9. Error Handling

```typescript
import { Neo4jError } from "neo4j-driver";

export const handleNeo4jError = (error: unknown): never => {
  if (error instanceof Neo4jError) {
    switch (error.code) {
      case "Neo.ClientError.Security.Unauthorized":
        throw new Error("Invalid Neo4j credentials");
      case "Neo.ClientError.Security.Forbidden":
        throw new Error("User does not have permission for this operation");
      case "Neo.ClientError.Statement.SyntaxError":
        throw new Error(`Invalid Cypher query: ${error.message}`);
      case "Neo.ClientError.Schema.ConstraintValidationFailed":
        throw new Error(`Constraint violation: ${error.message}`);
      case "Neo.TransientError.Transaction.DeadlockDetected":
        throw new Error("Deadlock detected — retry the operation");
      default:
        throw new Error(`Neo4j error [${error.code}]: ${error.message}`);
    }
  }
  throw error;
};
```

### Transient Error Retry

`executeRead`/`executeWrite` handle transient retries automatically. If using raw `session.run()`, catch and retry transient errors:

```typescript
const isTransientError = (error: unknown): boolean =>
  error instanceof Neo4jError && error.code.startsWith("Neo.TransientError");
```

---

## 10. Connection Lifecycle

```typescript
// App startup
const driver = initDriver(config.uri, config.user, config.password);
await driver.verifyConnectivity();

// App shutdown (or React cleanup)
useEffect(() => {
  return () => {
    closeDriver();
  };
}, []);
```

---

## Anti-Patterns

| Anti-Pattern                                           | Why It Fails                                                                             | Fix                                                                       |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Storing the driver in React state                      | `useState(neo4j.driver(...))` — driver is not serializable, gets recreated on re-render  | Store driver in a module-level variable                                   |
| Creating a new driver per query                        | Bypasses connection pooling, exhausts resources                                          | Create one driver at app startup, reuse it                                |
| Not closing sessions                                   | Connection pool exhaustion — queries start timing out                                    | Always close in `finally` or use `withSession` helper                     |
| String concatenation in Cypher                         | Cypher injection vulnerability                                                           | Always use parameterized queries                                          |
| Ignoring `neo4j.Integer` type                          | `toNumber()` silently overflows for values > `Number.MAX_SAFE_INTEGER`                   | Use `toString()` for display, `toBigInt()` for arithmetic on large values |
| Using `record.get('n').identity`                       | Internal numeric ID — can change across database restarts                                | Use `record.get('n').elementId` (stable string identifier)                |
| Not mapping Neo4j types before storing in Zustand      | Zustand stores (and JSON serialization) can't handle `neo4j.Integer` or `neo4j.DateTime` | Always map with `toNumber()` / `toString()` before storing                |
| Using `session.run()` for multi-statement transactions | No automatic retry on transient errors, no transaction boundary                          | Use `session.executeRead(tx => ...)` or `session.executeWrite(tx => ...)` |
