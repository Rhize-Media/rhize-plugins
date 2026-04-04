import { runCypher } from "@/lib/neo4j/queries";
import { onPageTaskPost, onPageSummary, onPagePages } from "@/lib/dataforseo/client";
import type { WorkflowRun } from "@/types";

interface SiteAuditInput {
  domain: string;
  maxPages?: number;
  locationCode?: number;
  languageCode?: string;
}

interface AuditIssue {
  severity: "critical" | "high" | "medium" | "low";
  category: string;
  description: string;
  affectedPages: number;
}

interface SiteAuditResult {
  workflowRun: WorkflowRun;
  totalPages: number;
  issues: AuditIssue[];
  contentOpportunities: ContentOpportunity[];
}

interface ContentOpportunity {
  url: string;
  title: string;
  issue: string;
  recommendation: string;
}

export async function runSiteAudit(
  input: SiteAuditInput
): Promise<SiteAuditResult> {
  const { domain } = input;

  const runResult = await runCypher(
    `CREATE (w:WorkflowRun {
      id: randomUUID(), type: "site-audit",
      status: "running", startedAt: datetime()
    }) RETURN w.id AS runId`
  );
  const runId = runResult[0].runId as string;

  try {
    // 1. Start on-page crawl
    const url = domain.startsWith("http") ? domain : `https://${domain}`;
    const crawlRes = await onPageTaskPost(url);
    const taskId = crawlRes?.tasks?.[0]?.id;

    if (!taskId) {
      throw new Error("Failed to start on-page crawl");
    }

    // Wait for crawl to process
    await delay(10000);

    // 2. Fetch summary and pages
    const [summaryRes, pagesRes] = await Promise.all([
      onPageSummary(taskId).catch(() => null),
      onPagePages(taskId).catch(() => null),
    ]);

    const pages = pagesRes?.tasks?.[0]?.result?.[0]?.items ?? [];
    const totalPages = pages.length;

    // 3. Analyze issues
    const issues: AuditIssue[] = [];

    // Title issues
    const noTitle = pages.filter((p: Record<string, unknown>) => {
      const meta = p.meta as Record<string, unknown> | undefined;
      return !meta?.title;
    });
    if (noTitle.length > 0) {
      issues.push({
        severity: "critical",
        category: "On-Page SEO",
        description: "Pages missing title tags",
        affectedPages: noTitle.length,
      });
    }

    const longTitles = pages.filter((p: Record<string, unknown>) => {
      const meta = p.meta as Record<string, unknown> | undefined;
      return meta?.title && (meta.title as string).length > 60;
    });
    if (longTitles.length > 0) {
      issues.push({
        severity: "medium",
        category: "On-Page SEO",
        description: "Pages with title tags exceeding 60 characters",
        affectedPages: longTitles.length,
      });
    }

    // Meta description issues
    const noMeta = pages.filter((p: Record<string, unknown>) => {
      const meta = p.meta as Record<string, unknown> | undefined;
      return !meta?.description;
    });
    if (noMeta.length > 0) {
      issues.push({
        severity: "high",
        category: "On-Page SEO",
        description: "Pages missing meta descriptions",
        affectedPages: noMeta.length,
      });
    }

    // Heading issues
    const noH1 = pages.filter((p: Record<string, unknown>) => {
      const onPage = p.on_page as Record<string, unknown> | undefined;
      return (onPage?.h1_count as number) === 0;
    });
    if (noH1.length > 0) {
      issues.push({
        severity: "high",
        category: "On-Page SEO",
        description: "Pages missing H1 heading",
        affectedPages: noH1.length,
      });
    }

    const multiH1 = pages.filter((p: Record<string, unknown>) => {
      const onPage = p.on_page as Record<string, unknown> | undefined;
      return (onPage?.h1_count as number) > 1;
    });
    if (multiH1.length > 0) {
      issues.push({
        severity: "medium",
        category: "On-Page SEO",
        description: "Pages with multiple H1 headings",
        affectedPages: multiH1.length,
      });
    }

    // Thin content
    const thinContent = pages.filter((p: Record<string, unknown>) => {
      const onPage = p.on_page as Record<string, unknown> | undefined;
      const wordCount = (onPage?.content_word_count as number) ?? 0;
      return wordCount > 0 && wordCount < 300;
    });
    if (thinContent.length > 0) {
      issues.push({
        severity: "medium",
        category: "Content Quality",
        description: "Pages with thin content (under 300 words)",
        affectedPages: thinContent.length,
      });
    }

    // Missing structured data
    const noSchema = pages.filter(
      (p: Record<string, unknown>) => !p.has_json_ld && !p.has_microdata
    );
    if (noSchema.length > 0) {
      issues.push({
        severity: "low",
        category: "Structured Data",
        description: "Pages without structured data markup",
        affectedPages: noSchema.length,
      });
    }

    // Missing images alt text
    const noAlt = pages.filter((p: Record<string, unknown>) => {
      const onPage = p.on_page as Record<string, unknown> | undefined;
      return (onPage?.images_without_alt_count as number) > 0;
    });
    if (noAlt.length > 0) {
      issues.push({
        severity: "medium",
        category: "Accessibility",
        description: "Pages with images missing alt text",
        affectedPages: noAlt.length,
      });
    }

    // HTTP status issues
    const errorPages = pages.filter((p: Record<string, unknown>) => {
      const status = p.status_code as number;
      return status >= 400;
    });
    if (errorPages.length > 0) {
      issues.push({
        severity: "critical",
        category: "Technical SEO",
        description: `Pages returning error status codes (4xx/5xx)`,
        affectedPages: errorPages.length,
      });
    }

    // 4. Identify content opportunities
    const contentOpportunities: ContentOpportunity[] = [];

    for (const page of thinContent.slice(0, 10)) {
      const p = page as Record<string, unknown>;
      const meta = p.meta as Record<string, unknown> | undefined;
      contentOpportunities.push({
        url: (p.url as string) ?? "",
        title: (meta?.title as string) ?? "Untitled",
        issue: "Thin content",
        recommendation: "Expand content to at least 1,000 words with relevant subtopics and internal links.",
      });
    }

    // 5. Store audit results in Neo4j
    await runCypher(
      `CREATE (a:SiteAudit {
         id: randomUUID(),
         domain: $domain,
         totalPages: $totalPages,
         criticalIssues: $critical,
         highIssues: $high,
         mediumIssues: $medium,
         lowIssues: $low,
         date: datetime()
       })`,
      {
        domain,
        totalPages,
        critical: issues.filter((i) => i.severity === "critical").length,
        high: issues.filter((i) => i.severity === "high").length,
        medium: issues.filter((i) => i.severity === "medium").length,
        low: issues.filter((i) => i.severity === "low").length,
      }
    );

    // Store content opportunities as potential ContentPiece nodes
    for (const opp of contentOpportunities) {
      await runCypher(
        `MERGE (c:ContentPiece {url: $url})
         ON CREATE SET c.id = randomUUID(), c.title = $title,
           c.slug = $slug, c.stage = "refresh",
           c.createdAt = datetime(), c.updatedAt = datetime()`,
        {
          url: opp.url,
          title: opp.title,
          slug: opp.url.replace(/^https?:\/\/[^/]+/, "").replace(/\/$/, "") || "/",
        }
      );
    }

    const summaryText = `Audited ${totalPages} pages. Found ${issues.length} issues (${issues.filter((i) => i.severity === "critical").length} critical, ${issues.filter((i) => i.severity === "high").length} high). ${contentOpportunities.length} content opportunities identified.`;

    await runCypher(
      `MATCH (w:WorkflowRun {id: $runId})
       SET w.status = "completed", w.completedAt = datetime(), w.summary = $summary`,
      { runId, summary: summaryText }
    );

    return {
      workflowRun: {
        id: runId,
        type: "site-audit",
        status: "completed",
        startedAt: new Date().toISOString(),
        summary: summaryText,
      },
      totalPages,
      issues,
      contentOpportunities,
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

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
