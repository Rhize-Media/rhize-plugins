import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { runContentIngest, _setFirecrawl } from "@/lib/workflows/content-ingest";

// ---------------------------------------------------------------------------
// Mock Neo4j
// ---------------------------------------------------------------------------

const mockRunCypher = vi.fn();
vi.mock("@/lib/neo4j/queries", () => ({
  runCypher: (...args: unknown[]) => mockRunCypher(...args),
  linkAuthorExpertise: vi.fn(),
}));

// ---------------------------------------------------------------------------
// Mock Claude
// ---------------------------------------------------------------------------

vi.mock("@/lib/ai/claude", () => ({
  generateStructured: vi.fn().mockResolvedValue({
    data: {
      themes: ["SEO", "Content Marketing", "Analytics"],
      summary: "An article about SEO strategies.",
      title: "SEO Best Practices",
      author: "Jane Doe",
    },
    usage: {
      inputTokens: 100,
      outputTokens: 50,
      cacheCreationInputTokens: 0,
      cacheReadInputTokens: 0,
      cost: 0.001,
    },
  }),
}));

// ---------------------------------------------------------------------------
// Mock embeddings
// ---------------------------------------------------------------------------

vi.mock("@/lib/ai/embeddings", () => ({
  embedBatch: vi.fn().mockResolvedValue([[0.1, 0.2, 0.3]]),
}));

// ---------------------------------------------------------------------------
// Mock Firecrawl client
// ---------------------------------------------------------------------------

function makeMockFirecrawl() {
  return {
    scrape: vi.fn().mockResolvedValue({
      markdown: "# SEO Best Practices\n\nGreat content about SEO...",
      metadata: { title: "SEO Best Practices", author: "Jane Doe" },
    }),
  } as unknown;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("runContentIngest", () => {
  beforeEach(() => {
    vi.clearAllMocks();

    // Default: return empty arrays for most Cypher calls
    mockRunCypher.mockResolvedValue([]);

    // First call — create WorkflowRun
    mockRunCypher.mockResolvedValueOnce([{ runId: "wf-123" }]);
    // Second call — create ContentPiece
    mockRunCypher.mockResolvedValueOnce([{ id: "cp-456" }]);

    // Inject mock Firecrawl
    const mock = makeMockFirecrawl();
    _setFirecrawl(mock as unknown as Parameters<typeof _setFirecrawl>[0]);
  });

  afterEach(() => {
    _setFirecrawl(null);
  });

  it("scrapes URL and creates content piece with themes", async () => {
    const result = await runContentIngest({ url: "https://example.com/article" });

    // Firecrawl scrape was called with the URL
    const mock = makeMockFirecrawl();
    // We need to check the injected mock, so re-inject and check the call
    // Actually, the mock was already injected in beforeEach — verify via side effects
    // mockRunCypher was called multiple times: WorkflowRun, ContentPiece, summary, themes, embedding, link, complete
    expect(mockRunCypher).toHaveBeenCalledTimes(
      1 + // create WorkflowRun
      1 + // create ContentPiece
      1 + // set summary
      3 + // 3 themes (SEO, Content Marketing, Analytics)
      1 + // embed summary
      1 + // link workflow run to content piece
      1   // mark workflow complete
    );

    // Result should have contentPiece with title
    expect(result.contentPiece).toBeDefined();
    expect(result.contentPiece.title).toBe("SEO Best Practices");

    // Themes array should have 3 items
    expect(result.themes).toHaveLength(3);
    expect(result.themes).toEqual(["SEO", "Content Marketing", "Analytics"]);
  });

  it("creates workflow run and marks it completed", async () => {
    await runContentIngest({ url: "https://example.com/article" });

    // First Cypher call creates the WorkflowRun
    const firstCallQuery = mockRunCypher.mock.calls[0][0] as string;
    expect(firstCallQuery).toContain("WorkflowRun");
    expect(firstCallQuery).toContain("content-ingest");

    // Last Cypher call marks workflow as completed
    const lastCallIndex = mockRunCypher.mock.calls.length - 1;
    const lastCallQuery = mockRunCypher.mock.calls[lastCallIndex][0] as string;
    expect(lastCallQuery).toContain('status = "completed"');
  });

  it("marks workflow as failed on error", async () => {
    // Make Firecrawl scrape throw an error
    const failingMock = {
      scrape: vi.fn().mockRejectedValue(new Error("Scrape failed")),
    } as unknown;
    _setFirecrawl(failingMock as unknown as Parameters<typeof _setFirecrawl>[0]);

    await expect(
      runContentIngest({ url: "https://example.com/broken" })
    ).rejects.toThrow("Scrape failed");

    // The last Cypher call should set status to "failed"
    const lastCallIndex = mockRunCypher.mock.calls.length - 1;
    const lastCallQuery = mockRunCypher.mock.calls[lastCallIndex][0] as string;
    expect(lastCallQuery).toContain('status = "failed"');

    // Should also store the error message
    const lastCallParams = mockRunCypher.mock.calls[lastCallIndex][1] as Record<string, unknown>;
    expect(lastCallParams.error).toBe("Scrape failed");
  });
});
