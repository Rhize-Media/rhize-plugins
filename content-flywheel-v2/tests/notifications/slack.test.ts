import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { sendSlackMessage } from "@/lib/notifications/slack";

// ---------------------------------------------------------------------------
// Mock global fetch
// ---------------------------------------------------------------------------

const ORIGINAL_FETCH = globalThis.fetch;

function mockFetch(response: unknown, ok = true) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok,
    json: async () => response,
  });
  globalThis.fetch = fetchMock as unknown as typeof fetch;
  return fetchMock;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("sendSlackMessage", () => {
  beforeEach(() => {
    process.env.SLACK_BOT_TOKEN = "xoxb-test-token";
    process.env.SLACK_CHANNEL_ID = "C1234567890";
  });

  afterEach(() => {
    globalThis.fetch = ORIGINAL_FETCH;
    delete process.env.SLACK_BOT_TOKEN;
    delete process.env.SLACK_CHANNEL_ID;
    vi.restoreAllMocks();
  });

  it("sends message when env vars are set", async () => {
    const fetchMock = mockFetch({ ok: true });

    const result = await sendSlackMessage("Hello from tests");

    expect(result).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledOnce();

    const [url, options] = fetchMock.mock.calls[0];
    expect(url).toBe("https://slack.com/api/chat.postMessage");
    expect(options.method).toBe("POST");
    expect(options.headers.Authorization).toBe("Bearer xoxb-test-token");
    expect(options.headers["Content-Type"]).toBe("application/json");

    const body = JSON.parse(options.body);
    expect(body.channel).toBe("C1234567890");
    expect(body.text).toBe("Hello from tests");
  });

  it("no-ops silently when SLACK_BOT_TOKEN is missing", async () => {
    delete process.env.SLACK_BOT_TOKEN;
    const fetchMock = mockFetch({ ok: true });
    const debugSpy = vi.spyOn(console, "debug").mockImplementation(() => {});

    const result = await sendSlackMessage("Should not send");

    expect(result).toEqual({ ok: true });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(debugSpy).toHaveBeenCalledWith(
      expect.stringContaining("Skipping notification"),
    );
  });

  it("no-ops silently when SLACK_CHANNEL_ID is missing", async () => {
    delete process.env.SLACK_CHANNEL_ID;
    const fetchMock = mockFetch({ ok: true });

    const result = await sendSlackMessage("Should not send");

    expect(result).toEqual({ ok: true });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("handles fetch errors gracefully", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(
      new Error("Network failure"),
    ) as unknown as typeof fetch;

    const result = await sendSlackMessage("Will fail");

    expect(result).toEqual({ ok: false, error: "Network failure" });
  });

  it("handles non-Error fetch rejections", async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(
      "string error",
    ) as unknown as typeof fetch;

    const result = await sendSlackMessage("Will fail");

    expect(result).toEqual({ ok: false, error: "Unknown error" });
  });

  it("returns error when Slack API responds with ok: false", async () => {
    mockFetch({ ok: false, error: "channel_not_found" });

    const result = await sendSlackMessage("Bad channel");

    expect(result).toEqual({ ok: false, error: "channel_not_found" });
  });

  it("uses custom channel when provided", async () => {
    const fetchMock = mockFetch({ ok: true });

    await sendSlackMessage("Custom channel msg", "C9999999999");

    const body = JSON.parse(fetchMock.mock.calls[0][1].body);
    expect(body.channel).toBe("C9999999999");
  });
});
