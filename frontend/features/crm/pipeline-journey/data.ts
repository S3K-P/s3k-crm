/* ============================================================
   PIPELINE JOURNEY — PRESENTATION

   What is left in this file is **how the funnel looks**, not what
   it says. Geometry, gradients and tooltip captions live here;
   every count, value, rate and delta now comes from the API via
   `use-journey-data.ts`.

   It used to hold both. That was the problem: the fabricated
   figures were indistinguishable from configuration, so a page
   showing "263 opportunities" against an organization with none
   looked like a working feature rather than a placeholder. See
   CR06 — invented metrics rendered beside real ones get acted on.

   Geometry is computed from a row's **position**, because the
   number of rows is whatever the tenant configured: an
   organization with three stages and one with nine both get a
   funnel that tapers evenly from top to bottom.
   ============================================================ */

import type { JourneyFocusMeta, JourneyStage, StageDetailLevel } from './types';

/** The core figures a row carries before presentation is applied. */
export interface StageCore {
  id: string;
  label: string;
  count: number;
  value: string;
  conversion: number | null;
  movement: number | null;
}

/**
 * The funnel's colour ramp, widest row to narrowest.
 *
 * Sampled by position rather than indexed by stage name, so it degrades
 * sensibly for any row count: three stages take the first, middle and last
 * entries; ten stages repeat the darkest end rather than running out.
 */
const GRADIENTS = [
  'from-violet-900 to-violet-700',
  'from-violet-700 to-violet-600',
  'from-violet-600 to-purple-600',
  'from-purple-600 to-fuchsia-600',
  'from-fuchsia-600 to-pink-600',
] as const;

/** Conversion-figure colours, matched to the ramp above for contrast. */
const CONVERSION_COLORS = ['#c4b5fd', '#ddd6fe', '#f0abfc', '#f5d0fe', '#fbcfe8'] as const;

/** Widest and narrowest row, as a percentage of the container. */
const WIDEST_PCT = 100;
const NARROWEST_PCT = 46;

function sample<T>(ramp: readonly T[], index: number, total: number): T {
  if (total <= 1) return ramp[0];
  const position = index / (total - 1);
  return ramp[Math.min(ramp.length - 1, Math.round(position * (ramp.length - 1)))];
}

/**
 * How much detail a row can show before it is too narrow to hold it.
 *
 * Driven by the row's own width rather than its index: the same rule then
 * applies whether the funnel has four rows or twelve.
 */
function detailFor(widthPct: number): StageDetailLevel {
  if (widthPct >= 78) return 'full';
  if (widthPct >= 60) return 'compact';
  return 'minimal';
}

/** Apply the funnel's geometry and colour to one row's real figures. */
export function decorateStage(core: StageCore, index: number, total: number): JourneyStage {
  const span = WIDEST_PCT - NARROWEST_PCT;
  const widthPct =
    total <= 1 ? WIDEST_PCT : WIDEST_PCT - (span * index) / (total - 1);
  const isTerminal = index === total - 1;

  return {
    ...core,
    position: index + 1,
    widthPct,
    // The taper closes the gap to the next row's width, so the trapezoid's
    // lower edge meets the row beneath it instead of guessing an angle.
    taperPct: isTerminal ? 0 : span / (total - 1) / 2,
    gradient: sample(GRADIENTS, index, total),
    conversionColor: sample(CONVERSION_COLORS, index, total),
    detail: detailFor(widthPct),
    minimalCaption: '',
    tooltipLabels: { count: 'Deals', value: 'Value', conversion: 'Conversion' },
    // No footnote: the per-stage colour it used to carry ("avg. 6 days in
    // stage", "5 proposals expire this week") was invented, and there is no
    // aggregate behind either claim.
    tooltipFootnote: 'Click to open this stage in the opportunity list',
    isTerminal,
  };
}

/**
 * Drawer header copy for a stage, built from that stage's real figures.
 *
 * Takes the row rather than a lookup table: the previous version keyed
 * hardcoded subtitles off five fixed stage names, which no tenant is obliged
 * to use, and every one of those subtitles quoted a fabricated number.
 */
export function getFocusMeta(stage: JourneyStage | undefined): JourneyFocusMeta {
  if (!stage) {
    return { title: 'Opportunities', subtitle: '' };
  }

  const deals = `${stage.count} ${stage.count === 1 ? 'opportunity' : 'opportunities'}`;
  const value = stage.value && stage.value !== '—' ? ` · ${stage.value}` : '';

  return { title: stage.label, subtitle: `${deals}${value}` };
}
