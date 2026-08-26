import Link from 'next/link';

/* ============================================================
   JOURNEY EMPTY STATE
   Shown when there are no open opportunities. The outlined
   funnel echoes the real one so the page reads as "not filled
   yet" rather than "broken".
   ============================================================ */

/** Widths and bottom-edge insets of the four outline rows. */
const OUTLINE_ROWS = [
  { width: '100%', taper: 9 },
  { width: '82%', taper: 10 },
  { width: '66%', taper: 11 },
  { width: '48%', taper: 0 },
];

export default function JourneyEmptyState() {
  return (
    <div className="anim-fade-up flex flex-col items-center px-8 py-20 text-center">
      <div className="mb-[26px] flex w-[260px] flex-col items-center gap-2">
        {OUTLINE_ROWS.map(row => (
          <div
            key={row.width}
            className="bd h-11 rounded-xl border-[1.5px] border-dashed"
            style={{
              width: row.width,
              clipPath: row.taper
                ? `polygon(0 0, 100% 0, ${100 - row.taper}% 100%, ${row.taper}% 100%)`
                : undefined,
            }}
          />
        ))}
      </div>

      <h2 className="txt font-display text-[22px] font-extrabold tracking-[-0.02em]">
        Your journey starts with one lead
      </h2>
      <p className="txt-muted mt-2 max-w-[420px] text-[13.5px] leading-[1.6]">
        No open opportunities yet. Add your first lead and this funnel will start filling — you&apos;ll
        see value, conversion and momentum build stage by stage.
      </p>

      <div className="mt-[22px] flex gap-2.5">
        <Link
          href="/leads"
          className="rounded-xl px-5 py-[11px] text-[13.5px] font-semibold text-white transition hover:opacity-90"
          style={{
            background: 'var(--accent)',
            boxShadow: '0 10px 24px -12px rgba(109, 40, 217, 0.7)',
          }}
        >
          Add your first lead
        </Link>
        <Link
          href="/lead-sources"
          className="ctl px-5 py-[11px] text-[13.5px] font-semibold transition hover:opacity-80"
        >
          Import from CSV
        </Link>
      </div>
    </div>
  );
}
