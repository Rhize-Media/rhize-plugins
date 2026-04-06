import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  clusterKeywords,
  classifyIntentAI,
  classifyIntentRegex,
  nameCluster,
} from "@/lib/ai/clustering";

// ---------------------------------------------------------------------------
// Mock Claude AI client — prevent real API calls
// ---------------------------------------------------------------------------

vi.mock("@/lib/ai/claude", () => ({
  generateStructured: vi.fn(),
}));

import { generateStructured } from "@/lib/ai/claude";
const mockGenerateStructured = generateStructured as ReturnType<typeof vi.fn>;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("clusterKeywords", () => {
  beforeEach(() => vi.clearAllMocks());

  it("puts all in cluster 0 when fewer than 5 keywords", () => {
    const keywords = [
      { term: "running shoes", embedding: [1, 0, 0] },
      { term: "trail running", embedding: [0, 1, 0] },
      { term: "marathon training", embedding: [0, 0, 1] },
    ];

    const result = clusterKeywords(keywords);

    expect(result).toHaveLength(3);
    for (const assignment of result) {
      expect(assignment.clusterId).toBe(0);
    }
  });

  it("assigns keywords to multiple clusters", () => {
    // 3 tight groups with small noise to ensure separation
    const groupA = [
      { term: "a1", embedding: [1, 0, 0] },
      { term: "a2", embedding: [0.99, 0.01, 0] },
      { term: "a3", embedding: [0.98, 0.02, 0] },
    ];
    const groupB = [
      { term: "b1", embedding: [0, 1, 0] },
      { term: "b2", embedding: [0.01, 0.99, 0] },
      { term: "b3", embedding: [0.02, 0.98, 0] },
    ];
    const groupC = [
      { term: "c1", embedding: [0, 0, 1] },
      { term: "c2", embedding: [0, 0.01, 0.99] },
      { term: "c3", embedding: [0, 0.02, 0.98] },
    ];

    const result = clusterKeywords([...groupA, ...groupB, ...groupC]);

    const distinctClusters = new Set(result.map((r) => r.clusterId));
    expect(distinctClusters.size).toBeGreaterThanOrEqual(2);
  });

  it("returns assignment for every input keyword", () => {
    const keywords = Array.from({ length: 10 }, (_, i) => ({
      term: `kw-${i}`,
      embedding: Array.from({ length: 5 }, () => Math.random()),
    }));

    const result = clusterKeywords(keywords);

    expect(result).toHaveLength(10);
    for (const assignment of result) {
      expect(assignment).toHaveProperty("term");
      expect(assignment).toHaveProperty("clusterId");
    }
  });
});

describe("classifyIntentRegex", () => {
  beforeEach(() => vi.clearAllMocks());

  it("classifies transactional keywords", () => {
    expect(classifyIntentRegex("buy shoes online")).toBe("transactional");
  });

  it("classifies commercial keywords", () => {
    expect(classifyIntentRegex("best laptop 2026")).toBe("commercial");
  });

  it("classifies navigational keywords", () => {
    expect(classifyIntentRegex("github login")).toBe("navigational");
  });

  it("classifies informational keywords", () => {
    expect(classifyIntentRegex("how to learn python")).toBe("informational");
  });

  it("defaults to informational", () => {
    expect(classifyIntentRegex("random keyword")).toBe("informational");
  });
});

describe("classifyIntentAI", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns AI classifications", async () => {
    mockGenerateStructured.mockResolvedValue({
      data: {
        classifications: [
          { term: "buy shoes", intent: "transactional" },
        ],
      },
    });

    const result = await classifyIntentAI(["buy shoes"]);

    expect(result.get("buy shoes")).toBe("transactional");
    expect(mockGenerateStructured).toHaveBeenCalledOnce();
  });

  it("falls back to regex on API error", async () => {
    mockGenerateStructured.mockRejectedValue(new Error("API error"));

    const result = await classifyIntentAI(["buy shoes", "how to cook"]);

    expect(result.size).toBe(2);
    expect(result.get("buy shoes")).toBe("transactional");
    expect(result.get("how to cook")).toBe("informational");
  });
});

describe("nameCluster", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns AI-generated name", async () => {
    mockGenerateStructured.mockResolvedValue({
      data: { name: "Running Gear", pillarTopic: "Running" },
    });

    const result = await nameCluster(["running shoes", "trail running", "run"]);

    expect(result.name).toBe("Running Gear");
    expect(result.pillarTopic).toBe("Running");
    expect(mockGenerateStructured).toHaveBeenCalledOnce();
  });

  it("falls back to shortest keyword on error", async () => {
    mockGenerateStructured.mockRejectedValue(new Error("API error"));

    const result = await nameCluster(["running shoes", "run"]);

    expect(result.name).toBe("run");
    expect(result.pillarTopic).toBe("run");
  });
});
