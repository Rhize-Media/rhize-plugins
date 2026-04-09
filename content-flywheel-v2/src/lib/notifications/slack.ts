// ---------------------------------------------------------------------------
// Slack notification module — lightweight chat.postMessage via fetch
// ---------------------------------------------------------------------------

interface SlackResult {
  ok: boolean;
  error?: string;
}

/**
 * Post a message to Slack using the Web API `chat.postMessage` endpoint.
 *
 * Gracefully no-ops when `SLACK_BOT_TOKEN` or `SLACK_CHANNEL_ID` env vars
 * are not set — logs a debug message and returns `{ ok: true }`.
 *
 * @param text    - The message text to send
 * @param channel - Optional channel override (defaults to `SLACK_CHANNEL_ID`)
 */
export async function sendSlackMessage(
  text: string,
  channel?: string,
): Promise<SlackResult> {
  const token = process.env.SLACK_BOT_TOKEN;
  const targetChannel = channel ?? process.env.SLACK_CHANNEL_ID;

  if (!token || !targetChannel) {
    console.debug(
      "[slack] Skipping notification — SLACK_BOT_TOKEN or SLACK_CHANNEL_ID not set",
    );
    return { ok: true };
  }

  try {
    const res = await fetch("https://slack.com/api/chat.postMessage", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ channel: targetChannel, text }),
    });

    const data = (await res.json()) as { ok: boolean; error?: string };

    if (!data.ok) {
      return { ok: false, error: data.error ?? "Unknown Slack API error" };
    }

    return { ok: true };
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return { ok: false, error: message };
  }
}
