---
name: neo4j-data-models
description: Neo4j graph data modeling patterns — node/relationship design, fraud detection schemas, and modeling best practices.
---

# Neo4j Data Models

## When to Use

Use this skill when designing or extending a Neo4j graph data model. Covers naming conventions, node/relationship design, property management, fraud detection domain models, and modeling best practices.

## Design Process

Start with specific business questions before designing the model. Follow a three-phase cycle:

1. **Conceptualize** the structure (nodes, relationships, properties)
2. **Design queries** that answer the business questions
3. **Validate** against real data and optimize

Every node requires a unique identifier or property combination. Prioritize the model around the application's most frequent or critical queries.

## Naming Conventions

### Node Labels — CapitalCase

```cypher
CREATE (:Person {name: "Alice"})
CREATE (:Company {name: "Neo4j"})
CREATE (:Transaction {transactionId: "TX-001"})
```

### Relationship Types — UPPER_SNAKE_CASE

```cypher
(:Person)-[:WORKS_AT]->(:Company)
(:Account)-[:PERFORM]->(:Transaction)
(:Customer)-[:HAS_EMAIL]->(:Email)
```

### Properties — camelCase

```cypher
CREATE (:Person {firstName: "Alice", lastName: "Smith", deptId: 101})
CREATE (:Transaction {transactionId: "TX-001", createdAt: datetime()})
```

## Node Design

### Keep Labels Minimal (max 4)

Additional attributes belong in properties, not labels:

```cypher
// BAD: too many labels
CREATE (:Person:Employee:Developer:Manager {name: "Alice"})

// GOOD: use properties for attributes
CREATE (:Person {name: "Alice", role: "Developer", department: "Engineering"})
```

### Eliminate Redundancy with Shared Nodes

Instead of duplicating data across nodes, create shared nodes:

```cypher
// BAD: email duplicated as string property on multiple customers
CREATE (:Customer {email: "shared@example.com"})
CREATE (:Customer {email: "shared@example.com"})

// GOOD: shared Email node
CREATE (e:Email {address: "shared@example.com"})
CREATE (c1:Customer)-[:HAS_EMAIL]->(e)
CREATE (c2:Customer)-[:HAS_EMAIL]->(e)
```

### Extract Collections into Nodes

When attributes form collections, connect them as separate nodes rather than storing arrays:

```cypher
// BAD: array property
CREATE (:Customer {phones: ["+1-555-0100", "+1-555-0200"]})

// GOOD: separate nodes with relationships
CREATE (c:Customer)-[:HAS_PHONE]->(:Phone {number: "+1-555-0100"})
CREATE (c)-[:HAS_PHONE]->(:Phone {number: "+1-555-0200"})
```

## Relationship Design

### Use Specific, Descriptive Types

```cypher
// BAD: generic relationship
(:Person)-[:RELATED_TO]->(:Company)

// GOOD: descriptive type
(:Person)-[:WORKS_AT]->(:Company)
(:Person)-[:FOUNDED]->(:Company)
```

### Single Direction, Not Symmetric Pairs

```cypher
// BAD: redundant symmetric relationships
(:Person)-[:KNOWS]->(:Person)
(:Person)<-[:KNOWS]-(:Person)

// GOOD: single direction, query in either direction
(:Person)-[:KNOWS]->(:Person)
// Query: MATCH (a)-[:KNOWS]-(b)  -- undirected traversal
```

### Intermediate Nodes for Hyperedges

When a relationship involves three or more entities, introduce an intermediate node:

```cypher
// Model: Alice and Bob worked on a project with specific roles
CREATE (a:Person {name: "Alice"})-[:WORKED_ON]->(w:Work {role: "Contributor"})
CREATE (w)-[:FOR_PROJECT]->(p:Project {name: "GraphDB Project"})
CREATE (b:Person {name: "Bob"})-[:WORKED_ON]->(w)
```

## Property Management

### Properties for Identification and Querying

- **Identification properties**: unique keys for anchoring queries (indexed)
- **Query-support properties**: simple, indexed properties for filtering and traversal
- **Decoration properties**: complex data returned in results only (not indexed)

### Always Create Constraints on Business Keys

```cypher
CREATE CONSTRAINT customer_unique FOR (c:Customer) REQUIRE c.customerId IS UNIQUE
CREATE CONSTRAINT email_unique FOR (e:Email) REQUIRE e.address IS UNIQUE
CREATE CONSTRAINT account_unique FOR (a:Account) REQUIRE a.accountNumber IS UNIQUE
```

### Index Frequently Queried Properties

```cypher
CREATE INDEX customer_nationality FOR (c:Customer) ON (c.nationality)
CREATE INDEX transaction_date FOR (t:Transaction) ON (t.timestamp)
```

## Data Loading Best Practices

1. **Establish constraints first** — unique constraints on business keys before loading
2. **Use MERGE for nodes** with unique identifiers (avoids duplicates)
3. **Batch large datasets** — process in chunks of 1,000–10,000
4. **Pre-clean source data** — deduplicate before loading
5. **Transform foreign keys to relationships** — don't store FKs as properties

```cypher
// Batch loading pattern
UNWIND $batch AS row
MERGE (c:Customer {customerId: row.customerId})
ON CREATE SET c.firstName = row.firstName, c.lastName = row.lastName
MERGE (e:Email {address: row.email})
MERGE (c)-[:HAS_EMAIL]->(e)
```

## Standard Patterns

### Linked Lists (Ordered Sequences)

```cypher
// Chain events in order
CREATE (e1:Event)-[:NEXT]->(e2:Event)-[:NEXT]->(e3:Event)

// Traverse in order
MATCH (start:Event {id: $startId})-[:NEXT*]->(subsequent:Event)
RETURN subsequent
```

### Timeline Trees

```cypher
// Year -> Month -> Day hierarchy
CREATE (:Year {value: 2024})-[:HAS_MONTH]->(:Month {value: 3})-[:HAS_DAY]->(:Day {value: 15})

// Find all events on a specific day
MATCH (:Year {value: 2024})-[:HAS_MONTH]->(:Month {value: 3})-[:HAS_DAY]->(d:Day {value: 15})
MATCH (d)<-[:ON_DAY]-(event)
RETURN event
```

### Transaction Base Model (Reference)

This is the Neo4j reference data model for banking transactions, fraud detection, and financial investigation. Use it as the canonical schema when building fraud or banking applications.

#### Graph Overview

```
Customer -[:HAS_EMAIL]-> Email
Customer -[:HAS_PHONE]-> Phone
Customer -[:HAS_ADDRESS]-> Address
Customer -[:HAS_PASSPORT]-> Passport
Customer -[:HAS_DRIVING_LICENSE]-> DrivingLicense
Customer -[:HAS_FACE]-> Face
Customer -[:HAS_NATIONALITY]-> Country
Customer -[:HAS_ACCOUNT {role, since}]-> Account
Account  -[:PERFORMS]-> Transaction -[:BENEFITS_TO]-> Account
Account  -[:IS_HOSTED]-> Country
Transaction -[:IMPLIED {totalMovements}]-> Movement
Counterparty -[:HAS_ACCOUNT {since}]-> Account
Counterparty -[:HAS_ADDRESS {since, isCurrent}]-> Address
Address  -[:LOCATED_IN]-> Country
Device   -[:USED_BY {lastUsed}]-> Customer
Session  -[:SESSION_USES_DEVICE]-> Device
Session  -[:USES_IP]-> IP
IP       -[:IS_ALLOCATED_TO {createdAt}]-> ISP
IP       -[:LOCATED_IN {createdAt}]-> Location
Location -[:LOCATED_IN]-> Country
Alert    -[:TRIGGERED]-> Case
Account  -[:SUBJECT_OF]-> Case
Customer -[:SUBJECT_OF]-> Case
```

Account labels: `Account` (required), plus `Internal`, `External`, `HighRiskJurisdiction`, `Flagged`, `UnderInvestigation`, `Confirmed`.

#### Node Labels and Key Properties

| Label              | Key Properties                                       | Other Properties                                                                                                                    |
| ------------------ | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **Account**        | `accountNumber` (String)                             | `accountType`, `openedDate`, `closedDate`, `suspendedDate`                                                                          |
| **Customer**       | `customerId` (String)                                | `firstName`, `middleName`, `lastName`, `dateOfBirth` (Date), `placeOfBirth`, `countryOfBirth`                                       |
| **Transaction**    | `transactionId` (String)                             | `amount` (Float, always positive), `currency` (ISO 4217), `date` (DateTime), `message`, `type`                                      |
| **Movement**       | `movementId` (String)                                | `amount` (Float), `currency`, `date` (DateTime), `description`, `status`, `sequenceNumber` (Integer), `authorisedBy`, `validatedBy` |
| **Counterparty**   | `counterpartyId` (String)                            | `name`, `type` (INDIVIDUAL/BUSINESS/GOVERNMENT/CHARITY), `registrationNumber`                                                       |
| **Email**          | `address` (String)                                   | `domain`                                                                                                                            |
| **Phone**          | `phoneNumber` (String)                               | `countryCode`                                                                                                                       |
| **Address**        | `addressLine1` + `postTown` + `postCode` (composite) | `addressLine2`, `region`, `latitude`, `longitude`                                                                                   |
| **Passport**       | `passportNumber` (String)                            | `issueDate`, `expiryDate`, `issuingCountry`, `nationality`                                                                          |
| **DrivingLicense** | `licenseNumber` + `issuingCountry` (composite)       | `issueDate`, `expiryDate`                                                                                                           |
| **Face**           | `faceId` (String)                                    | `embedding` (List\<Float\>, 512–1536 dims)                                                                                          |
| **Device**         | `deviceId` (String)                                  | `deviceType`, `userAgent`                                                                                                           |
| **Session**        | `sessionId` (String)                                 | `status`                                                                                                                            |
| **IP**             | `ipAddress` (String)                                 | —                                                                                                                                   |
| **ISP**            | `name` (String)                                      | —                                                                                                                                   |
| **Location**       | `city` + `postCode` + `country`                      | `latitude`, `longitude`                                                                                                             |
| **Country**        | `code` (ISO 3166-1 alpha-2)                          | `name`                                                                                                                              |
| **Alert**          | `alertId` (String)                                   | `ruleName`, `ruleId`, `severity` (LOW/MEDIUM/HIGH/CRITICAL), `triggeredAt`                                                          |
| **Case**           | `caseId` (String)                                    | `status`, `outcome`, `financialStakes` (Float), `investigatedBy`, `closedAt`                                                        |

All nodes with timestamps use `createdAt` (DateTime) for record creation.

#### Relationship Types

| Relationship           | Direction                            | Properties                                                     |
| ---------------------- | ------------------------------------ | -------------------------------------------------------------- |
| `:HAS_ACCOUNT`         | Customer→Account                     | `role`, `since`                                                |
| `:HAS_ACCOUNT`         | Counterparty→Account                 | `since`                                                        |
| `:HAS_EMAIL`           | Customer→Email                       | `since`                                                        |
| `:HAS_PHONE`           | Customer→Phone                       | `since`                                                        |
| `:HAS_ADDRESS`         | Customer→Address                     | `addedAt`, `lastChangedAt`, `isCurrent`                        |
| `:HAS_ADDRESS`         | Counterparty→Address                 | `since`, `isCurrent`                                           |
| `:HAS_PASSPORT`        | Customer→Passport                    | `verificationDate`, `verificationMethod`, `verificationStatus` |
| `:HAS_DRIVING_LICENSE` | Customer→DrivingLicense              | `verificationDate`, `verificationMethod`, `verificationStatus` |
| `:HAS_FACE`            | Customer→Face                        | `verificationDate`, `verificationMethod`, `verificationStatus` |
| `:HAS_NATIONALITY`     | Customer→Country                     | —                                                              |
| `:PERFORMS`            | Account→Transaction                  | —                                                              |
| `:BENEFITS_TO`         | Transaction→Account                  | —                                                              |
| `:IMPLIED`             | Transaction→Movement                 | `totalMovements`                                               |
| `:IS_HOSTED`           | Account→Country                      | —                                                              |
| `:SESSION_USES_DEVICE` | Session→Device                       | —                                                              |
| `:USES_IP`             | Session→IP                           | —                                                              |
| `:USED_BY`             | Device→Customer                      | `lastUsed`                                                     |
| `:IS_ALLOCATED_TO`     | IP→ISP                               | `createdAt`                                                    |
| `:LOCATED_IN`          | Address/IP/Location→Country/Location | `createdAt` (on IP→Location)                                   |
| `:SUBJECT_OF`          | Account/Customer→Case                | —                                                              |
| `:TRIGGERED`           | Alert→Case                           | —                                                              |

#### Constraints and Indexes

```cypher
// Node key constraints (unique business identifiers)
CREATE CONSTRAINT customer_id IF NOT EXISTS
  FOR (c:Customer) REQUIRE c.customerId IS NODE KEY;
CREATE CONSTRAINT account_number IF NOT EXISTS
  FOR (a:Account) REQUIRE a.accountNumber IS NODE KEY;
CREATE CONSTRAINT transaction_id IF NOT EXISTS
  FOR (t:Transaction) REQUIRE t.transactionId IS NODE KEY;
CREATE CONSTRAINT movement_id IF NOT EXISTS
  FOR (m:Movement) REQUIRE m.movementId IS NODE KEY;
CREATE CONSTRAINT email_address IF NOT EXISTS
  FOR (e:Email) REQUIRE e.address IS NODE KEY;
CREATE CONSTRAINT phone_number IF NOT EXISTS
  FOR (p:Phone) REQUIRE p.number IS NODE KEY;
CREATE CONSTRAINT passport_number IF NOT EXISTS
  FOR (p:Passport) REQUIRE (p.passportNumber, p.issuingCountry) IS NODE KEY;
CREATE CONSTRAINT driving_licence_number IF NOT EXISTS
  FOR (d:DrivingLicense) REQUIRE (d.licenseNumber, d.issuingCountry) IS NODE KEY;
CREATE CONSTRAINT device_id IF NOT EXISTS
  FOR (d:Device) REQUIRE d.deviceId IS NODE KEY;
CREATE CONSTRAINT ip_address IF NOT EXISTS
  FOR (i:IP) REQUIRE i.ipAddress IS NODE KEY;
CREATE CONSTRAINT session_id IF NOT EXISTS
  FOR (s:Session) REQUIRE s.sessionId IS NODE KEY;
CREATE CONSTRAINT face_id IF NOT EXISTS
  FOR (f:Face) REQUIRE f.faceId IS NODE KEY;
CREATE CONSTRAINT counterparty_id IF NOT EXISTS
  FOR (cp:Counterparty) REQUIRE cp.counterpartyId IS NODE KEY;
CREATE CONSTRAINT isp_name IF NOT EXISTS
  FOR (i:ISP) REQUIRE i.name IS NODE KEY;
CREATE CONSTRAINT country_code IF NOT EXISTS
  FOR (c:Country) REQUIRE c.code IS NODE KEY;
CREATE CONSTRAINT address_composite IF NOT EXISTS
  FOR (a:Address) REQUIRE (a.addressLine1, a.postTown, a.postCode) IS NODE KEY;
CREATE CONSTRAINT alert_id IF NOT EXISTS
  FOR (a:Alert) REQUIRE a.alertId IS NODE KEY;
CREATE CONSTRAINT case_id IF NOT EXISTS
  FOR (c:Case) REQUIRE c.caseId IS NODE KEY;

// Performance indexes
CREATE INDEX transaction_date_idx IF NOT EXISTS FOR (t:Transaction) ON (t.date);
CREATE INDEX transaction_amount_idx IF NOT EXISTS FOR (t:Transaction) ON (t.amount);

// Vector index for facial recognition
CALL db.index.vector.createNodeIndex(
  'face_embedding_idx', 'Face', 'embedding', 1536, 'cosine'
);

// Full-text index for customer name search
CREATE FULLTEXT INDEX customer_name_idx IF NOT EXISTS
  FOR (c:Customer) ON EACH [c.firstName, c.lastName, c.middleName];
```

#### Key Design Decisions

- **PII as separate nodes** (Email, Phone, Address, Passport, DrivingLicense, Face) — enables shared-identity detection via graph traversal
- **Transaction as a node** (not a relationship) — allows attaching amount, currency, timestamp, and linking to Movements
- **Movement sub-transactions** — Transaction `:IMPLIED` Movement captures multi-part payments (installments, fees)
- **Account multi-labels** — `Internal`, `External`, `HighRiskJurisdiction` enable label-based filtering without property checks
- **Verification on relationships** — `:HAS_PASSPORT`, `:HAS_DRIVING_LICENSE`, `:HAS_FACE` carry `verificationDate/Method/Status` so the same document can have different verification states per customer
- **Session → Device → Customer chain** — connects digital activity to identity for device fingerprinting and session analysis
- **IP → ISP + Location** — enriches network data for geographic anomaly detection
- **Alert → Case pipeline** — separates automated detection (Alert) from human investigation (Case) with `:TRIGGERED` and `:SUBJECT_OF`

#### Fraud Investigation Pattern

```cypher
// Flag an account and open a case
MATCH (a:Account {accountNumber: $accNum})
SET a:Flagged

CREATE (alert:Alert {
  alertId: $alertId,
  ruleName: $ruleName,
  severity: 'HIGH',
  triggeredAt: datetime()
})
CREATE (case:Case {
  caseId: $caseId,
  status: 'OPEN',
  createdAt: datetime()
})
CREATE (alert)-[:TRIGGERED]->(case)
CREATE (a)-[:SUBJECT_OF]->(case)

// Link customer to the same case
MATCH (c:Customer)-[:HAS_ACCOUNT]->(a:Account)-[:SUBJECT_OF]->(case:Case {caseId: $caseId})
CREATE (c)-[:SUBJECT_OF]->(case)
```

## Query Performance

- **Anchor on indexed properties** — start MATCH from a constrained, indexed node
- **Use specific relationship types** — `[:PERFORMS]` not `[*]`
- **PROFILE queries** to verify index usage and eliminate CartesianProduct operators
- **Pre-aggregate statistics** for frequently accessed counts/sums
- **Use label filtering** — `MATCH (a:Account:HighRiskJurisdiction)` is faster than `WHERE a.jurisdiction = 'high-risk'`

## Anti-Patterns

### 1. Modeling Everything as Properties

```cypher
// BAD: can't traverse to find shared attributes
CREATE (:Customer {email: "a@b.com", phone: "555-0100"})

// GOOD: nodes enable graph queries
CREATE (:Customer)-[:HAS_EMAIL]->(:Email {address: "a@b.com"})
```

### 2. Generic Relationship Types

```cypher
// BAD: loses semantic meaning
(:Customer)-[:CONNECTED_TO]->(:Account)

// GOOD: specific and queryable
(:Customer)-[:HAS_ACCOUNT]->(:Account)
```

### 3. Symmetric Relationships

Don't create both directions — Cypher can traverse relationships regardless of direction.

### 4. Missing Unique Constraints

Always create constraints on business keys before loading data. Without them, MERGE creates duplicates.

### 5. Storing Foreign Keys as Properties

```cypher
// BAD: relational thinking
CREATE (:Order {customerId: "C001", productId: "P001"})

// GOOD: graph thinking
CREATE (:Customer {customerId: "C001"})-[:PLACED]->(:Order)-[:CONTAINS]->(:Product {productId: "P001"})
```

### 6. Unbounded Fanout Without Grouping

If a node has 100,000+ relationships of the same type, consider intermediate grouping nodes (e.g., group by time period or category).

## Validation Checklist

- [ ] Model addresses all business questions
- [ ] Every node has a unique identifier
- [ ] Relationship types are specific and meaningful
- [ ] No symmetric relationship pairs
- [ ] Unique constraints exist on business keys
- [ ] Critical query paths are indexed
- [ ] Model validated with representative data volume
- [ ] Naming conventions are consistent (CapitalCase labels, UPPER_SNAKE_CASE rels, camelCase props)
