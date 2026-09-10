"use client";

// Prevent static prerendering of global error page (Next.js 16 LayoutRouterContext bug)
export const dynamic = "force-dynamic";

export default function GlobalError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-center space-y-4">
          <h2 className="text-2xl font-bold">Something went wrong</h2>
          <button
            onClick={reset}
            className="px-4 py-2 bg-white text-black rounded-md font-medium"
          >
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
