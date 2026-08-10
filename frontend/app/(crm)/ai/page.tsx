import { redirect } from 'next/navigation';

/* ============================================================
   AI SECTION INDEX
   The AI area has no landing page of its own — it exists so the
   /ai breadcrumb segment resolves to a real route instead of a
   404. Sends visitors to the first capability in the section.
   ============================================================ */

export default function AiIndexPage() {
  redirect('/ai/insights');
}
