import { describe, it, expect, vi, beforeEach } from "vitest";
import { runArticleDraft } from "@/lib/workflows/article-draft";

// ---------------------------------------------------------------------------
// Mock Neo4j queries
// ---------------------------------------------------------------------------

const mockRunCypher = vi.fn();
const mockMoveStage = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/neo4j/queries", () => ({
  runCypher: (...args: unknown[]) => mockRunCypher(...args),
  moveContentToStage: (...args: unknown[]) => mockMoveStage(...args),
}));

// ---------------------------------------------------------------------------
// Mock workflow helpers
// ---------------------------------------------------------------------------

const mockCreateRun = vi.fn().mockResolvedValue("wf-draft-1");
const mockCompleteRun = vi.fn().mockResolvedValue(undefined);
const mockFailRun = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/workflows/helpers", () => ({
  createWorkflowRun: (...args: unknown[]) => mockCreateRun(...args),
  completeWorkflowRun: (...args: unknown[]) => mockCompleteRun(...args),
  failWorkflowRun: (...args: unknown[]) => mockFailRun(...args),
}));

// ---------------------------------------------------------------------------
// Mock Claude generateText
// ---------------------------------------------------------------------------

const mockGenerateText = vi.fn().mockResolvedValue({
  text: "This is a well-written section about the topic with detailed examples and analysis.",
  usage: {
    inputTokens: 200,
    outputTokens: 100,
    cacheCreationInputTokens: 50,
    cacheReadInputTokens: 0,
    cost: 0.005,
  },
});

vi.mock("@/lib/ai/claude", () => ({
  generateText: (...args: unknown[]) => mockGenerateText(...args),
}));

// ---------------------------------------------------------------------------
// Helper: set up the runCypher mock sequence for a successful run
// ---------------------------------------------------------------------------

function setupMockSequence() {
  // 1. Load outline from Neo4j
  mockRunCypher.mockResolvedValueOnce([
    {
      title: "SEO Guide",
      metaDescription: "A guide",
      sections: JSON.stringify([
        {
          heading: "What is SEO",
          bullets: ["Definition", "Importance"],
          targetWordCount: 300,
        },
        {
          heading: "Keyword Research",
          bullets: ["Tools", "Strategy"],
          targetWordCount: 400,
        },
      ]),
      faqTopics: ["How long does SEO take?"],
    },
  ]);

  // 2. Create Draft node
  mockRunCypher.mockResolvedValueOnce([{ draftId: "draft-1" }]);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("runArticleDraft", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMockSequence();
  });

  it("generates sections in parallel and creates draft", async () => {
    const result = await runArticleDraft({ contentId: "cp-123" });

    // generateText called once per section (2 sections)
    expect(mockGenerateText).toHaveBeenCalledTimes(2);

    // Each call uses model "sonnet" and has system prompt with cache_control
    for (const call of mockGenerateText.mock.calls) {
      const callArgs = call[0];
      expect(callArgs.model).toBe("sonnet");
      expect(callArgs.system[0].cache_control).toEqual({ type: "ephemeral" });
    }

    // Result draft content contains both section headings
    expect(result.draft.content).toContain("## What is SEO");
    expect(result.draft.content).toContain("## Keyword Research");

    // Result has wordCount > 0
    expect(result.draft.wordCount).toBeGreaterThan(0);
  });

  it("moves content to optimize stage", async () => {
    await runArticleDraft({ contentId: "cp-123" });

    expect(mockMoveStage).toHaveBeenCalledWith("cp-123", "optimize");
  });

  it("calculates total cost from all sections", async () => {
    const result = await runArticleDraft({ contentId: "cp-123" });

    // 2 sections x $0.005 per section = $0.01
    expect(result.totalCost).toBe(0.01);
  });

  it("marks workflow as failed when no outline exists", async () => {
    // Fully reset all mocks (clears queued mockResolvedValueOnce calls)
    vi.resetAllMocks();
    mockCreateRun.mockResolvedValue("wf-draft-1");
    mockCompleteRun.mockResolvedValue(undefined);
    mockFailRun.mockResolvedValue(undefined);

    // Outline query returns empty array — no outline exists
    mockRunCypher.mockResolvedValueOnce([]);

    await expect(runArticleDraft({ contentId: "cp-123" })).rejects.toThrow(
      "No outline found"
    );

    expect(mockFailRun).toHaveBeenCalled();
  });
});
