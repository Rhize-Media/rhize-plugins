"use client";

import { useEffect, useState, useCallback } from "react";
import { PIPELINE_STAGES, type ContentPiece, type PipelineStage } from "@/types";

interface BoardData {
  [stage: string]: ContentPiece[];
}

export default function BoardPage() {
  const [board, setBoard] = useState<BoardData>({});
  const [loading, setLoading] = useState(true);
  const [draggedItem, setDraggedItem] = useState<ContentPiece | null>(null);

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
