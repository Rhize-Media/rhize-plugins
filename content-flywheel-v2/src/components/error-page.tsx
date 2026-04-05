"use client";

interface ErrorPageProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export function ErrorPage({ error, reset }: ErrorPageProps) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-8">
      <div className="text-center">
        <h2 className="mb-2 text-lg font-semibold text-zinc-800 dark:text-zinc-200">
          Something went wrong
        </h2>
        <p className="max-w-md text-sm text-zinc-500">{error.message}</p>
        {error.digest && (
          <p className="mt-1 text-xs text-zinc-400">digest: {error.digest}</p>
        )}
      </div>
      <button
        onClick={reset}
        className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-zinc-100 dark:text-zinc-900"
      >
        Try again
      </button>
    </div>
  );
}
