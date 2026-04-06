import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  createWorkflowRun,
  completeWorkflowRun,
  failWorkflowRun,
} from "@/lib/workflows/helpers";

// ---------------------------------------------------------------------------
// Mock Neo4j
// ---------------------------------------------------------------------------

const mockRunCypher = vi.fn();

vi.mock("@/lib/neo4j/queries", () => ({
  runCypher: (...args: unknown[]) => mockRunCypher(...args),
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("createWorkflowRun", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRunCypher.mockResolvedValue([{ runId: "wf-123" }]);
  });

  it("creates a workflow run with optional content linking", async () => {
    const runId = await createWorkflowRun("keyword-research", "cp-1");

    expect(runId).toBe("wf-123");
    expect(mockRunCypher).toHaveBeenCalledOnce();
    const cypher = mockRunCypher.mock.calls[0][0] as string;
    expect(cypher).toContain("OPTIONAL MATCH");
    expect(cypher).toContain("FOREACH");
    expect(cypher).toContain('"keyword-research"');
  });

  it("uses direct MATCH when requireContent is true", async () => {
    await createWorkflowRun("article-outline", "cp-1", {
      requireContent: true,
    });

    const cypher = mockRunCypher.mock.calls[0][0] as string;
    expect(cypher).not.toContain("OPTIONAL MATCH");
    expect(cypher).not.toContain("FOREACH");
    expect(cypher).toContain("MATCH (c:ContentPiece");
  });

  it("passes contentId as parameter", async () => {
    await createWorkflowRun("content-ingest", "cp-42");

    const params = mockRunCypher.mock.calls[0][1] as Record<string, unknown>;
    expect(params.contentId).toBe("cp-42");
  });

  it("handles null contentId", async () => {
    await createWorkflowRun("content-ingest", null);

    const params = mockRunCypher.mock.calls[0][1] as Record<string, unknown>;
    expect(params.contentId).toBeNull();
  });
});

describe("completeWorkflowRun", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRunCypher.mockResolvedValue([]);
  });

  it("sets status to completed with summary", async () => {
    await completeWorkflowRun("wf-123", "Done: 5 keywords");

    expect(mockRunCypher).toHaveBeenCalledOnce();
    const cypher = mockRunCypher.mock.calls[0][0] as string;
    expect(cypher).toContain('w.status = "completed"');
    expect(cypher).toContain("w.summary = $summary");

    const params = mockRunCypher.mock.calls[0][1] as Record<string, unknown>;
    expect(params.runId).toBe("wf-123");
    expect(params.summary).toBe("Done: 5 keywords");
  });
});

describe("failWorkflowRun", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRunCypher.mockResolvedValue([]);
  });

  it("sets status to failed with error message from Error", async () => {
    await failWorkflowRun("wf-123", new Error("API timeout"));

    const cypher = mockRunCypher.mock.calls[0][0] as string;
    expect(cypher).toContain('w.status = "failed"');

    const params = mockRunCypher.mock.calls[0][1] as Record<string, unknown>;
    expect(params.error).toBe("API timeout");
  });

  it("uses 'Unknown error' for non-Error values", async () => {
    await failWorkflowRun("wf-123", "string error");

    const params = mockRunCypher.mock.calls[0][1] as Record<string, unknown>;
    expect(params.error).toBe("Unknown error");
  });

  it("handles null error", async () => {
    await failWorkflowRun("wf-123", null);

    const params = mockRunCypher.mock.calls[0][1] as Record<string, unknown>;
    expect(params.error).toBe("Unknown error");
  });
});
