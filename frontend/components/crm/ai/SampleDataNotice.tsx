import { FlaskConical } from 'lucide-react';

/* ============================================================
   SAMPLE DATA NOTICE

   AI Insights and Next Best Action render a **design preview**.
   The accounts, deal values, risks and recommendations on those
   two screens come from a fixture in `features/ai/`, not from
   this organization's CRM — no query reaches the database and
   no AI provider is called.

   Both pages were removed once for exactly that reason: shown
   inside the signed-in application, beside real records and
   with nothing to mark them, an invented "at risk, ₹45L
   exposed" reads as a finding about a real customer. They are
   back so the interface can be seen and demonstrated, and this
   banner is the condition of their being back — it is what
   separates a design preview from a false report.

   Remove this component only together with the fixtures, when
   these screens are wired to real generation.
   ============================================================ */

export default function SampleDataNotice() {
  return (
    <div
      role="note"
      className="bd flex items-start gap-2.5 rounded-xl border border-amber-400/50 px-3.5 py-2.5"
      style={{ background: 'color-mix(in srgb, #f59e0b 10%, transparent)' }}
    >
      <FlaskConical
        className="mt-px h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400"
        aria-hidden="true"
      />
      <p className="txt text-[12.5px] font-medium leading-relaxed">
        <span className="font-bold">Design preview — sample data.</span>{' '}
        <span className="txt-muted">
          The companies, values and recommendations below are illustrative and are
          not drawn from your CRM. Nothing here reflects real records.
        </span>
      </p>
    </div>
  );
}
