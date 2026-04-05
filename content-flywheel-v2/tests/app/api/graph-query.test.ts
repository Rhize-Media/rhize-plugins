import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

vi.mock("@/lib/neo4j/queries", () => ({
  runCypher: vi.fn().mockResolvedValue([{ count: 5 }]),
}));

import { POST } from "@/app/api/graph/query/route";
import { runCypher } from "@/lib/neo4j/queries";

function mockRequest(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request("http://localhost/api/graph/query", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
  });
}

describe("POST /api/graph/query", () => {
  const originalSecret = process.env.GRAPH_QUERY_SECRET;

  beforeEach(() => {
    vi.clearAllMocks();
    process.env.GRAPH_QUERY_SECRET = "test-secret";
  });

  afterEach(() => {
    if (originalSecret === undefined) {
      delete process.env.GRAPH_QUERY_SECRET;
    } else {
      process.env.GRAPH_QUERY_SECRET = originalSecret;
    }
  });

  it("returns 503 when GRAPH_QUERY_SECRET is not configured", async () => {
    delete process.env.GRAPH_QUERY_SECRET;
    const res = await POST(
      mockRequest({ query: "MATCH (n) RETURN n" }) as never
    );
    expect(res.status).toBe(503);
    expect(runCypher).not.toHaveBeenCalled();
  });

  it("returns 401 when no secret header is provided", async () => {
    const res = await POST(
      mockRequest({ query: "MATCH (n) RETURN n" }) as never
    );
    expect(res.status).toBe(401);
    expect(runCypher).not.toHaveBeenCalled();
  });

  it("returns 401 when wrong secret is provided", async () => {
    const res = await POST(
      mockRequest(
        { query: "MATCH (n) RETURN n" },
        { "x-graph-secret": "wrong" }
      ) as never
    );
    expect(res.status).toBe(401);
    expect(runCypher).not.toHaveBeenCalled();
  });

  it("returns 400 when query is missing with correct secret", async () => {
    const res = await POST(
      mockRequest({}, { "x-graph-secret": "test-secret" }) as never
    );
    expect(res.status).toBe(400);
  });

  it("executes query and returns results with correct secret", async () => {
    const res = await POST(
      mockRequest(
        { query: "MATCH (s:PipelineStage) RETURN count(s) AS count" },
        { "x-graph-secret": "test-secret" }
      ) as never
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.results).toEqual([{ count: 5 }]);
    expect(runCypher).toHaveBeenCalledWith(
      "MATCH (s:PipelineStage) RETURN count(s) AS count",
      {}
    );
  });

  it("passes params through to runCypher", async () => {
    await POST(
      mockRequest(
        { query: "MATCH (c {id: $id}) RETURN c", params: { id: "abc" } },
        { "x-graph-secret": "test-secret" }
      ) as never
    );
    expect(runCypher).toHaveBeenCalledWith(
      "MATCH (c {id: $id}) RETURN c",
      { id: "abc" }
    );
  });
});
