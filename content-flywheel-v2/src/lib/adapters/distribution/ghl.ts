import type { DistributionAdapter, SocialPost, PostResult } from "@/types";

function getGHLConfig() {
  const apiKey = process.env.GHL_API_KEY;
  const locationId = process.env.GHL_LOCATION_ID;

  if (!apiKey || !locationId) {
    throw new Error(
      "Missing GoHighLevel credentials. Set GHL_API_KEY and GHL_LOCATION_ID."
    );
  }

  return { apiKey, locationId };
}

async function ghlFetch(
  path: string,
  options: RequestInit = {}
): Promise<Response> {
  const { apiKey } = getGHLConfig();
  return fetch(`https://services.leadconnectorhq.com${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      Version: "2021-07-28",
      ...options.headers,
    },
  });
}

export const ghlAdapter: DistributionAdapter = {
  async schedulePost(
    content: SocialPost,
    scheduledAt: Date
  ): Promise<PostResult> {
    const { locationId } = getGHLConfig();

    const res = await ghlFetch("/social-media-posting/post", {
      method: "POST",
      body: JSON.stringify({
        locationId,
        type: "post",
        accountIds: [content.platform],
        summary: content.text,
        mediaUrls: content.mediaUrls ?? [],
        scheduledAt: scheduledAt.toISOString(),
      }),
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`GHL post failed (${res.status}): ${body}`);
    }

    const data = await res.json();
    return {
      id: data.id ?? data.postId ?? "unknown",
      platform: content.platform,
      status: "scheduled",
      scheduledAt: scheduledAt.toISOString(),
    };
  },

  async getPostStatus(
    id: string
  ): Promise<"scheduled" | "posted" | "failed"> {
    const res = await ghlFetch(`/social-media-posting/post/${id}`);
    if (!res.ok) return "failed";
    const data = await res.json();
    return data.status ?? "scheduled";
  },

  async listPlatforms(): Promise<string[]> {
    const { locationId } = getGHLConfig();
    const res = await ghlFetch(
      `/social-media-posting/oauth/accounts?locationId=${locationId}`
    );
    if (!res.ok) return [];
    const data = await res.json();
    return (data.accounts ?? []).map(
      (a: { platform: string }) => a.platform
    );
  },
};
