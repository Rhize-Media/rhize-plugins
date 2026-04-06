import { runCypher } from "@/lib/neo4j/queries";
import type { WorkflowType } from "@/types";

// ---------------------------------------------------------------------------
// Shared workflow run lifecycle helpers
// ---------------------------------------------------------------------------
// Every workflow creates a WorkflowRun node at start, then marks it
// completed or failed at the end. These three operations are identical
// across all workflows — only the `type` and linking strategy differ.
// ---------------------------------------------------------------------------

/**
 * Create a WorkflowRun node and optionally link it to a ContentPiece.
 *
 * When `contentId` is provided and guaranteed to exist, uses a direct MATCH.
 * When `contentId` may be null or the piece may not exist yet, uses
 * OPTIONAL MATCH + FOREACH/CASE (the standard conditional pattern).
 */
export async function createWorkflowRun(
  type: WorkflowType,
  contentId: string | null,
  opts: { requireContent?: boolean } = {}
): Promise<string> {
  const linkClause = opts.requireContent
    ? `MATCH (c:ContentPiece {id: $contentId})
    CREATE (c)-[:HAS_WORKFLOW_RUN]->(w)`
    : `OPTIONAL MATCH (c:ContentPiece {id: $contentId})
    FOREACH (_ IN CASE WHEN c IS NOT NULL THEN [1] ELSE [] END |
      CREATE (c)-[:HAS_WORKFLOW_RUN]->(w)
    )`;

  const result = await runCypher(
    `CREATE (w:WorkflowRun {
      id: randomUUID(), type: "${type}",
      contentId: $contentId, status: "running",
      startedAt: datetime()
    })
    WITH w
    ${linkClause}
    RETURN w.id AS runId`,
    { contentId }
  );
  return result[0].runId as string;
}

/**
 * Mark a WorkflowRun as completed with a summary string.
 */
export async function completeWorkflowRun(
  runId: string,
  summary: string
): Promise<void> {
  await runCypher(
    `MATCH (w:WorkflowRun {id: $runId})
     SET w.status = "completed", w.completedAt = datetime(),
         w.summary = $summary`,
    { runId, summary }
  );
}

/**
 * Mark a WorkflowRun as failed. Extracts the message from an Error
 * (or uses "Unknown error" for non-Error values) and stores it on the node.
 */
export async function failWorkflowRun(
  runId: string,
  error: unknown
): Promise<void> {
  const message = error instanceof Error ? error.message : "Unknown error";
  await runCypher(
    `MATCH (w:WorkflowRun {id: $runId})
     SET w.status = "failed", w.completedAt = datetime(), w.error = $error`,
    { runId, error: message }
  );
}
