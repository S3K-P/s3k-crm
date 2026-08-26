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
    // Settle on the final values instead of animating. This still goes through
    // a frame rather than setting state in the effect body: a synchronous
    // setState here would cascade a second render, and starting from 0 on both
    // server and client keeps hydration matched either way.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const settle = requestAnimationFrame(() => setProgress(1));
      return () => cancelAnimationFrame(settle);
    }

    let frame = 0;
    const start = performance.now();

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      setProgress(easeOutCubic(t));
      if (t < 1) frame = requestAnimationFrame(tick);
    };

    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [duration]);

  return progress;
}
