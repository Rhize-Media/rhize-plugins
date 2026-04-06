import { describe, it, expect, vi, beforeEach } from "vitest";
import { runArticleOutline } from "@/lib/workflows/article-outline";

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
// Mock Claude
// ---------------------------------------------------------------------------

const mockGenerateStructured = vi.fn().mockResolvedValue({
  data: {
    title: "Complete Guide to SEO",
    metaDescription:
      "Learn SEO best practices with this comprehensive guide covering keywords, content optimization, and link building.",
    sections: [
      {
        heading: "What is SEO?",
        bullets: ["Definition", "Importance"],
        targetWordCount: 300,
      },
      {
        heading: "Keyword Research",
        bullets: ["Tools", "Strategy"],
        targetWordCount: 400,
      },
      {
        heading: "On-Page Optimization",
        bullets: ["Title tags", "Meta descriptions"],
        targetWordCount: 350,
      },
    ],
    faqTopics: ["How long does SEO take?", "Is SEO worth it?"],
    internalLinks: ["Content Marketing Guide (/blog/content-marketing)"],
  },
  usage: {
    inputTokens: 500,
    outputTokens: 200,
    cacheCreationInputTokens: 100,
    cacheReadInputTokens: 0,
    cost: 0.01,
  },
});

vi.mock("@/lib/ai/claude", () => ({
  generateStructured: (...args: unknown[]) => mockGenerateStructured(...args),
}));

// ---------------------------------------------------------------------------
// Helper: set up the runCypher mock sequence for a successful run
// ---------------------------------------------------------------------------

function setupMockSequence() {
  // 1. Create WorkflowRun
  mockRunCypher.mockResolvedValueOnce([{ runId: "wf-789" }]);
  // 2. Load content + keywords + themes
  mockRunCypher.mockResolvedValueOnce([
    {
      title: "SEO Guide",
      summary: "A guide about SEO",
      url: "https://example.com",
      keywords: ["seo", "ranking"],
      themes: ["SEO"],
    },
  ]);
  // 3. Load SERP data
  mockRunCypher.mockResolvedValueOnce([{ keyword: "seo", position: 5 }]);
  // 4. Load internal links
  mockRunCypher.mockResolvedValueOnce([
    { title: "Content Marketing", slug: "content-marketing" },
  ]);
  // 5. Create Outline node
  mockRunCypher.mockResolvedValueOnce([{ outlineId: "ol-123" }]);
  // 6. Mark workflow complete
  mockRunCypher.mockResolvedValueOnce([]);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("runArticleOutline", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupMockSequence();
  });

  it("generates outline and creates Outline node", async () => {
    const result = await runArticleOutline({ contentId: "cp-123" });

    // generateStructured was called with model "sonnet"
    expect(mockGenerateStructured).toHaveBeenCalledOnce();
    const callArgs = mockGenerateStructured.mock.calls[0][0];
    expect(callArgs.model).toBe("sonnet");

    // System prompt has cache_control
    expect(callArgs.system[0].cache_control).toEqual({ type: "ephemeral" });

    // Result has outline with 3 sections
    expect(result.outline.sections).toHaveLength(3);
    expect(result.outline.title).toBe("Complete Guide to SEO");

    // Outline node was created in Neo4j
    const cypherCalls = mockRunCypher.mock.calls;
    const createOutlineCall = cypherCalls.find(
      (call: unknown[]) =>
        typeof call[0] === "string" && call[0].includes("CREATE (o:Outline")
    );
    expect(createOutlineCall).toBeDefined();
  });

  it("moves content to draft stage", async () => {
    await runArticleOutline({ contentId: "cp-123" });

    expect(mockMoveStage).toHaveBeenCalledWith("cp-123", "draft");
  });

  it("marks workflow as failed on error", async () => {
    // Reset mocks and set up only the first call (create WorkflowRun)
    vi.clearAllMocks();
    mockRunCypher.mockResolvedValueOnce([{ runId: "wf-789" }]);
    // Content load succeeds
    mockRunCypher.mockResolvedValueOnce([
      {
        title: "SEO Guide",
        summary: "A guide about SEO",
        url: "https://example.com",
        keywords: ["seo", "ranking"],
        themes: ["SEO"],
      },
    ]);
    // SERP data succeeds
    mockRunCypher.mockResolvedValueOnce([{ keyword: "seo", position: 5 }]);
    // Internal links succeeds
    mockRunCypher.mockResolvedValueOnce([
      { title: "Content Marketing", slug: "content-marketing" },
    ]);

    // Make generateStructured throw
    mockGenerateStructured.mockRejectedValueOnce(new Error("AI service down"));

    // The error catch block calls runCypher to mark workflow failed
    mockRunCypher.mockResolvedValueOnce([]);

    await expect(runArticleOutline({ contentId: "cp-123" })).rejects.toThrow(
      "AI service down"
    );

    // Verify the workflow run was marked as failed
    const lastCypherCall =
      mockRunCypher.mock.calls[mockRunCypher.mock.calls.length - 1];
    expect(lastCypherCall[0]).toContain('w.status = "failed"');
    expect(lastCypherCall[1].error).toBe("AI service down");
  });
});
