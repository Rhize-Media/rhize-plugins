import { describe, it, expect, vi, beforeEach } from "vitest";
import { runBrandVoiceCheck } from "@/lib/workflows/brand-voice-check";

// ---------------------------------------------------------------------------
// Mock Neo4j
// ---------------------------------------------------------------------------

const mockRunCypher = vi.fn();

vi.mock("@/lib/neo4j/queries", () => ({
  runCypher: (...args: unknown[]) => mockRunCypher(...args),
}));

// ---------------------------------------------------------------------------
// Mock workflow helpers
// ---------------------------------------------------------------------------

const mockCreateRun = vi.fn().mockResolvedValue("wf-bv-1");
const mockCompleteRun = vi.fn().mockResolvedValue(undefined);
const mockFailRun = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/workflows/helpers", () => ({
  createWorkflowRun: (...args: unknown[]) => mockCreateRun(...args),
  completeWorkflowRun: (...args: unknown[]) => mockCompleteRun(...args),
  failWorkflowRun: (...args: unknown[]) => mockFailRun(...args),
}));

// ---------------------------------------------------------------------------
// Mock Claude generateStructured
// ---------------------------------------------------------------------------

const mockGenerateStructured = vi.fn().mockResolvedValue({
  data: {
    score: 85,
    issues: [
      {
        section: "Introduction",
        issue: "Passive voice used",
        suggestion: "Use active voice for stronger impact",
      },
    ],
  },
  usage: {
    inputTokens: 500,
    outputTokens: 200,
    cacheCreationInputTokens: 0,
    cacheReadInputTokens: 0,
    cost: 0.003,
  },
});

vi.mock("@/lib/ai/claude", () => ({
  generateStructured: (...args: unknown[]) => mockGenerateStructured(...args),
}));

// ---------------------------------------------------------------------------
// Helper: set up the runCypher mock sequence for a successful run
// ---------------------------------------------------------------------------

function setupMockSequence() {
  // 1. Load draft content
  mockRunCypher.mockResolvedValueOnce([
    {
      content: "# SEO Guide\n\n## What is SEO\n\nSEO is the practice...",
      title: "SEO Guide",
    },
  ]);
  // 2. Create BrandVoiceScore node
  mockRunCypher.mockResolvedValueOnce([{ scoreId: "bvs-1" }]);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("runBrandVoiceCheck", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMockSequence();
  });

  it("scores draft and creates BrandVoiceScore node", async () => {
    const result = await runBrandVoiceCheck({ contentId: "cp-123" });

    // generateStructured was called with model "haiku"
    expect(mockGenerateStructured).toHaveBeenCalledOnce();
    const callArgs = mockGenerateStructured.mock.calls[0][0];
    expect(callArgs.model).toBe("haiku");

    // Result has brandVoiceScore with score 85
    expect(result.brandVoiceScore.score).toBe(85);

    // Result has 1 issue with section "Introduction"
    expect(result.brandVoiceScore.issues).toHaveLength(1);
    expect(result.brandVoiceScore.issues[0].section).toBe("Introduction");

    // BrandVoiceScore node was created in Neo4j
    const cypherCalls = mockRunCypher.mock.calls;
    const createScoreCall = cypherCalls.find(
      (call: unknown[]) =>
        typeof call[0] === "string" &&
        call[0].includes("CREATE (b:BrandVoiceScore")
    );
    expect(createScoreCall).toBeDefined();
  });

  it("marks workflow complete with score summary", async () => {
    await runBrandVoiceCheck({ contentId: "cp-123" });

    expect(mockCompleteRun).toHaveBeenCalledOnce();
    const summary = mockCompleteRun.mock.calls[0][1] as string;
    expect(summary).toContain("85/100");
  });

  it("marks workflow as failed when no draft exists", async () => {
    // Reset runCypher completely so the setupMockSequence queue is gone
    mockRunCypher.mockReset();
    // Load draft returns empty array
    mockRunCypher.mockResolvedValueOnce([]);

    await expect(
      runBrandVoiceCheck({ contentId: "cp-123" })
    ).rejects.toThrow();

    expect(mockFailRun).toHaveBeenCalledOnce();
  });
});
