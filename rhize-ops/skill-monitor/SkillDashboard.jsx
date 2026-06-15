/* SkillDashboard.jsx
 * Live artifact dashboard for skill-monitor weekly audits.
 *
 * Self-contained React component. Renders identically in:
 *   (a) Claude Artifacts (`application/vnd.ant.react`)
 *   (b) static HTML with React + Recharts + Babel-standalone via CDN
 *
 * Inputs (one of):
 *   - `props.snapshots`: array of SnapshotV1 objects (when used as a component)
 *   - `window.__SNAPSHOTS__`: global injected by dashboard.py (HTML mode)
 *
 * SnapshotV1 shape mirrors monitor.py output:
 *   {
 *     events: Event[],          // post-2026-05-08 schema; may be []
 *     report: {
 *       generated_at, window_days, total_invocations, unique_skills_used,
 *       top_skills: [[skill, count], ...],
 *       direct_top, indirect_top, indirect_compaction_top,
 *       by_week: { "2026-W18": { skill: count, ... } | { _total: N } },
 *       by_project: { path: { skill: count, ... } },
 *       by_entrypoint: { ep: count },
 *       by_source_type: { src: count },
 *       indirect_by_slug: { slug: { skill: count, ... } },
 *     }
 *   }
 *
 * Backfilled snapshots may carry `_backfilled_from_markdown: true` and have
 * empty `events` / partial fields; the component degrades gracefully.
 */

const { useState, useMemo } = React;
const {
  ResponsiveContainer, AreaChart, Area, BarChart, Bar, ScatterChart, Scatter,
  PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, LabelList,
} = Recharts;

// ────────────────────────────────────────────────────────────────────
// Aggregation helpers
// ────────────────────────────────────────────────────────────────────

function getSnapshots() {
  // Use prop if provided (artifact mode), else global (HTML mode).
  // The component is invoked at the bottom of this file; we read whichever
  // is available there.
  return (typeof window !== "undefined" && window.__SNAPSHOTS__) || [];
}

function fmtDate(s) {
  if (!s) return "";
  return s.slice(0, 10);
}

function unionWeeks(snapshots) {
  // Each snapshot's report.by_week may overlap; later snapshots override.
  const weeks = {};
  for (const snap of snapshots) {
    const bw = (snap.report && snap.report.by_week) || {};
    for (const [w, skills] of Object.entries(bw)) {
      if (!weeks[w]) weeks[w] = { week: w, direct: 0, indirect_real: 0, compaction: 0, total: 0 };
      // For backfilled snapshots, by_week contains { _total: N }.
      // For native snapshots, by_week is { skill: count, ... } per week.
      // We don't know per-week direct/indirect breakdown, so split heuristically.
      let weekTotal = 0;
      for (const [k, n] of Object.entries(skills)) {
        if (k === "_total") { weekTotal = n; continue; }
        weekTotal += n;
      }
      weeks[w].total = Math.max(weeks[w].total, weekTotal);
    }
  }
  // Estimate direct/indirect/compaction split per week using the LATEST
  // snapshot's overall ratios (since per-week breakdown isn't stored).
  const latest = snapshots[snapshots.length - 1];
  const r = (latest && latest.report) || {};
  const sum = (arr) => (arr || []).reduce((a, [, n]) => a + n, 0);
  const dT = sum(r.direct_top), iT = sum(r.indirect_top), cT = sum(r.indirect_compaction_top);
  const grand = dT + iT + cT || 1;
  const fDir = dT / grand, fInd = iT / grand, fComp = cT / grand;
  return Object.values(weeks)
    .sort((a, b) => a.week.localeCompare(b.week))
    .map((w) => ({
      ...w,
      direct: Math.round(w.total * fDir),
      indirect_real: Math.round(w.total * fInd),
      compaction: Math.round(w.total * fComp),
    }));
}

function topSkillsWithDeltas(snapshots, n = 25) {
  const latest = snapshots[snapshots.length - 1];
  const prior = snapshots[snapshots.length - 2];
  const lTop = ((latest && latest.report && latest.report.top_skills) || []).slice(0, n);
  const pRank = new Map();
  if (prior && prior.report) {
    (prior.report.top_skills || []).forEach(([s], i) => pRank.set(s, i + 1));
  }
  return lTop.map(([skill, count], i) => {
    const pr = pRank.get(skill);
    const delta = pr ? pr - (i + 1) : null; // positive = moved up
    return { rank: i + 1, skill, count, delta, isNew: pr === undefined };
  });
}

function leverageScatter(snapshots) {
  const r = (snapshots[snapshots.length - 1] || {}).report || {};
  const dMap = new Map(r.direct_top || []);
  const iMap = new Map(r.indirect_top || []);
  const all = new Set([...dMap.keys(), ...iMap.keys()]);
  return [...all].map((skill) => ({
    skill,
    direct: dMap.get(skill) || 0,
    indirect: iMap.get(skill) || 0,
  }));
}

function pruneCandidates(snapshots, keepList = []) {
  // Skills present in ANY older snapshot but absent from the latest,
  // minus anything on the keep-list.
  const latest = snapshots[snapshots.length - 1];
  if (!latest) return [];
  const latestSkills = new Set((latest.report.top_skills || []).map(([s]) => s));
  const everSeen = new Map(); // skill -> { lastSeenSnap, totalCount }
  for (const snap of snapshots) {
    for (const [s, n] of (snap.report.top_skills || [])) {
      const cur = everSeen.get(s) || { total: 0, lastSeen: null };
      cur.total += n;
      cur.lastSeen = snap.report.generated_at;
      everSeen.set(s, cur);
    }
  }
  const keepSet = new Set(keepList);
  return [...everSeen.entries()]
    .filter(([s]) => !latestSkills.has(s) && !keepSet.has(s))
    .map(([skill, v]) => ({ skill, total: v.total, lastSeen: fmtDate(v.lastSeen) }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 30);
}

function woWDelta(snapshots) {
  if (snapshots.length < 2) return { added: [], lost: [], movers: [] };
  const cur = snapshots[snapshots.length - 1].report;
  const prev = snapshots[snapshots.length - 2].report;
  const curMap = new Map(cur.top_skills || []);
  const prevMap = new Map(prev.top_skills || []);
  const added = [...curMap.entries()]
    .filter(([s]) => !prevMap.has(s))
    .map(([s, n]) => ({ skill: s, count: n }))
    .sort((a, b) => b.count - a.count);
  const lost = [...prevMap.entries()]
    .filter(([s]) => !curMap.has(s))
    .map(([s, n]) => ({ skill: s, count: n }))
    .sort((a, b) => b.count - a.count);
  const movers = [];
  for (const [s, c] of curMap) {
    const p = prevMap.get(s);
    if (p === undefined) continue;
    const d = c - p;
    if (Math.abs(d) >= 5) movers.push({ skill: s, delta: d, current: c, prior: p });
  }
  movers.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
  return { added, lost, movers };
}

function bySourceSplit(snapshots) {
  const r = (snapshots[snapshots.length - 1] || {}).report || {};
  const ep = r.by_entrypoint || {};
  const host = (ep.cli || 0) + (ep["sdk-cli"] || 0);
  const cowork = (ep["local-agent"] || 0) + (ep["claude-desktop"] || 0);
  return [
    { name: "Host CLI", value: host, color: "#3b82f6" },
    { name: "Cowork desktop", value: cowork, color: "#a855f7" },
  ].filter((d) => d.value > 0);
}

function topProjects(snapshots, n = 10) {
  const r = (snapshots[snapshots.length - 1] || {}).report || {};
  const bp = r.by_project || {};
  const rows = Object.entries(bp).map(([proj, skills]) => {
    const total = Object.values(skills).reduce((a, b) => a + b, 0);
    const top = Object.entries(skills).sort((a, b) => b[1] - a[1])[0];
    return { project: proj, total, topSkill: top ? top[0] : "—" };
  });
  return rows.sort((a, b) => b.total - a.total).slice(0, n);
}

function bySubagent(snapshots) {
  const r = (snapshots[snapshots.length - 1] || {}).report || {};
  const ibs = r.indirect_by_slug || {};
  return Object.entries(ibs).map(([slug, skills]) => {
    const entries = Object.entries(skills).sort((a, b) => b[1] - a[1]);
    const total = entries.reduce((a, [, n]) => a + n, 0);
    const top3 = entries.slice(0, 3).map(([s, n]) => `${s} (${n})`).join(", ");
    return { slug, total, top3 };
  }).sort((a, b) => b.total - a.total);
}

// ────────────────────────────────────────────────────────────────────
// Subcomponents
// ────────────────────────────────────────────────────────────────────

function KpiTile({ label, value, sublabel }) {
  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 flex-1 min-w-0">
      <div className="text-xs uppercase tracking-wider text-gray-500">{label}</div>
      <div className="text-3xl font-semibold text-gray-900 mt-1">{value}</div>
      {sublabel ? <div className="text-xs text-gray-400 mt-1">{sublabel}</div> : null}
    </div>
  );
}

function DeltaBadge({ delta, isNew }) {
  if (isNew) return <span className="text-xs text-emerald-600 font-medium">new</span>;
  if (delta == null) return null;
  if (delta === 0) return <span className="text-xs text-gray-400">—</span>;
  if (delta > 0) return <span className="text-xs text-emerald-600">▲ {delta}</span>;
  return <span className="text-xs text-rose-600">▼ {Math.abs(delta)}</span>;
}

function SectionCard({ title, subtitle, children }) {
  return (
    <section className="bg-white rounded-lg shadow-sm border border-gray-200 p-5 mb-5">
      <h2 className="text-lg font-semibold text-gray-900">{title}</h2>
      {subtitle ? <p className="text-sm text-gray-500 mt-1 mb-3">{subtitle}</p> : <div className="mb-3" />}
      {children}
    </section>
  );
}

// ────────────────────────────────────────────────────────────────────
// Main component
// ────────────────────────────────────────────────────────────────────

function SkillDashboard(props) {
  const snapshots = (props && props.snapshots) || getSnapshots();

  if (!snapshots.length) {
    return (
      <div className="p-8 text-center text-gray-500">
        No snapshots found. Run <code className="bg-gray-100 px-1 rounded">python3 monitor.py</code> first.
      </div>
    );
  }

  const latest = snapshots[snapshots.length - 1];
  const r = latest.report;
  const weeklyTrend = useMemo(() => unionWeeks(snapshots), [snapshots]);
  const topSkills = useMemo(() => topSkillsWithDeltas(snapshots, 25), [snapshots]);
  const leverage = useMemo(() => leverageScatter(snapshots), [snapshots]);
  const prune = useMemo(() => pruneCandidates(snapshots, props.keepList || []), [snapshots, props.keepList]);
  const wow = useMemo(() => woWDelta(snapshots), [snapshots]);
  const sources = useMemo(() => bySourceSplit(snapshots), [snapshots]);
  const projects = useMemo(() => topProjects(snapshots, 10), [snapshots]);
  const subagents = useMemo(() => bySubagent(snapshots), [snapshots]);

  const dateRange = `${fmtDate(snapshots[0].report.generated_at)} → ${fmtDate(latest.report.generated_at)}`;

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-6 font-sans">
      <div className="max-w-7xl mx-auto">

        {/* Sticky header / KPIs */}
        <header className="mb-6">
          <h1 className="text-2xl font-semibold text-gray-900">Skill Audit Dashboard</h1>
          <p className="text-sm text-gray-500 mt-1">
            {snapshots.length} snapshot{snapshots.length === 1 ? "" : "s"} · {dateRange} · last refreshed {fmtDate(r.generated_at)}
          </p>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
            <KpiTile label="Total invocations" value={r.total_invocations} sublabel={`window: ${r.window_days || "all-time"} days`} />
            <KpiTile label="Unique skills" value={r.unique_skills_used} />
            <KpiTile label="Snapshots" value={snapshots.length} sublabel={dateRange} />
            <KpiTile label="Direct ÷ Indirect" value={
              `${(r.direct_top || []).reduce((a, [, n]) => a + n, 0)} ÷ ${(r.indirect_top || []).reduce((a, [, n]) => a + n, 0)}`
            } sublabel="latest snapshot" />
          </div>
        </header>

        {/* 1. Trend chart */}
        <SectionCard title="Weekly invocation trend" subtitle="Stacked by direct / indirect (real subagent) / auto-compaction">
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <AreaChart data={weeklyTrend} margin={{ top: 10, right: 20, left: -10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis dataKey="week" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend />
                <Area type="monotone" dataKey="direct" stackId="1" stroke="#2563eb" fill="#3b82f6" name="Direct" />
                <Area type="monotone" dataKey="indirect_real" stackId="1" stroke="#7c3aed" fill="#a855f7" name="Indirect (real)" />
                <Area type="monotone" dataKey="compaction" stackId="1" stroke="#9ca3af" fill="#d1d5db" name="Auto-compaction" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        {/* 2. Top skills */}
        <SectionCard title="Top 25 skills (latest snapshot)" subtitle="With rank delta vs. prior snapshot">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-gray-500 border-b border-gray-200">
                  <th className="py-2 pr-2 w-10">#</th>
                  <th className="py-2 pr-2">Skill</th>
                  <th className="py-2 pr-2 w-20 text-right">Count</th>
                  <th className="py-2 pr-2 w-20 text-right">Δ rank</th>
                </tr>
              </thead>
              <tbody>
                {topSkills.map((row) => (
                  <tr key={row.skill} className="border-b border-gray-100">
                    <td className="py-1.5 pr-2 text-gray-400">{row.rank}</td>
                    <td className="py-1.5 pr-2"><code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{row.skill}</code></td>
                    <td className="py-1.5 pr-2 text-right tabular-nums">{row.count}</td>
                    <td className="py-1.5 pr-2 text-right"><DeltaBadge delta={row.delta} isNew={row.isNew} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </SectionCard>

        {/* 3. Leverage scatter */}
        <SectionCard title="Direct vs. indirect leverage" subtitle="Skills above the diagonal: subagents reach for them more than you do — candidate trigger-description tweaks">
          <div style={{ width: "100%", height: 320 }}>
            <ResponsiveContainer>
              <ScatterChart margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" dataKey="direct" name="Direct" tick={{ fontSize: 11 }} label={{ value: "Direct invocations", position: "bottom", offset: -5, style: { fontSize: 11, fill: "#6b7280" } }} />
                <YAxis type="number" dataKey="indirect" name="Indirect" tick={{ fontSize: 11 }} label={{ value: "Indirect", angle: -90, position: "insideLeft", style: { fontSize: 11, fill: "#6b7280" } }} />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} content={({ payload }) => {
                  if (!payload || !payload.length) return null;
                  const d = payload[0].payload;
                  return (
                    <div className="bg-white border border-gray-200 rounded shadow px-2 py-1 text-xs">
                      <div className="font-medium">{d.skill}</div>
                      <div className="text-gray-500">direct: {d.direct} · indirect: {d.indirect}</div>
                    </div>
                  );
                }} />
                <Scatter data={leverage} fill="#6366f1" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        {/* 4. Prune candidates */}
        <SectionCard title="Prune candidates" subtitle={`Skills not seen in the latest snapshot (excluding keep-list of ${(props.keepList || []).length}). Sorted by all-time count.`}>
          {prune.length === 0 ? (
            <p className="text-sm text-gray-500">None — every skill seen historically still appears in the latest snapshot.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-gray-500 border-b border-gray-200">
                    <th className="py-2 pr-2">Skill</th>
                    <th className="py-2 pr-2 w-24 text-right">All-time</th>
                    <th className="py-2 pr-2 w-32 text-right">Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {prune.map((row) => (
                    <tr key={row.skill} className="border-b border-gray-100">
                      <td className="py-1.5 pr-2"><code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{row.skill}</code></td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{row.total}</td>
                      <td className="py-1.5 pr-2 text-right text-gray-500 text-xs tabular-nums">{row.lastSeen}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>

        {/* 5. Subagent type breakdown */}
        <SectionCard title="Indirect skill use by subagent type" subtitle="Resolved from each main session's toolUseResult.agentType">
          {subagents.length === 0 ? (
            <p className="text-sm text-gray-500">No subagent attribution data yet — needs at least one fresh snapshot from the post-2026-05-08 monitor.py.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs uppercase tracking-wider text-gray-500 border-b border-gray-200">
                    <th className="py-2 pr-2">Agent type</th>
                    <th className="py-2 pr-2 w-20 text-right">Total</th>
                    <th className="py-2 pr-2">Top skills</th>
                  </tr>
                </thead>
                <tbody>
                  {subagents.map((row) => (
                    <tr key={row.slug} className="border-b border-gray-100">
                      <td className="py-1.5 pr-2"><code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{row.slug}</code></td>
                      <td className="py-1.5 pr-2 text-right tabular-nums">{row.total}</td>
                      <td className="py-1.5 pr-2 text-xs text-gray-600">{row.top3}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>

        {/* 6. Top projects */}
        <SectionCard title="Top projects by skill density" subtitle="cwd-based; Cowork sandbox paths mapped to originCwd">
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <BarChart data={projects} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis type="category" dataKey="project" tick={{ fontSize: 10 }} width={220}
                  tickFormatter={(p) => p.length > 32 ? "…" + p.slice(-30) : p} />
                <Tooltip />
                <Bar dataKey="total" fill="#0ea5e9" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>

        {/* 7. Source split */}
        <SectionCard title="Host CLI vs. Cowork desktop split" subtitle="From by_entrypoint">
          {sources.length === 0 ? (
            <p className="text-sm text-gray-500">No entrypoint data.</p>
          ) : (
            <div style={{ width: "100%", height: 240 }}>
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={sources} dataKey="value" nameKey="name" outerRadius={90} label>
                    {sources.map((d, i) => <Cell key={i} fill={d.color} />)}
                  </Pie>
                  <Legend />
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
        </SectionCard>

        {/* 8. Week-over-week delta */}
        <SectionCard title="Week-over-week delta" subtitle="Latest snapshot vs. prior">
          {snapshots.length < 2 ? (
            <p className="text-sm text-gray-500">Need at least two snapshots — wait one week for the next audit run.</p>
          ) : (
            <div className="grid md:grid-cols-2 gap-5">
              <div>
                <h3 className="text-sm font-medium text-emerald-700 mb-2">New this week ({wow.added.length})</h3>
                {wow.added.length === 0 ? <p className="text-xs text-gray-400">none</p> : (
                  <ul className="text-sm space-y-1">
                    {wow.added.slice(0, 15).map((d) => (
                      <li key={d.skill}><code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{d.skill}</code> <span className="text-gray-500">— {d.count}</span></li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <h3 className="text-sm font-medium text-rose-700 mb-2">Lost this week ({wow.lost.length})</h3>
                {wow.lost.length === 0 ? <p className="text-xs text-gray-400">none</p> : (
                  <ul className="text-sm space-y-1">
                    {wow.lost.slice(0, 15).map((d) => (
                      <li key={d.skill}><code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{d.skill}</code> <span className="text-gray-500">— {d.count} prior</span></li>
                    ))}
                  </ul>
                )}
              </div>
              {wow.movers.length > 0 ? (
                <div className="md:col-span-2">
                  <h3 className="text-sm font-medium text-gray-700 mb-2">Big movers (Δ ≥ 5)</h3>
                  <ul className="text-sm space-y-1">
                    {wow.movers.slice(0, 10).map((d) => (
                      <li key={d.skill}>
                        <code className="text-xs bg-gray-100 px-1.5 py-0.5 rounded">{d.skill}</code>{" "}
                        <span className={d.delta > 0 ? "text-emerald-600" : "text-rose-600"}>
                          {d.delta > 0 ? "▲" : "▼"} {Math.abs(d.delta)}
                        </span>
                        <span className="text-gray-500"> ({d.prior} → {d.current})</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )}
        </SectionCard>

        {/* Footer */}
        <footer className="text-xs text-gray-400 text-center mt-6 mb-2 leading-relaxed">
          Generated {fmtDate(r.generated_at)} from {snapshots.length} snapshot{snapshots.length === 1 ? "" : "s"} covering {dateRange}.
          <br />
          <span className="text-gray-300">
            Limitations: slash-only invocations not counted · no terminal/IDE breakdown (both log as <code>cli</code>) ·
            compaction agents bucketed separately.
          </span>
        </footer>

      </div>
    </div>
  );
}

// Mount to DOM in HTML mode. In Claude Artifact mode, the artifact runtime
// imports this file and mounts SkillDashboard automatically.
if (typeof document !== "undefined" && document.getElementById("root")) {
  const root = ReactDOM.createRoot(document.getElementById("root"));
  root.render(React.createElement(SkillDashboard, {
    snapshots: window.__SNAPSHOTS__ || [],
    keepList: window.__KEEP_LIST__ || [],
  }));
}
