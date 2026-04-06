import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/neo4j/queries", () => ({
  getContentDetailById: vi.fn(),
}));

import { GET } from "@/app/api/content/[id]/route";
import { getContentDetailById } from "@/lib/neo4j/queries";

function mockRequest() {
  return new Request("http://localhost/api/content/abc");
}

describe("GET /api/content/[id]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 404 when content not found", async () => {
    vi.mocked(getContentDetailById).mockResolvedValueOnce(null);
    const res = await GET(mockRequest() as never, {
      params: Promise.resolve({ id: "missing" }),
    });
    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body.error).toBe("Not found");
  });

  it("returns content detail when found", async () => {
    const mockDetail = {
      id: "abc-123",
      title: "Test Article",
      slug: "test-article",
      author: "Jim",
      stage: "draft",
      keywords: [{ term: "test", volume: 100 }],
      serpSnapshots: [],
      backlinks: [],
      internalLinks: [],
      seoScore: null,
      workflowRuns: [],
      aiVisibility: [],
      stageHistory: [],
    };
    vi.mocked(getContentDetailById).mockResolvedValueOnce(mockDetail);
    const res = await GET(mockRequest() as never, {
      params: Promise.resolve({ id: "abc-123" }),
    });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual(mockDetail);
    expect(getContentDetailById).toHaveBeenCalledWith("abc-123");
  });

  it("returns 500 when query throws", async () => {
    vi.mocked(getContentDetailById).mockRejectedValueOnce(
      new Error("Connection lost")
    );
    const res = await GET(mockRequest() as never, {
      params: Promise.resolve({ id: "abc" }),
    });
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toBe("Connection lost");
  });
});
