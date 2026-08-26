/* ============================================================
   JOURNEY SKELETON
   Placeholder blocks in the same rhythm as the loaded page —
   hero, KPI row, funnel + side column — so nothing jumps when
   the data lands.
   ============================================================ */

export default function JourneySkeleton() {
  return (
    <div className="flex flex-col gap-5 p-6 lg:p-8">
      <div className="surface-2 anim-shimmer h-[150px] rounded-[26px]" />

      <div className="grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(230px,1fr))]">
        {[0.1, 0.2, 0.3, 0.4].map(delay => (
          <div
            key={delay}
            className="surface-2 anim-shimmer h-28 rounded-[20px]"
            style={{ animationDelay: `${delay}s` }}
          />
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-[1.55fr_1fr]">
        <div
          className="surface-2 anim-shimmer h-[470px] rounded-[26px]"
          style={{ animationDelay: '0.15s' }}
        />
        <div
          className="surface-2 anim-shimmer h-[470px] rounded-[26px]"
          style={{ animationDelay: '0.25s' }}
        />
      </div>

      <p className="txt-faint text-center text-[12.5px] font-semibold">
        Assembling your pipeline journey…
      </p>
    </div>
  );
}
