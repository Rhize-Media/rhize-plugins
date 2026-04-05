export default function ContentLoading() {
  return (
    <div className="mx-auto max-w-4xl px-6 py-8">
      <div className="mb-4 h-3 w-28 rounded bg-zinc-200 dark:bg-zinc-800" />
      <div className="mb-6">
        <div className="h-7 w-3/4 rounded bg-zinc-200 dark:bg-zinc-800" />
        <div className="mt-2 h-3 w-1/2 rounded bg-zinc-200 dark:bg-zinc-800" />
      </div>
      <div className="mb-8 flex gap-2">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-7 w-32 animate-pulse rounded-md bg-zinc-200 dark:bg-zinc-800"
          />
        ))}
      </div>
      {[0, 1, 2].map((i) => (
        <div key={i} className="mb-8">
          <div className="mb-3 h-5 w-32 rounded bg-zinc-200 dark:bg-zinc-800" />
          <div className="h-24 animate-pulse rounded-md bg-zinc-100 dark:bg-zinc-900" />
        </div>
      ))}
    </div>
  );
}
