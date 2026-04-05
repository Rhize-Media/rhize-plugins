import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  keywordSuggestions,
  serpLive,
  backlinksSummary,
  competitorDomains,
} from "@/lib/dataforseo/client";

const ORIGINAL_FETCH = globalThis.fetch;

describe("DataForSEO client", () => {
  beforeEach(() => {
    process.env.DATAFORSEO_USERNAME = "test@example.com";
    process.env.DATAFORSEO_PASSWORD = "testpass";
  });

  afterEach(() => {
    globalThis.fetch = ORIGINAL_FETCH;
    vi.restoreAllMocks();
  });

  function mockFetch(response: unknown, ok = true, status = 200) {
    const fetchMock = vi.fn().mockResolvedValue({
      ok,
      status,
      json: async () => response,
      text: async () => JSON.stringify(response),
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;
    return fetchMock;
  }

  it("throws when credentials missing", async () => {
    delete process.env.DATAFORSEO_USERNAME;
    delete process.env.DATAFORSEO_PASSWORD;
    await expect(keywordSuggestions(["test"])).rejects.toThrow(
      /Missing DataForSEO credentials/
    );
  });

  it("sends Basic auth header with base64 credentials", async () => {
    const fetchMock = mockFetch({ tasks: [] });
    await keywordSuggestions(["test"]);
    const expected = Buffer.from("test@example.com:testpass").toString("base64");
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers.Authorization).toBe(`Basic ${expected}`);
  });

  it("keywordSuggestions posts to correct endpoint with payload", async () => {
    const fetchMock = mockFetch({ tasks: [{ result: [{ items: [] }] }] });
    await keywordSuggestions(["flywheel", "content"], 2840, "en");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain(
      "/keywords_data/google_ads/keywords_for_keywords/live"
    );
    expect(options.method).toBe("POST");
    const body = JSON.parse(options.body);
    expect(body).toEqual([
      { keywords: ["flywheel", "content"], location_code: 2840, language_code: "en" },
    ]);
  });

  it("serpLive posts to correct endpoint", async () => {
    const fetchMock = mockFetch({ tasks: [] });
    await serpLive("content flywheel");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/serp/google/organic/live/regular");
    const body = JSON.parse(options.body);
    expect(body[0].keyword).toBe("content flywheel");
  });

  it("backlinksSummary posts correct target", async () => {
    const fetchMock = mockFetch({ tasks: [] });
    await backlinksSummary("rhize.media");
    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toContain("/backlinks/summary/live");
    const body = JSON.parse(options.body);
    expect(body[0].target).toBe("rhize.media");
  });

  it("competitorDomains uses dataforseo_labs endpoint", async () => {
    const fetchMock = mockFetch({ tasks: [] });
    await competitorDomains("example.com");
    const [url] = fetchMock.mock.calls[0];
    expect(url).toContain("/dataforseo_labs/google/competitors_domain/live");
  });

  it("throws on non-OK response with status and body", async () => {
    mockFetch({ error: "bad request" }, false, 400);
    await expect(keywordSuggestions(["x"])).rejects.toThrow(/400/);
  });

  it("uses default US location and English language", async () => {
    const fetchMock = mockFetch({ tasks: [] });
    await keywordSuggestions(["test"]);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body[0].location_code).toBe(2840);
    expect(body[0].language_code).toBe("en");
  });
});
