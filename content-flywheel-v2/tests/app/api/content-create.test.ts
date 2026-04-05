import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/lib/neo4j/queries", () => ({
  createContent: vi.fn().mockResolvedValue({
    id: "new-id-123",
    title: "Test",
    slug: "test",
    author: "tester",
    stage: "inspiration",
    createdAt: "2026-04-05T12:00:00Z",
    updatedAt: "2026-04-05T12:00:00Z",
  }),
}));

import { POST } from "@/app/api/content/route";
import { createContent } from "@/lib/neo4j/queries";

function mockRequest(body: unknown): Request {
  return new Request("http://localhost/api/content", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

describe("POST /api/content", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns 400 when title is missing", async () => {
    const res = await POST(
      mockRequest({ slug: "test", author: "x" }) as never
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/title/);
  });

  it("returns 400 when slug is missing", async () => {
    const res = await POST(
      mockRequest({ title: "Test", author: "x" }) as never
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/slug/);
  });

  it("returns 400 when author is missing", async () => {
    const res = await POST(
      mockRequest({ title: "Test", slug: "test" }) as never
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toMatch(/author/);
  });

  it("creates content with all required fields and returns 201", async () => {
    const res = await POST(
      mockRequest({
        title: "Test Article",
        slug: "test-article",
        author: "Jim",
      }) as never
    );
    expect(res.status).toBe(201);
    expect(createContent).toHaveBeenCalledWith(
      expect.objectContaining({
        title: "Test Article",
        slug: "test-article",
        author: "Jim",
        stage: "inspiration", // default
      })
    );
  });

  it("defaults to inspiration stage when stage is missing", async () => {
    await POST(
      mockRequest({ title: "T", slug: "t", author: "a" }) as never
    );
    expect(createContent).toHaveBeenCalledWith(
      expect.objectContaining({ stage: "inspiration" })
    );
  });

  it("defaults to inspiration stage when invalid stage provided", async () => {
    await POST(
      mockRequest({ title: "T", slug: "t", author: "a", stage: "bogus" }) as never
    );
    expect(createContent).toHaveBeenCalledWith(
      expect.objectContaining({ stage: "inspiration" })
    );
  });

  it("accepts valid stage override", async () => {
    await POST(
      mockRequest({ title: "T", slug: "t", author: "a", stage: "draft" }) as never
    );
    expect(createContent).toHaveBeenCalledWith(
      expect.objectContaining({ stage: "draft" })
    );
  });

  it("passes through optional url field", async () => {
    await POST(
      mockRequest({
        title: "T",
        slug: "t",
        author: "a",
        url: "https://example.com",
      }) as never
    );
    expect(createContent).toHaveBeenCalledWith(
      expect.objectContaining({ url: "https://example.com" })
    );
  });

  it("sets url to null when not provided", async () => {
    await POST(
      mockRequest({ title: "T", slug: "t", author: "a" }) as never
    );
    expect(createContent).toHaveBeenCalledWith(
      expect.objectContaining({ url: null })
    );
  });

  it("returns 500 when createContent throws", async () => {
    vi.mocked(createContent).mockRejectedValueOnce(
      new Error("Constraint violation")
    );
    const res = await POST(
      mockRequest({ title: "T", slug: "t", author: "a" }) as never
    );
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toBe("Constraint violation");
  });
});
