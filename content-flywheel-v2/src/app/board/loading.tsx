import { PIPELINE_STAGES } from "@/types";

export default function BoardLoading() {
  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-4 dark:border-zinc-800 dark:bg-zinc-950">
        <div>
          <div className="h-5 w-40 rounded bg-zinc-200 dark:bg-zinc-800" />
          <div className="mt-2 h-3 w-24 rounded bg-zinc-200 dark:bg-zinc-800" />
        </div>
      </header>
      <div className="flex flex-1 gap-4 overflow-x-auto p-6">
        {PIPELINE_STAGES.map((stage) => (
          <div
            key={stage.name}
            className="flex w-72 shrink-0 flex-col rounded-lg bg-zinc-50 dark:bg-zinc-900"
          >
            <div className="flex items-center gap-2 px-4 py-3">
              <div
                className="h-3 w-3 rounded-full"
                style={{ backgroundColor: stage.color }}
              />
              <div className="h-4 w-20 rounded bg-zinc-200 dark:bg-zinc-800" />
            </div>
            <div className="flex flex-1 flex-col gap-2 px-3 pb-3">
              {[0, 1].map((i) => (
                <div
                  key={i}
                  className="h-16 animate-pulse rounded-md border border-zinc-200 bg-white dark:border-zinc-700 dark:bg-zinc-800"
                />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
