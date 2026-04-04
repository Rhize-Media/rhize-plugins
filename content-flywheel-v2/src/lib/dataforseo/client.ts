const BASE_URL = "https://api.dataforseo.com/v3";

function getAuth(): string {
  const username = process.env.DATAFORSEO_USERNAME;
  const password = process.env.DATAFORSEO_PASSWORD;
  if (!username || !password) {
    throw new Error(
      "Missing DataForSEO credentials. Set DATAFORSEO_USERNAME and DATAFORSEO_PASSWORD."
    );
  }
  return Buffer.from(`${username}:${password}`).toString("base64");
}

async function apiCall<T>(
  path: string,
  body?: unknown
): Promise<T> {
  const auth = getAuth();
  const res = await fetch(`${BASE_URL}${path}`, {
    method: body ? "POST" : "GET",
    headers: {
      Authorization: `Basic ${auth}`,
      "Content-Type": "application/json",
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`DataForSEO ${path} failed (${res.status}): ${text}`);
  }

  return res.json() as Promise<T>;
}

// --- Keywords Data API ---

export async function keywordSuggestions(
  keywords: string[],
  locationCode = 2840,
  languageCode = "en"
) {
  return apiCall<DataForSEOResponse>("/keywords_data/google_ads/keywords_for_keywords/live", [
    { keywords, location_code: locationCode, language_code: languageCode },
  ]);
}

export async function relatedKeywords(
  keyword: string,
  locationCode = 2840,
  languageCode = "en"
) {
  return apiCall<DataForSEOResponse>("/dataforseo_labs/google/related_keywords/live", [
    { keyword, location_code: locationCode, language_code: languageCode },
  ]);
}

export async function keywordIdeas(
  keyword: string,
  locationCode = 2840,
  languageCode = "en"
) {
  return apiCall<DataForSEOResponse>("/dataforseo_labs/google/keyword_suggestions/live", [
    { keyword, location_code: locationCode, language_code: languageCode },
  ]);
}

// --- SERP API ---

export async function serpLive(
  keyword: string,
  locationCode = 2840,
  languageCode = "en"
) {
  return apiCall<DataForSEOResponse>("/serp/google/organic/live/regular", [
    { keyword, location_code: locationCode, language_code: languageCode },
  ]);
}

export async function serpLiveBatch(
  tasks: { keyword: string; url?: string; location_code?: number; language_code?: string }[]
) {
  return apiCall<DataForSEOResponse>(
    "/serp/google/organic/live/regular",
    tasks.map((t) => ({
      keyword: t.keyword,
      location_code: t.location_code ?? 2840,
      language_code: t.language_code ?? "en",
    }))
  );
}

// --- Labs API ---

export async function historicalRankOverview(
  domain: string,
  locationCode = 2840,
  languageCode = "en"
) {
  return apiCall<DataForSEOResponse>("/dataforseo_labs/google/historical_rank_overview/live", [
    { target: domain, location_code: locationCode, language_code: languageCode },
  ]);
}

export async function domainRankOverview(
  domain: string,
  locationCode = 2840,
  languageCode = "en"
) {
  return apiCall<DataForSEOResponse>("/dataforseo_labs/google/domain_rank_overview/live", [
    { target: domain, location_code: locationCode, language_code: languageCode },
  ]);
}

export async function competitorDomains(
  domain: string,
  locationCode = 2840,
  languageCode = "en"
) {
  return apiCall<DataForSEOResponse>("/dataforseo_labs/google/competitors_domain/live", [
    { target: domain, location_code: locationCode, language_code: languageCode },
  ]);
}

export async function keywordGap(
  targets: string[],
  locationCode = 2840,
  languageCode = "en"
) {
  return apiCall<DataForSEOResponse>("/dataforseo_labs/google/domain_intersection/live", [
    {
      targets: Object.fromEntries(targets.map((t, i) => [String(i + 1), t])),
      location_code: locationCode,
      language_code: languageCode,
    },
  ]);
}

// --- Backlinks API ---

export async function backlinksSummary(domain: string) {
  return apiCall<DataForSEOResponse>("/backlinks/summary/live", [
    { target: domain },
  ]);
}

export async function backlinksReferringDomains(domain: string, limit = 100) {
  return apiCall<DataForSEOResponse>("/backlinks/referring_domains/live", [
    { target: domain, limit },
  ]);
}

export async function backlinksAnchors(domain: string, limit = 100) {
  return apiCall<DataForSEOResponse>("/backlinks/anchors/live", [
    { target: domain, limit },
  ]);
}

export async function backlinksNewLost(
  domain: string,
  type: "new" | "lost" = "new"
) {
  const endpoint =
    type === "new"
      ? "/backlinks/history/live"
      : "/backlinks/history/live";
  return apiCall<DataForSEOResponse>(endpoint, [
    { target: domain, date_from: thirtyDaysAgo() },
  ]);
}

// --- AI Optimization ---

export async function aiOptimizationBrandMentions(
  brand: string,
  keywords: string[]
) {
  return apiCall<DataForSEOResponse>("/content_analysis/search/live", [
    {
      keyword: brand,
      search_mode: "as_is",
    },
  ]);
}

// --- OnPage API ---

export async function onPageTaskPost(domain: string) {
  return apiCall<DataForSEOResponse>("/on_page/task_post", [
    {
      target: domain,
      max_crawl_pages: 500,
      store_raw_html: false,
    },
  ]);
}

export async function onPageSummary(taskId: string) {
  return apiCall<DataForSEOResponse>(`/on_page/summary/${taskId}`);
}

export async function onPagePages(taskId: string, limit = 100) {
  return apiCall<DataForSEOResponse>("/on_page/pages", [
    { id: taskId, limit },
  ]);
}

// --- Types ---

interface DataForSEOResponse {
  version?: string;
  status_code?: number;
  status_message?: string;
  tasks?: DataForSEOTask[];
  tasks_count?: number;
  tasks_error?: number;
}

interface DataForSEOTask {
  id?: string;
  status_code?: number;
  status_message?: string;
  result?: DataForSEOResult[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

interface DataForSEOResult {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  items?: any[];
  total_count?: number;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  [key: string]: any;
}

export type { DataForSEOResponse, DataForSEOTask, DataForSEOResult };

// --- Helpers ---

function thirtyDaysAgo(): string {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return d.toISOString().split("T")[0];
}
