import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { embedBatch, embedAndCacheKeywords, _setGenAI } from "@/lib/ai/embeddings";

// ---------------------------------------------------------------------------
// Mock Neo4j driver — prevent real DB calls
// ---------------------------------------------------------------------------

const mockRun = vi.fn();
const mockClose = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/neo4j/driver", () => ({
  getDriver: () => ({
    session: () => ({ run: mockRun, close: mockClose }),
  }),
}));

// ---------------------------------------------------------------------------
// Mock GoogleGenAI client factory
// ---------------------------------------------------------------------------

function makeMockGenAI() {
  return {
    models: {
      embedContent: vi.fn().mockResolvedValue({
        embeddings: [
          { values: new Array(256).fill(0.1) },
          { values: new Array(256).fill(0.2) },
        ],
      }),
    },
  } as unknown;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

afterEach(() => {
  _setGenAI(null);
  vi.clearAllMocks();
});

describe("embedBatch", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns empty array for empty input", async () => {
    const result = await embedBatch([]);
    expect(result).toEqual([]);
  });

  it("returns embedding vectors from Gemini API", async () => {
    const mock = makeMockGenAI() as { models: { embedContent: ReturnType<typeof vi.fn> } };
    _setGenAI(mock as unknown as Parameters<typeof _setGenAI>[0]);

    const result = await embedBatch(["hello", "world"]);

    expect(result).toHaveLength(2);
    expect(result[0]).toHaveLength(256);
    expect(result[0][0]).toBe(0.1);
    expect(result[1][0]).toBe(0.2);
    expect(mock.models.embedContent).toHaveBeenCalledOnce();
    expect(mock.models.embedContent).toHaveBeenCalledWith(
      expect.objectContaining({
        model: "text-embedding-004",
        contents: ["hello", "world"],
      })
    );
  });

  it("chunks texts into batches of 100", async () => {
    const mock = makeMockGenAI() as { models: { embedContent: ReturnType<typeof vi.fn> } };
    // Return 100 embeddings for the first call, 50 for the second
    mock.models.embedContent
      .mockResolvedValueOnce({
        embeddings: new Array(100).fill({ values: new Array(256).fill(0.1) }),
      })
      .mockResolvedValueOnce({
        embeddings: new Array(50).fill({ values: new Array(256).fill(0.2) }),
      });

    _setGenAI(mock as unknown as Parameters<typeof _setGenAI>[0]);

    const texts = new Array(150).fill("text");
    const result = await embedBatch(texts);

    expect(mock.models.embedContent).toHaveBeenCalledTimes(2);
    expect(result).toHaveLength(150);
  });
});

describe("embedAndCacheKeywords", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("skips keywords that already have embeddings", async () => {
    // Neo4j returns 0 records — all keywords already have embeddings
    mockRun.mockResolvedValueOnce({ records: [] });

    const mock = makeMockGenAI() as { models: { embedContent: ReturnType<typeof vi.fn> } };
    _setGenAI(mock as unknown as Parameters<typeof _setGenAI>[0]);

    const result = await embedAndCacheKeywords(["seo", "marketing"]);

    expect(result).toEqual({ embedded: 0, skipped: 2 });
    expect(mock.models.embedContent).not.toHaveBeenCalled();
  });

  it("embeds and stores missing keywords", async () => {
    // Neo4j returns 2 keywords needing embedding
    mockRun.mockResolvedValueOnce({
      records: [
        { get: () => "seo" },
        { get: () => "marketing" },
      ],
    });

    const mock = makeMockGenAI() as { models: { embedContent: ReturnType<typeof vi.fn> } };
    _setGenAI(mock as unknown as Parameters<typeof _setGenAI>[0]);

    await embedAndCacheKeywords(["seo", "marketing"]);

    // Should have called session.run 3 times:
    // 1x to find missing embeddings, 2x to SET k.embedding
    expect(mockRun).toHaveBeenCalledTimes(3);
    const secondCall = mockRun.mock.calls[1];
    expect(secondCall[0]).toContain("SET k.embedding");
    expect(secondCall[1].term).toBe("seo");
    expect(secondCall[1].vector).toHaveLength(256);

    const thirdCall = mockRun.mock.calls[2];
    expect(thirdCall[0]).toContain("SET k.embedding");
    expect(thirdCall[1].term).toBe("marketing");
  });

  it("returns correct counts", async () => {
    // 3 terms submitted, only 2 need embedding (1 already has one)
    mockRun.mockResolvedValueOnce({
      records: [
        { get: () => "seo" },
        { get: () => "content" },
      ],
    });
    // Allow the SET calls to succeed
    mockRun.mockResolvedValue({ records: [] });

    const mock = makeMockGenAI() as { models: { embedContent: ReturnType<typeof vi.fn> } };
    _setGenAI(mock as unknown as Parameters<typeof _setGenAI>[0]);

    const result = await embedAndCacheKeywords(["seo", "marketing", "content"]);

    expect(result).toEqual({ embedded: 2, skipped: 1 });
  });
});
