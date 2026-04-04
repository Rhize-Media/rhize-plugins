import { runCypher } from "@/lib/neo4j/queries";
import { onPageTaskPost, onPageSummary, onPagePages } from "@/lib/dataforseo/client";
import type { SEOScore, WorkflowRun } from "@/types";

interface ContentOptimizeInput {
  contentId: string;
  url: string;
  primaryKeyword?: string;
  locationCode?: number;
  languageCode?: string;
}

interface ContentOptimizeResult {
  workflowRun: WorkflowRun;
  seoScore: SEOScore;
}

export async function runContentOptimize(
  input: ContentOptimizeInput
): Promise<ContentOptimizeResult> {
  const { contentId, url, primaryKeyword } = input;

  // Create workflow run node
  const runResult = await runCypher(
    `CREATE (w:WorkflowRun {
      id: randomUUID(), type: "content-optimize",
      contentId: $contentId, status: "running",
      startedAt: datetime()
    }) RETURN w.id AS runId`,
    { contentId }
  );
  const runId = runResult[0].runId as string;

  try {
    // 1. Start on-page crawl via DataForSEO
    const crawlRes = await onPageTaskPost(url).catch(() => null);
    const taskId = crawlRes?.tasks?.[0]?.id;

    let pageData: Record<string, unknown> | null = null;

    if (taskId) {
      // Wait briefly for crawl to complete, then fetch results
      await delay(5000);

      const summaryRes = await onPageSummary(taskId).catch(() => null);
      const pagesRes = await onPagePages(taskId).catch(() => null);

      const pages = pagesRes?.tasks?.[0]?.result?.[0]?.items ?? [];
      pageData = pages.find(
        (p: Record<string, unknown>) => (p.url as string) === url || (p.url as string) === url + "/"
      ) ?? pages[0] ?? null;

      // Merge crawl summary data if available
      if (summaryRes?.tasks?.[0]?.result?.[0]) {
        const summary = summaryRes.tasks[0].result[0];
        pageData = { ...pageData, _crawlSummary: summary };
      }
    }

    // 2. Score each SEO dimension
    const titleScore = scoreTitleTag(pageData, primaryKeyword);
    const metaScore = scoreMetaDescription(pageData, primaryKeyword);
    const headingScore = scoreHeadingStructure(pageData, primaryKeyword);
    const eeatScore = scoreEEAT(pageData);
    const internalLinkScore = scoreInternalLinks(pageData);
    const structuredDataScore = scoreStructuredData(pageData);
    const wordCount = extractWordCount(pageData);

    // 3. Calculate overall score (weighted average)
    const overall = Math.round(
      titleScore * 0.15 +
      metaScore * 0.15 +
      headingScore * 0.20 +
      eeatScore * 0.20 +
      internalLinkScore * 0.15 +
      structuredDataScore * 0.15
    );

    // 4. Generate recommendations
    const recommendations = generateRecommendations({
      titleScore,
      metaScore,
      headingScore,
      eeatScore,
      internalLinkScore,
      structuredDataScore,
      wordCount,
      pageData,
      primaryKeyword,
    });

    // 5. Persist SEO score to Neo4j
    await runCypher(
      `MATCH (c:ContentPiece {id: $contentId})
       CREATE (s:SEOScore {
         id: randomUUID(),
         overall: $overall,
         titleScore: $titleScore,
         metaScore: $metaScore,
         headingScore: $headingScore,
         eeatScore: $eeatScore,
         internalLinkScore: $internalLinkScore,
         structuredDataScore: $structuredDataScore,
         wordCount: $wordCount,
         recommendations: $recommendations,
         date: datetime()
       })
       CREATE (c)-[:HAS_SCORE]->(s)`,
      {
        contentId,
        overall,
        titleScore,
        metaScore,
        headingScore,
        eeatScore,
        internalLinkScore,
        structuredDataScore,
        wordCount,
        recommendations,
      }
    );

    // 6. If content is in draft/optimize stage, check if it should advance
    if (overall >= 80) {
      await runCypher(
        `MATCH (c:ContentPiece {id: $contentId})
         WHERE c.stage IN ["draft", "optimize"]
         MATCH (s:PipelineStage {name: "review"})
         SET c.stage = "review", c.updatedAt = datetime()
         MERGE (c)-[:IN_STAGE]->(s)`,
        { contentId }
      );
    }

    // 7. Mark workflow complete
    const summary = `SEO Score: ${overall}/100 (Title: ${titleScore}, Meta: ${metaScore}, Headings: ${headingScore}, E-E-A-T: ${eeatScore}, Links: ${internalLinkScore}, Schema: ${structuredDataScore}). ${recommendations.length} recommendations.`;

    await runCypher(
      `MATCH (w:WorkflowRun {id: $runId})
       SET w.status = "completed", w.completedAt = datetime(), w.summary = $summary`,
      { runId, summary }
    );

    const seoScore: SEOScore = {
      id: "", // assigned by Neo4j
      contentId,
      overall,
      titleScore,
      metaScore,
      headingScore,
      eeatScore,
      internalLinkScore,
      structuredDataScore,
      wordCount,
      recommendations,
      date: new Date().toISOString(),
    };

    return {
      workflowRun: {
        id: runId,
        type: "content-optimize",
        contentId,
        status: "completed",
        startedAt: new Date().toISOString(),
        summary,
      },
      seoScore,
    };
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    await runCypher(
      `MATCH (w:WorkflowRun {id: $runId})
       SET w.status = "failed", w.completedAt = datetime(), w.error = $error`,
      { runId, error: message }
    );
    throw error;
  }
}

// ── Scoring Functions ──────────────────────────────────────

function scoreTitleTag(page: Record<string, unknown> | null, keyword?: string): number {
  if (!page) return 0;

  const meta = page.meta as Record<string, unknown> | undefined;
  const title = (meta?.title as string) ?? "";
  if (!title) return 0;

  let score = 40; // base for having a title

  // Length check: 50-60 chars ideal
  if (title.length >= 50 && title.length <= 60) score += 30;
  else if (title.length >= 40 && title.length <= 70) score += 15;

  // Keyword presence
  if (keyword && title.toLowerCase().includes(keyword.toLowerCase())) {
    score += 20;
    // Front-loaded bonus
    if (title.toLowerCase().indexOf(keyword.toLowerCase()) < 20) score += 10;
  } else if (!keyword) {
    score += 15; // no keyword to check, partial credit
  }

  return Math.min(score, 100);
}

function scoreMetaDescription(page: Record<string, unknown> | null, keyword?: string): number {
  if (!page) return 0;

  const meta = page.meta as Record<string, unknown> | undefined;
  const description = (meta?.description as string) ?? "";
  if (!description) return 0;

  let score = 30;

  // Length: 150-160 chars
  if (description.length >= 150 && description.length <= 160) score += 35;
  else if (description.length >= 120 && description.length <= 180) score += 20;
  else if (description.length > 0) score += 10;

  // Keyword presence
  if (keyword && description.toLowerCase().includes(keyword.toLowerCase())) {
    score += 20;
  } else if (!keyword) {
    score += 10;
  }

  // CTA signals
  if (/\b(learn|discover|get|find|try|start|compare|see|read)\b/i.test(description)) {
    score += 15;
  }

  return Math.min(score, 100);
}

function scoreHeadingStructure(page: Record<string, unknown> | null, _keyword?: string): number {
  if (!page) return 0;

  const onPage = page.on_page as Record<string, unknown> | undefined;
  const h1Count = (onPage?.h1_count as number) ?? 0;
  const h2Count = (onPage?.h2_count as number) ?? 0;
  const h3Count = (onPage?.h3_count as number) ?? 0;

  let score = 0;

  // Exactly one H1
  if (h1Count === 1) score += 40;
  else if (h1Count > 1) score += 10;

  // Has H2 sections
  if (h2Count >= 2) score += 30;
  else if (h2Count === 1) score += 15;

  // Has H3 subsections
  if (h3Count >= 2) score += 15;
  else if (h3Count >= 1) score += 10;

  // Logical depth (not just H1 + H2, uses hierarchy)
  if (h2Count > 0 && h3Count > 0) score += 15;

  return Math.min(score, 100);
}

function scoreEEAT(page: Record<string, unknown> | null): number {
  if (!page) return 0;

  let score = 20; // base

  const onPage = page.on_page as Record<string, unknown> | undefined;

  // Content depth (word count proxy)
  const wordCount = (onPage?.content_word_count as number) ?? 0;
  if (wordCount >= 2000) score += 20;
  else if (wordCount >= 1000) score += 10;

  // External links (citations to authoritative sources)
  const externalLinks = (onPage?.external_links_count as number) ?? 0;
  if (externalLinks >= 3) score += 20;
  else if (externalLinks >= 1) score += 10;

  // Images (shows evidence, experience)
  const imageCount = (onPage?.images_count as number) ?? 0;
  if (imageCount >= 3) score += 15;
  else if (imageCount >= 1) score += 10;

  // Structured data present (Author/Organization)
  const hasSchema = page.has_microdata as boolean | undefined;
  if (hasSchema) score += 15;

  // HTTPS
  const isHttps = (page.url as string)?.startsWith("https") ?? false;
  if (isHttps) score += 10;

  return Math.min(score, 100);
}

function scoreInternalLinks(page: Record<string, unknown> | null): number {
  if (!page) return 0;

  const onPage = page.on_page as Record<string, unknown> | undefined;
  const internalLinks = (onPage?.internal_links_count as number) ?? 0;
  const wordCount = (onPage?.content_word_count as number) ?? 0;

  if (internalLinks === 0) return 10;

  // Target: 3-5 links per 1,000 words
  const per1k = wordCount > 0 ? (internalLinks / wordCount) * 1000 : 0;

  if (per1k >= 3 && per1k <= 5) return 100;
  if (per1k >= 2 && per1k <= 7) return 75;
  if (per1k >= 1) return 50;
  return 30;
}

function scoreStructuredData(page: Record<string, unknown> | null): number {
  if (!page) return 0;

  let score = 0;

  const hasSchema = page.has_microdata as boolean | undefined;
  const hasJsonLd = page.has_json_ld as boolean | undefined;

  if (hasJsonLd) score += 60;
  else if (hasSchema) score += 40;

  // Open Graph tags
  const meta = page.meta as Record<string, unknown> | undefined;
  const ogTitle = meta?.og_title as string | undefined;
  const ogDescription = meta?.og_description as string | undefined;
  const ogImage = meta?.og_image as string | undefined;

  if (ogTitle) score += 15;
  if (ogDescription) score += 10;
  if (ogImage) score += 15;

  return Math.min(score, 100);
}

function extractWordCount(page: Record<string, unknown> | null): number {
  if (!page) return 0;
  const onPage = page.on_page as Record<string, unknown> | undefined;
  return (onPage?.content_word_count as number) ?? 0;
}

// ── Recommendations ────────────────────────────────────────

interface ScoreContext {
  titleScore: number;
  metaScore: number;
  headingScore: number;
  eeatScore: number;
  internalLinkScore: number;
  structuredDataScore: number;
  wordCount: number;
  pageData: Record<string, unknown> | null;
  primaryKeyword?: string;
}

function generateRecommendations(ctx: ScoreContext): string[] {
  const recs: string[] = [];

  if (ctx.titleScore < 70) {
    recs.push("Optimize title tag: aim for 50-60 characters with primary keyword front-loaded.");
  }
  if (ctx.metaScore < 70) {
    recs.push("Improve meta description: 150-160 characters with keyword and clear CTA.");
  }
  if (ctx.headingScore < 70) {
    recs.push("Fix heading structure: ensure exactly one H1 with logical H2/H3 hierarchy.");
  }
  if (ctx.eeatScore < 60) {
    recs.push("Strengthen E-E-A-T signals: add author bio, cite authoritative sources, include original data or case studies.");
  }
  if (ctx.internalLinkScore < 70) {
    recs.push("Add internal links: target 3-5 contextual links per 1,000 words with descriptive anchor text.");
  }
  if (ctx.structuredDataScore < 50) {
    recs.push("Add structured data: implement JSON-LD schema (Article, FAQPage, or HowTo) and Open Graph tags.");
  }
  if (ctx.wordCount < 1000) {
    recs.push(`Content is thin at ${ctx.wordCount} words. Expand to at least 1,500 words for informational content.`);
  }
  if (ctx.primaryKeyword && ctx.titleScore < 80) {
    recs.push(`Ensure primary keyword "${ctx.primaryKeyword}" appears in title, H1, meta description, and first paragraph.`);
  }

  return recs;
}

// ── Helpers ────────────────────────────────────────────────

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
