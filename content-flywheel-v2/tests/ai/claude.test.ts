import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import Anthropic from "@anthropic-ai/sdk";
import { calculateCost, _setClient, generateText, generateStructured } from "@/lib/ai/claude";

// ---------------------------------------------------------------------------
// Mock Neo4j driver — prevent real DB calls
// ---------------------------------------------------------------------------

const mockRun = vi.fn().mockResolvedValue({ records: [] });
const mockClose = vi.fn().mockResolvedValue(undefined);

vi.mock("@/lib/neo4j/driver", () => ({
  getDriver: () => ({
    session: () => ({ run: mockRun, close: mockClose }),
  }),
}));

// ---------------------------------------------------------------------------
// Mock Anthropic client factory
// ---------------------------------------------------------------------------

interface MockMessages {
  create: ReturnType<typeof vi.fn>;
  parse: ReturnType<typeof vi.fn>;
}

function makeMockUsage(overrides?: Partial<Record<string, number | null>>) {
  return {
    input_tokens: 100,
    output_tokens: 50,
    cache_creation_input_tokens: 0,
    cache_read_input_tokens: 0,
    cache_creation: null,
    inference_geo: null,
    ...overrides,
  };
}

function makeMockClient(responseOverrides?: Record<string, unknown>): { client: Anthropic; messages: MockMessages } {
  const defaultResponse = {
    id: "msg_test",
    type: "message",
    role: "assistant",
    model: "claude-haiku-4-5-20251001",
    content: [{ type: "text", text: "Hello world" }],
    stop_reason: "end_turn",
    usage: makeMockUsage(),
    ...responseOverrides,
  };

  const messages: MockMessages = {
    create: vi.fn().mockResolvedValue(defaultResponse),
    parse: vi.fn().mockResolvedValue({
      ...defaultResponse,
      parsed_output: { answer: 42 },
    }),
  };

  return {
    client: { messages } as unknown as Anthropic,
    messages,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("calculateCost", () => {
  it("calculates Haiku cost correctly", () => {
    const cost = calculateCost("claude-haiku-4-5-20251001", {
      input_tokens: 1_000_000,
      output_tokens: 1_000_000,
      cache_creation_input_tokens: 0,
      cache_read_input_tokens: 0,
    });
    // Haiku: $0.80/M input + $4.00/M output = $4.80
    expect(cost).toBeCloseTo(4.80, 2);
  });

  it("calculates Sonnet cost correctly", () => {
    const cost = calculateCost("claude-sonnet-4-5-20250929", {
      input_tokens: 1_000_000,
      output_tokens: 1_000_000,
      cache_creation_input_tokens: 0,
      cache_read_input_tokens: 0,
    });
    // Sonnet: $3.00/M input + $15.00/M output = $18.00
    expect(cost).toBeCloseTo(18.0, 2);
  });

  it("accounts for cache pricing", () => {
    const cost = calculateCost("claude-haiku-4-5-20251001", {
      input_tokens: 500_000,
      output_tokens: 100_000,
      cache_creation_input_tokens: 200_000,
      cache_read_input_tokens: 300_000,
    });
    // Regular input = 500k - 300k cache_read = 200k
    // (200k/1M)*0.80 + (100k/1M)*4.00 + (200k/1M)*1.00 + (300k/1M)*0.08
    // = 0.16 + 0.40 + 0.20 + 0.024 = 0.784
    expect(cost).toBeCloseTo(0.784, 3);
  });

  it("returns 0 for unknown model", () => {
    const cost = calculateCost("unknown-model", {
      input_tokens: 1000,
      output_tokens: 1000,
    });
    expect(cost).toBe(0);
  });

  it("handles undefined cache fields", () => {
    const cost = calculateCost("claude-haiku-4-5-20251001", {
      input_tokens: 1000,
      output_tokens: 500,
    });
    // (1000/1M)*0.80 + (500/1M)*4.00 = 0.0008 + 0.002 = 0.0028
    expect(cost).toBeCloseTo(0.0028, 4);
  });
});

describe("generateText", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRun.mockResolvedValue({ records: [] });
  });

  afterEach(() => {
    _setClient(null);
  });

  it("returns text and usage from Claude response", async () => {
    const { client, messages } = makeMockClient();
    _setClient(client);

    const result = await generateText({
      system: "You are helpful.",
      messages: [{ role: "user", content: "Hi" }],
    });

    expect(result.text).toBe("Hello world");
    expect(result.usage.inputTokens).toBe(100);
    expect(result.usage.outputTokens).toBe(50);
    expect(result.usage.cost).toBeGreaterThan(0);
    expect(messages.create).toHaveBeenCalledOnce();
  });

  it("defaults to haiku model", async () => {
    const { client, messages } = makeMockClient();
    _setClient(client);

    await generateText({
      system: "Test",
      messages: [{ role: "user", content: "Hi" }],
    });

    expect(messages.create.mock.calls[0][0].model).toBe("claude-haiku-4-5-20251001");
  });

  it("uses sonnet when specified", async () => {
    const { client, messages } = makeMockClient();
    _setClient(client);

    await generateText({
      model: "sonnet",
      system: "Test",
      messages: [{ role: "user", content: "Hi" }],
    });

    expect(messages.create.mock.calls[0][0].model).toBe("claude-sonnet-4-5-20250929");
  });

  it("records usage to Neo4j", async () => {
    const { client } = makeMockClient();
    _setClient(client);

    await generateText({
      system: "Test",
      messages: [{ role: "user", content: "Hi" }],
      contentId: "content-123",
    });

    expect(mockRun).toHaveBeenCalledOnce();
    const cypherCall = mockRun.mock.calls[0];
    expect(cypherCall[0]).toContain("CREATE (a:AIUsage");
    expect(cypherCall[1].contentId).toBe("content-123");
  });

  it("passes cache_control system messages through", async () => {
    const { client, messages } = makeMockClient();
    _setClient(client);

    await generateText({
      system: [
        { type: "text", text: "You are helpful.", cache_control: { type: "ephemeral" } },
      ],
      messages: [{ role: "user", content: "Hi" }],
    });

    const systemArg = messages.create.mock.calls[0][0].system;
    expect(systemArg[0].cache_control).toEqual({ type: "ephemeral" });
  });

  it("handles cache metrics in usage", async () => {
    const { client } = makeMockClient({
      usage: makeMockUsage({
        cache_creation_input_tokens: 500,
        cache_read_input_tokens: 300,
      }),
    });
    _setClient(client);

    const result = await generateText({
      system: "Test",
      messages: [{ role: "user", content: "Hi" }],
    });

    expect(result.usage.cacheCreationInputTokens).toBe(500);
    expect(result.usage.cacheReadInputTokens).toBe(300);
  });
});

describe("generateStructured", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockRun.mockResolvedValue({ records: [] });
  });

  afterEach(() => {
    _setClient(null);
  });

  it("returns parsed data and usage", async () => {
    const { z } = await import("zod");
    const schema = z.object({ answer: z.number() });

    const { client } = makeMockClient();
    _setClient(client);

    const result = await generateStructured({
      system: "Return JSON",
      messages: [{ role: "user", content: "What is 6*7?" }],
      schema,
    });

    expect(result.data).toEqual({ answer: 42 });
    expect(result.usage.inputTokens).toBe(100);
  });

  it("uses lower temperature by default", async () => {
    const { z } = await import("zod");
    const schema = z.object({ answer: z.number() });

    const { client, messages } = makeMockClient();
    _setClient(client);

    await generateStructured({
      system: "Return JSON",
      messages: [{ role: "user", content: "Test" }],
      schema,
    });

    expect(messages.parse.mock.calls[0][0].temperature).toBe(0.3);
  });
});
