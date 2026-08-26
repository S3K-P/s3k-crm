'use client';

import { useEffect, useState } from 'react';

/* ============================================================
   useCountUp
   Drives the headline counters from 0 to 1 over `duration` on a
   single requestAnimationFrame loop, eased so the numbers settle
   rather than stop dead. Returns the eased progress — callers
   multiply their own target by it, so every counter on the page
   lands together off one timer.

   Under `prefers-reduced-motion` it returns 1 immediately and
   never starts the loop.
   ============================================================ */

const easeOutCubic = (t: number) => 1 - Math.pow(1 - t, 3);

export function useCountUp(duration = 1400): number {
  const [progress, setProgress] = useState(0);

  useEffect(() => {
    // Settle on the final values instead of animating.
    //
    // Deferred through a **timer**, not `requestAnimationFrame`. rAF does not
    // run in a hidden tab, so the rAF version left every counter on the page
    // pinned at zero — permanently, and specifically for users who have asked
    // for reduced motion. A page reading "₹0 open pipeline" against a real
    // pipeline is a wrong number, not a missing animation, and it survived
    // until the tab was focused. Timers are throttled when hidden but they
    // still fire.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const settle = window.setTimeout(() => setProgress(1), 0);
      return () => window.clearTimeout(settle);
    }

    let frame = 0;
    const start = performance.now();

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      setProgress(easeOutCubic(t));
      if (t < 1) frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);

    // Browsers do not run rAF in a hidden tab, so without this the animation
    // never starts and every counter on the page renders — and *stays* — at
    // zero. That is far worse than an unanimated number: a backgrounded tab
    // would show "₹0 open pipeline" against a real pipeline, and it would
    // still say zero when the user came back to a tab that had, as far as the
    // browser was concerned, finished loading.
    //
    // The fallback fires shortly after the animation should have ended and
    // settles on the true values. When the tab is visible the loop has already
    // reached 1 by then and this is a no-op.
    const settle = window.setTimeout(() => setProgress(1), duration + 200);

    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(settle);
    };
  }, [duration]);

  return progress;
}
