import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/neo4j/queries", () => ({
  getContentDetailById: vi.fn(),
  updateContent: vi.fn(),
  deleteContent: vi.fn(),
}));

import { GET, PATCH, DELETE } from "@/app/api/content/[id]/route";
import { getContentDetailById, updateContent, deleteContent } from "@/lib/neo4j/queries";

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
      outline: null,
      draft: null,
      brandVoiceScore: null,
      themes: [],
      publishedTo: [],
      distributedTo: [],
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

describe("PATCH /api/content/[id]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("updates content and returns updated record", async () => {
    const updated = { id: "abc-123", title: "New Title", slug: "test", author: "Jim", stage: "draft" };
    vi.mocked(updateContent).mockResolvedValueOnce(updated as never);
    const req = new Request("http://localhost/api/content/abc-123", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "New Title" }),
    });
    const res = await PATCH(req as never, { params: Promise.resolve({ id: "abc-123" }) });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.title).toBe("New Title");
    expect(updateContent).toHaveBeenCalledWith("abc-123", { title: "New Title" });
  });

  it("returns 404 when content not found", async () => {
    vi.mocked(updateContent).mockResolvedValueOnce(null);
    const req = new Request("http://localhost/api/content/missing", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "X" }),
    });
    const res = await PATCH(req as never, { params: Promise.resolve({ id: "missing" }) });
    expect(res.status).toBe(404);
  });
});

describe("DELETE /api/content/[id]", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("deletes content and returns success", async () => {
    vi.mocked(deleteContent).mockResolvedValueOnce(true);
    const req = new Request("http://localhost/api/content/abc-123", { method: "DELETE" });
    const res = await DELETE(req as never, { params: Promise.resolve({ id: "abc-123" }) });
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.deleted).toBe(true);
  });

  it("returns 404 when content not found", async () => {
    vi.mocked(deleteContent).mockResolvedValueOnce(false);
    const req = new Request("http://localhost/api/content/missing", { method: "DELETE" });
    const res = await DELETE(req as never, { params: Promise.resolve({ id: "missing" }) });
    expect(res.status).toBe(404);
  });
});
