import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the Neo4j queries module before importing the route
vi.mock("@/lib/neo4j/queries", () => ({
  moveContentToStage: vi.fn().mockResolvedValue(undefined),
}));

import { POST } from "@/app/api/board/move/route";
import { moveContentToStage } from "@/lib/neo4j/queries";

function mockRequest(body: unknown): Request {
  return new Request("http://localhost/api/board/move", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/board/move", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 400 when contentId is missing", async () => {
    const res = await POST(mockRequest({ newStage: "draft" }) as never);
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/contentId/);
    expect(moveContentToStage).not.toHaveBeenCalled();
  });

  it("returns 400 when newStage is missing", async () => {
    const res = await POST(mockRequest({ contentId: "abc" }) as never);
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/newStage/);
  });

  it("returns 400 when newStage is invalid", async () => {
    const res = await POST(
      mockRequest({ contentId: "abc", newStage: "bogus" }) as never
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/newStage/);
    expect(moveContentToStage).not.toHaveBeenCalled();
  });

  it("calls moveContentToStage with valid input and returns 200", async () => {
    const res = await POST(
      mockRequest({ contentId: "abc-123", newStage: "draft" }) as never
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toEqual({ success: true });
    expect(moveContentToStage).toHaveBeenCalledWith("abc-123", "draft");
  });

  it("accepts all valid pipeline stages", async () => {
    const validStages = [
      "inspiration",
      "research",
      "draft",
      "optimize",
      "review",
      "published",
      "monitor",
      "refresh",
    ];
    for (const stage of validStages) {
      const res = await POST(
        mockRequest({ contentId: "abc", newStage: stage }) as never
      );
      expect(res.status).toBe(200);
    }
    expect(moveContentToStage).toHaveBeenCalledTimes(validStages.length);
  });

  it("returns 500 when moveContentToStage throws", async () => {
    vi.mocked(moveContentToStage).mockRejectedValueOnce(new Error("Neo4j down"));
    const res = await POST(
      mockRequest({ contentId: "abc", newStage: "draft" }) as never
    );
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toBe("Neo4j down");
  });
});
