'use client';

import { useState } from 'react';
import { ThumbsDown, ThumbsUp } from 'lucide-react';

import { submitAiFeedback, type AiFeedbackRating, type AiGeneration } from '@/features/ai/ai-insights';

/* ============================================================
   AI FEEDBACK BUTTONS

   Thumbs up/down on one stored generation, through
   `POST /crm/ai-insights/generations/{id}/feedback`. Shared by
   the record AI panel and the Next Best Action queue.
   ============================================================ */

export default function AiFeedbackButtons({ generation }: { generation: AiGeneration }) {
  const [rating, setRating] = useState(generation.feedback_rating);
  const [busy, setBusy] = useState(false);

  async function rate(next: AiFeedbackRating) {
    if (busy) return;
    setBusy(true);
    try {
      await submitAiFeedback(generation.id, next);
      setRating(next);
    } catch {
      // Feedback is a courtesy, not a blocking action — fail silently.
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        aria-label="Helpful"
        aria-pressed={rating === 'UP'}
        onClick={() => void rate('UP')}
        className={`rounded-md p-1 transition hover:opacity-70 ${rating === 'UP' ? 'text-emerald-600' : 'txt-faint'}`}
      >
        <ThumbsUp className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
      <button
        type="button"
        aria-label="Not helpful"
        aria-pressed={rating === 'DOWN'}
        onClick={() => void rate('DOWN')}
        className={`rounded-md p-1 transition hover:opacity-70 ${rating === 'DOWN' ? 'text-rose-600' : 'txt-faint'}`}
      >
        <ThumbsDown className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
