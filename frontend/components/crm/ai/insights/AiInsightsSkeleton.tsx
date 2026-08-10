import { cn } from '@/lib/utils';

/* ============================================================
   AI INSIGHTS SKELETON
   Mirrors the shape of the generated report: executive summary,
   score indicators, insight cards and analytics widgets.
   Animation is suppressed under prefers-reduced-motion.
   ============================================================ */

function Bar({ className }: { className?: string }) {
  return (
    <div
      className={cn('rounded motion-safe:animate-pulse', className)}
      style={{ background: 'var(--border)' }}
    />
  );
}

export default function AiInsightsSkeleton() {
  return (
    <div className="space-y-4" aria-hidden="true">
      {/* Executive summary */}
      <div className="surface bd rounded-2xl border p-5">
        <div className="flex items-start gap-3">
          <Bar className="h-10 w-10 shrink-0 rounded-xl" />
          <div className="min-w-0 flex-1 space-y-2">
            <Bar className="h-4 w-48" />
            <Bar className="h-3 w-full max-w-lg" />
            <Bar className="h-3 w-3/4 max-w-md" />
          </div>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="surface-2 bd rounded-xl border p-3.5">
              <Bar className="h-2.5 w-20" />
              <Bar className="mt-2.5 h-6 w-24" />
              <Bar className="mt-2 h-1.5 w-full rounded-full" />
            </div>
          ))}
        </div>

        <div className="mt-3 grid gap-3 md:grid-cols-2">
          <div className="surface-2 bd rounded-xl border p-3.5">
            <Bar className="h-2.5 w-28" />
            <Bar className="mt-2 h-3 w-full" />
            <Bar className="mt-1.5 h-3 w-2/3" />
          </div>
          <div className="surface-2 bd rounded-xl border p-3.5">
            <Bar className="h-2.5 w-20" />
            <Bar className="mt-2 h-3 w-full" />
            <Bar className="mt-1.5 h-3 w-3/4" />
          </div>
        </div>
      </div>

      {/* Insight cards */}
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }).map((_, index) => (
          <div key={index} className="surface bd rounded-2xl border">
            <div className="flex items-center gap-3 px-5 py-3.5">
              <Bar className="h-8 w-8 shrink-0 rounded-[10px]" />
              <div className="min-w-0 flex-1 space-y-1.5">
                <Bar className="h-3.5 w-36" />
                <Bar className="h-2.5 w-56 max-w-full" />
              </div>
            </div>
            <div className="bd space-y-2 border-t px-5 py-4">
              <Bar className="h-3 w-full" />
              <Bar className="h-3 w-11/12" />
              <Bar className="h-3 w-2/3" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
