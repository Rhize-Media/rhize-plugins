"use client";

import { useEffect, useState, use } from "react";
import { PIPELINE_STAGES, type ContentPiece, type Keyword, type SERPSnapshot, type SEOScore, type WorkflowRun, type AIVisibilitySnapshot } from "@/types";

interface ContentDetail extends ContentPiece {
  keywords: Keyword[];
  serpSnapshots: SERPSnapshot[];
  backlinks: { domain: string; authorityRank: number; anchorText: string }[];
  internalLinks: { targetTitle: string; targetSlug: string }[];
  seoScore: SEOScore | null;
  workflowRuns: WorkflowRun[];
  aiVisibility: (AIVisibilitySnapshot & { query: string })[];
  stageHistory: { stage: string; enteredAt: string; leftAt: string }[];
}

async function fetchContentDetail(id: string): Promise<ContentDetail | null> {
  const res = await fetch(`/api/content/${id}`);
  if (!res.ok) return null;
  return res.json();
}

async function runWorkflow(workflow: string, body: Record<string, unknown>) {
  const res = await fetch(`/api/workflows/${workflow}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

export default function ContentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [content, setContent] = useState<ContentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [runningWorkflow, setRunningWorkflow] = useState<string | null>(null);

  const refresh = () => fetchContentDetail(id).then(setContent);

  useEffect(() => {
    fetchContentDetail(id)
      .then(setContent)
      .finally(() => setLoading(false));
  }, [id]);

  async function handleRunWorkflow(workflow: string, body: Record<string, unknown>) {
    setRunningWorkflow(workflow);
    try {
      await runWorkflow(workflow, body);
      await refresh();
    } catch (err) {
      console.error(`Workflow ${workflow} failed:`, err);
    } finally {
      setRunningWorkflow(null);
    }
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-zinc-500">Loading...</p>
      </div>
    );
  }

  if (!content) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-zinc-500">Content not found</p>
      </div>
    );
  }

  const stageConfig = PIPELINE_STAGES.find((s) => s.name === content.stage);

  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <a
        href="/board"
        className="mb-4 inline-block text-sm text-zinc-500 hover:text-zinc-700"
      >
        &larr; Back to board
      </a>

      <div className="mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
            {content.title}
          </h1>
          {stageConfig && (
            <span
              className="rounded-full px-3 py-1 text-xs font-medium text-white"
              style={{ backgroundColor: stageConfig.color }}
            >
              {stageConfig.label}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-zinc-500">
          by {content.author} &middot; /{content.slug}
          {content.url && (
            <>
              {" "}&middot;{" "}
              <a href={content.url} className="underline" target="_blank" rel="noreferrer">
                {content.url}
              </a>
            </>
          )}
        </p>
      </div>

      {/* Workflow Actions */}
      <section className="mb-8 flex flex-wrap gap-2">
        <button
          onClick={() => handleRunWorkflow("keyword-research", { seeds: [content.title.split(" ").slice(0, 3).join(" ")], contentId: id })}
          disabled={runningWorkflow !== null}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {runningWorkflow === "keyword-research" ? "Running..." : "Research Keywords"}
        </button>
        {content.url && (
          <button
            onClick={() => handleRunWorkflow("content-optimize", { contentId: id, url: content.url })}
            disabled={runningWorkflow !== null}
            className="rounded-md bg-orange-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50"
          >
            {runningWorkflow === "content-optimize" ? "Running..." : "Run SEO Audit"}
          </button>
        )}
        {content.url && (
          <button
            onClick={() => handleRunWorkflow("serp-analysis", { contentId: id })}
            disabled={runningWorkflow !== null}
            className="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
          >
            {runningWorkflow === "serp-analysis" ? "Running..." : "Check Rankings"}
          </button>
        )}
        {content.url && (
          <button
            onClick={() => handleRunWorkflow("backlink-analysis", { contentId: id, domain: new URL(content.url!).hostname })}
            disabled={runningWorkflow !== null}
            className="rounded-md bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {runningWorkflow === "backlink-analysis" ? "Running..." : "Analyze Backlinks"}
          </button>
        )}
        <button
          onClick={() => handleRunWorkflow("ai-visibility", { contentId: id, brand: content.title.split(" ").slice(0, 2).join(" ") })}
          disabled={runningWorkflow !== null}
          className="rounded-md bg-teal-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-teal-700 disabled:opacity-50"
        >
          {runningWorkflow === "ai-visibility" ? "Running..." : "AI Visibility"}
        </button>
      </section>

      {/* SEO Score */}
      {content.seoScore && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-zinc-800 dark:text-zinc-200">
            SEO Score
          </h2>
          <div className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-700">
            <div className="mb-4 flex items-center gap-4">
              <div
                className={`flex h-16 w-16 items-center justify-center rounded-full text-xl font-bold text-white ${
                  content.seoScore.overall >= 80
                    ? "bg-green-500"
                    : content.seoScore.overall >= 60
                    ? "bg-yellow-500"
                    : "bg-red-500"
                }`}
              >
                {content.seoScore.overall}
              </div>
              <div className="text-sm text-zinc-600 dark:text-zinc-400">
                <p>Word count: {content.seoScore.wordCount.toLocaleString()}</p>
                <p>Last analyzed: {content.seoScore.date}</p>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {[
                { label: "Title", score: content.seoScore.titleScore },
                { label: "Meta", score: content.seoScore.metaScore },
                { label: "Headings", score: content.seoScore.headingScore },
                { label: "E-E-A-T", score: content.seoScore.eeatScore },
                { label: "Internal Links", score: content.seoScore.internalLinkScore },
                { label: "Schema", score: content.seoScore.structuredDataScore },
              ].map((dim) => (
                <div key={dim.label} className="rounded-md bg-zinc-100 p-2 dark:bg-zinc-800">
                  <p className="text-xs text-zinc-500">{dim.label}</p>
                  <p className={`text-lg font-semibold ${
                    dim.score >= 70 ? "text-green-600" : dim.score >= 50 ? "text-yellow-600" : "text-red-600"
                  }`}>
                    {dim.score}
                  </p>
                </div>
              ))}
            </div>
            {content.seoScore.recommendations.length > 0 && (
              <div className="mt-4">
                <p className="mb-1 text-sm font-medium text-zinc-700 dark:text-zinc-300">Recommendations</p>
                <ul className="list-inside list-disc space-y-1 text-sm text-zinc-600 dark:text-zinc-400">
                  {content.seoScore.recommendations.map((rec, i) => (
                    <li key={i}>{rec}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Keywords */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-zinc-800 dark:text-zinc-200">
          Target Keywords ({content.keywords.length})
        </h2>
        {content.keywords.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-zinc-500 dark:border-zinc-700">
                  <th className="pb-2 pr-4">Keyword</th>
                  <th className="pb-2 pr-4">Volume</th>
                  <th className="pb-2 pr-4">Difficulty</th>
                  <th className="pb-2 pr-4">Intent</th>
                  <th className="pb-2">CPC</th>
                </tr>
              </thead>
              <tbody>
                {content.keywords.map((kw) => (
                  <tr key={kw.id} className="border-b border-zinc-100 dark:border-zinc-800">
                    <td className="py-2 pr-4 font-medium">{kw.term}</td>
                    <td className="py-2 pr-4">{kw.volume?.toLocaleString()}</td>
                    <td className="py-2 pr-4">{kw.difficulty}</td>
                    <td className="py-2 pr-4">{kw.intent}</td>
                    <td className="py-2">{kw.cpc ? `$${kw.cpc.toFixed(2)}` : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-zinc-400">No keywords linked yet.</p>
        )}
      </section>

      {/* SERP History */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-zinc-800 dark:text-zinc-200">
          SERP History ({content.serpSnapshots.length})
        </h2>
        {content.serpSnapshots.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-zinc-500 dark:border-zinc-700">
                  <th className="pb-2 pr-4">Date</th>
                  <th className="pb-2 pr-4">Position</th>
                  <th className="pb-2 pr-4">Features</th>
                  <th className="pb-2">AI Overview</th>
                </tr>
              </thead>
              <tbody>
                {content.serpSnapshots.map((snap) => (
                  <tr key={snap.id} className="border-b border-zinc-100 dark:border-zinc-800">
                    <td className="py-2 pr-4">{snap.date}</td>
                    <td className="py-2 pr-4 font-medium">{snap.position || "—"}</td>
                    <td className="py-2 pr-4">{(snap.features ?? []).join(", ") || "—"}</td>
                    <td className="py-2">{snap.aiOverviewCited ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-zinc-400">No SERP data yet.</p>
        )}
      </section>

      {/* Backlinks */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-zinc-800 dark:text-zinc-200">
          Backlinks ({content.backlinks.length})
        </h2>
        {content.backlinks.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-zinc-500 dark:border-zinc-700">
                  <th className="pb-2 pr-4">Domain</th>
                  <th className="pb-2 pr-4">Authority</th>
                  <th className="pb-2">Anchor Text</th>
                </tr>
              </thead>
              <tbody>
                {content.backlinks.map((bl, i) => (
                  <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800">
                    <td className="py-2 pr-4">{bl.domain}</td>
                    <td className="py-2 pr-4">{bl.authorityRank}</td>
                    <td className="py-2">{bl.anchorText}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-sm text-zinc-400">No backlinks tracked yet.</p>
        )}
      </section>

      {/* Internal Links */}
      <section className="mb-8">
        <h2 className="mb-3 text-lg font-semibold text-zinc-800 dark:text-zinc-200">
          Internal Links ({content.internalLinks.length})
        </h2>
        {content.internalLinks.length > 0 ? (
          <ul className="space-y-1">
            {content.internalLinks.map((link, i) => (
              <li key={i} className="text-sm">
                <span className="text-zinc-600 dark:text-zinc-400">Links to: </span>
                <span className="font-medium">{link.targetTitle}</span>
                <span className="text-zinc-400"> /{link.targetSlug}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-zinc-400">No internal links yet.</p>
        )}
      </section>

      {/* Workflow History */}
      {content.workflowRuns && content.workflowRuns.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-zinc-800 dark:text-zinc-200">
            Workflow History ({content.workflowRuns.length})
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-zinc-500 dark:border-zinc-700">
                  <th className="pb-2 pr-4">Type</th>
                  <th className="pb-2 pr-4">Status</th>
                  <th className="pb-2 pr-4">Summary</th>
                  <th className="pb-2">Started</th>
                </tr>
              </thead>
              <tbody>
                {content.workflowRuns.map((w) => (
                  <tr key={w.id} className="border-b border-zinc-100 dark:border-zinc-800">
                    <td className="py-2 pr-4 font-mono text-xs">{w.type}</td>
                    <td className="py-2 pr-4">
                      <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        w.status === "completed"
                          ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                          : w.status === "failed"
                          ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                          : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                      }`}>
                        {w.status}
                      </span>
                    </td>
                    <td className="max-w-xs truncate py-2 pr-4 text-zinc-600 dark:text-zinc-400">
                      {w.summary ?? "—"}
                    </td>
                    <td className="py-2 text-xs text-zinc-500">
                      {w.startedAt?.slice(0, 19).replace("T", " ") ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* AI Visibility */}
      {content.aiVisibility && content.aiVisibility.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-zinc-800 dark:text-zinc-200">
            AI Visibility ({content.aiVisibility.length})
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-left text-zinc-500 dark:border-zinc-700">
                  <th className="pb-2 pr-4">Query</th>
                  <th className="pb-2 pr-4">LLM</th>
                  <th className="pb-2 pr-4">Mention Rate</th>
                  <th className="pb-2 pr-4">Accuracy</th>
                  <th className="pb-2">Citations</th>
                </tr>
              </thead>
              <tbody>
                {content.aiVisibility.map((av, i) => (
                  <tr key={i} className="border-b border-zinc-100 dark:border-zinc-800">
                    <td className="py-2 pr-4">{av.query}</td>
                    <td className="py-2 pr-4 font-mono text-xs">{av.llm}</td>
                    <td className="py-2 pr-4">{av.mentionRate}%</td>
                    <td className="py-2 pr-4">{av.accuracy}%</td>
                    <td className="py-2">{av.citationCount}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* Stage History */}
      {content.stageHistory && content.stageHistory.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-3 text-lg font-semibold text-zinc-800 dark:text-zinc-200">
            Stage History ({content.stageHistory.length})
          </h2>
          <div className="space-y-2">
            {content.stageHistory.map((transition, i) => {
              const cfg = PIPELINE_STAGES.find((s) => s.name === transition.stage);
              return (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <span
                    className="inline-block rounded-full px-2 py-0.5 text-xs font-medium text-white"
                    style={{ backgroundColor: cfg?.color ?? "#71717a" }}
                  >
                    {cfg?.label ?? transition.stage}
                  </span>
                  <span className="text-zinc-500">
                    {transition.enteredAt?.slice(0, 10) ?? "?"} — {transition.leftAt?.slice(0, 10) ?? "?"}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      )}
    </div>
  );
}
