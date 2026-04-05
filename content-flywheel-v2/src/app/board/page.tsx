"use client";

import { useEffect, useState, useCallback } from "react";
import { PIPELINE_STAGES, type ContentPiece, type PipelineStage } from "@/types";

interface BoardData {
  [stage: string]: ContentPiece[];
}

function slugify(input: string): string {
  return input
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-");
}

export default function BoardPage() {
  const [board, setBoard] = useState<BoardData>({});
  const [loading, setLoading] = useState(true);
  const [draggedItem, setDraggedItem] = useState<ContentPiece | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    title: "",
    slug: "",
    author: "",
    url: "",
    stage: "inspiration" as PipelineStage,
  });
  const [slugEdited, setSlugEdited] = useState(false);

  function resetForm() {
    setForm({ title: "", slug: "", author: "", url: "", stage: "inspiration" });
    setSlugEdited(false);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!form.title || !form.slug || !form.author) return;
    setCreating(true);
    try {
      const res = await fetch("/api/content", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: form.title,
          slug: form.slug,
          author: form.author,
          url: form.url || null,
          stage: form.stage,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        alert(`Failed to create: ${err.error ?? "unknown error"}`);
        return;
      }
      await fetchBoard();
      setShowCreate(false);
      resetForm();
    } finally {
      setCreating(false);
    }
  }

  const fetchBoard = useCallback(async () => {
    try {
      const res = await fetch("/api/board");
      const data = await res.json();
      const grouped: BoardData = {};
      for (const stage of PIPELINE_STAGES) {
        grouped[stage.name] = [];
      }
      for (const [stage, pieces] of Object.entries(data.board ?? {})) {
        grouped[stage] = pieces as ContentPiece[];
      }
      setBoard(grouped);
    } catch (err) {
      console.error("Failed to fetch board:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBoard();
  }, [fetchBoard]);

  async function handleDrop(targetStage: PipelineStage) {
    if (!draggedItem) return;

    // Optimistic update
    setBoard((prev) => {
      const next = { ...prev };
      for (const stage of Object.keys(next)) {
        next[stage] = next[stage].filter((c) => c.id !== draggedItem.id);
      }
      next[targetStage] = [
        ...next[targetStage],
        { ...draggedItem, stage: targetStage },
      ];
      return next;
    });

    setDraggedItem(null);

    // Persist to Neo4j via dedicated endpoint
    await fetch("/api/board/move", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contentId: draggedItem.id,
        newStage: targetStage,
      }),
    });
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-zinc-500">Loading pipeline...</p>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-zinc-950">
        <div>
          <h1 className="text-xl font-semibold text-zinc-900 dark:text-zinc-100">
            Content Flywheel
          </h1>
          <p className="text-sm text-zinc-500">Pipeline Board</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => {
              resetForm();
              setShowCreate(true);
            }}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
          >
            + New Content
          </button>
          <button
            onClick={async () => {
              const domain = prompt("Enter domain to audit:");
              if (!domain) return;
              await fetch("/api/workflows/site-audit", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ domain }),
              });
              fetchBoard();
            }}
            className="rounded-md bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            Site Audit
          </button>
          <button
            onClick={async () => {
              const seeds = prompt("Enter seed keywords (comma-separated):");
              if (!seeds) return;
              await fetch("/api/workflows/keyword-research", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ seeds: seeds.split(",").map((s) => s.trim()) }),
              });
            }}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
          >
            Keyword Research
          </button>
        </div>
      </header>

      {/* Create Content Modal */}
      {showCreate && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={() => !creating && setShowCreate(false)}
        >
          <div
            className="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-900"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              New Content
            </h2>
            <form onSubmit={handleCreate} className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                  Title
                </label>
                <input
                  type="text"
                  required
                  value={form.title}
                  onChange={(e) => {
                    const title = e.target.value;
                    setForm((f) => ({
                      ...f,
                      title,
                      slug: slugEdited ? f.slug : slugify(title),
                    }));
                  }}
                  className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  placeholder="The Ultimate Guide to..."
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                  Slug
                </label>
                <input
                  type="text"
                  required
                  value={form.slug}
                  onChange={(e) => {
                    setForm((f) => ({ ...f, slug: e.target.value }));
                    setSlugEdited(true);
                  }}
                  className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  placeholder="ultimate-guide"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                  Author
                </label>
                <input
                  type="text"
                  required
                  value={form.author}
                  onChange={(e) => setForm((f) => ({ ...f, author: e.target.value }))}
                  className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  placeholder="Jim Deola"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                  URL (optional)
                </label>
                <input
                  type="url"
                  value={form.url}
                  onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                  className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                  placeholder="https://rhize.media/blog/..."
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-zinc-600 dark:text-zinc-400">
                  Stage
                </label>
                <select
                  value={form.stage}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, stage: e.target.value as PipelineStage }))
                  }
                  className="w-full rounded-md border border-zinc-300 bg-white px-3 py-1.5 text-sm text-zinc-900 focus:border-zinc-500 focus:outline-none dark:border-zinc-700 dark:bg-zinc-800 dark:text-zinc-100"
                >
                  {PIPELINE_STAGES.map((s) => (
                    <option key={s.name} value={s.name}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="mt-4 flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  disabled={creating}
                  className="rounded-md px-3 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100 disabled:opacity-50 dark:text-zinc-300 dark:hover:bg-zinc-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creating}
                  className="rounded-md bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                >
                  {creating ? "Creating..." : "Create"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="flex flex-1 gap-4 overflow-x-auto p-6">
        {PIPELINE_STAGES.map((stage) => (
          <div
            key={stage.name}
            className="flex w-72 shrink-0 flex-col rounded-lg bg-zinc-50 dark:bg-zinc-900"
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => handleDrop(stage.name)}
          >
            {/* Column header */}
            <div className="flex items-center gap-2 px-4 py-3">
              <div
                className="h-3 w-3 rounded-full"
                style={{ backgroundColor: stage.color }}
              />
              <h2 className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                {stage.label}
              </h2>
              <span className="ml-auto rounded-full bg-zinc-200 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400">
                {board[stage.name]?.length ?? 0}
              </span>
            </div>

            {/* Cards */}
            <div className="flex flex-1 flex-col gap-2 overflow-y-auto px-3 pb-3">
              {(board[stage.name] ?? []).map((piece) => (
                <a
                  key={piece.id}
                  href={`/content/${piece.id}`}
                  draggable
                  onDragStart={() => setDraggedItem(piece)}
                  className="block cursor-grab rounded-md border border-zinc-200 bg-white p-3 shadow-sm transition-shadow hover:shadow-md active:cursor-grabbing dark:border-zinc-700 dark:bg-zinc-800"
                >
                  <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                    {piece.title}
                  </p>
                  <div className="mt-2 flex items-center gap-2 text-xs text-zinc-500">
                    <span>{piece.author}</span>
                    {piece.url && <span>&middot; {new URL(piece.url).pathname}</span>}
                  </div>
                </a>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
