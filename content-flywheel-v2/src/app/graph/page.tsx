"use client";

import { useEffect, useState } from "react";
import { PIPELINE_STAGES } from "@/types";

interface GraphStats {
  nodeCounts: Record<string, number>;
  relationshipCounts: Record<string, number>;
  stageDistribution: Array<{ stage: string; order: number; count: number }>;
  recentWorkflows: Array<{
    id: string;
    type: string;
    status: string;
    summary: string | null;
    startedAt: string;
  }>;
  topClusters: Array<{ name: string; pillarTopic: string; keywordCount: number }>;
}

export default function GraphPage() {
  const [stats, setStats] = useState<GraphStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/graph/stats")
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then((data) => {
        setStats(data);
        setError(null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-zinc-500">Loading graph stats...</p>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-zinc-500">Failed to load stats: {error}</p>
      </div>
    );
  }

  const maxStageCount = Math.max(
    1,
    ...stats.stageDistribution.map((s) => s.count)
  );

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl">
        <header className="mb-6">
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            Graph Explorer
          </h1>
          <p className="text-sm text-zinc-500">
            Neo4j content graph statistics and recent activity
          </p>
        </header>

        {/* Node counts */}
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Nodes
          </h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
            {Object.entries(stats.nodeCounts).map(([label, count]) => (
              <div
                key={label}
                className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900"
              >
                <p className="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
                  {count.toLocaleString()}
                </p>
                <p className="mt-1 text-xs text-zinc-500">{label}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Stage distribution (funnel) */}
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Pipeline Funnel
          </h2>
          <div className="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
            <div className="space-y-2">
              {stats.stageDistribution.map((s) => {
                const stageConfig = PIPELINE_STAGES.find(
                  (p) => p.name === s.stage
                );
                const widthPct = (s.count / maxStageCount) * 100;
                return (
                  <div key={s.stage} className="flex items-center gap-3">
                    <div className="w-24 text-xs text-zinc-600 dark:text-zinc-400">
                      {stageConfig?.label ?? s.stage}
                    </div>
                    <div className="relative flex-1 overflow-hidden rounded-md bg-zinc-100 dark:bg-zinc-800">
                      <div
                        className="h-6 rounded-md transition-all"
                        style={{
                          width: `${Math.max(widthPct, 2)}%`,
                          backgroundColor: stageConfig?.color ?? "#71717a",
                        }}
                      />
                    </div>
                    <div className="w-12 text-right text-sm font-medium text-zinc-700 dark:text-zinc-300">
                      {s.count}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </section>

        {/* Relationship counts */}
        <section className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
            Relationships
          </h2>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
            {Object.entries(stats.relationshipCounts).map(([type, count]) => (
              <div
                key={type}
                className="rounded-md border border-zinc-200 bg-white px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900"
              >
                <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                  {count.toLocaleString()}
                </p>
                <p className="font-mono text-[10px] text-zinc-500">{type}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Top clusters */}
        {stats.topClusters.length > 0 && (
          <section className="mb-8">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
              Top Keyword Clusters
            </h2>
            <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-left dark:border-zinc-800">
                    <th className="px-4 py-2 font-medium text-zinc-500">
                      Cluster
                    </th>
                    <th className="px-4 py-2 font-medium text-zinc-500">
                      Pillar Topic
                    </th>
                    <th className="px-4 py-2 text-right font-medium text-zinc-500">
                      Keywords
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {stats.topClusters.map((c) => (
                    <tr
                      key={c.name}
                      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                    >
                      <td className="px-4 py-2 font-medium text-zinc-900 dark:text-zinc-100">
                        {c.name}
                      </td>
                      <td className="px-4 py-2 text-zinc-600 dark:text-zinc-400">
                        {c.pillarTopic}
                      </td>
                      <td className="px-4 py-2 text-right text-zinc-700 dark:text-zinc-300">
                        {c.keywordCount}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {/* Recent workflows */}
        {stats.recentWorkflows.length > 0 && (
          <section className="mb-8">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-zinc-500">
              Recent Workflow Runs
            </h2>
            <div className="rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-left dark:border-zinc-800">
                    <th className="px-4 py-2 font-medium text-zinc-500">Type</th>
                    <th className="px-4 py-2 font-medium text-zinc-500">Status</th>
                    <th className="px-4 py-2 font-medium text-zinc-500">
                      Summary
                    </th>
                    <th className="px-4 py-2 font-medium text-zinc-500">
                      Started
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {stats.recentWorkflows.map((w) => (
                    <tr
                      key={w.id}
                      className="border-b border-zinc-100 last:border-0 dark:border-zinc-800"
                    >
                      <td className="px-4 py-2 font-mono text-xs text-zinc-700 dark:text-zinc-300">
                        {w.type}
                      </td>
                      <td className="px-4 py-2">
                        <span
                          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                            w.status === "completed"
                              ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400"
                              : w.status === "failed"
                              ? "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                              : "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400"
                          }`}
                        >
                          {w.status}
                        </span>
                      </td>
                      <td className="max-w-md truncate px-4 py-2 text-zinc-600 dark:text-zinc-400">
                        {w.summary ?? "—"}
                      </td>
                      <td className="px-4 py-2 text-xs text-zinc-500">
                        {w.startedAt.slice(0, 19).replace("T", " ")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
