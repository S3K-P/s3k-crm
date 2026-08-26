/* ============================================================
   PIPELINE JOURNEY — TYPES
   Narrative view of the sales funnel: one row per stage, the
   quarterly goal, week-over-week momentum and the AI-prioritised
   "what needs attention" queue.

   Currency is pre-formatted in Indian notation (₹L / ₹Cr) because
   the funnel renders values verbatim; swap the mock data for API
   values in the same shape when the backend lands.
   ============================================================ */

/** The five funnel rows, widest to narrowest. */
export type JourneyStageId = 'leads' | 'qualified' | 'proposal' | 'negotiation' | 'won';

/** Curated cross-stage cuts surfaced by the attention cards. */
export type AttentionPresetId = 'stuck' | 'closing' | 'growth' | 'ontrack';

/** Anything the deals drawer can be focused on. */
export type JourneyFocusId = JourneyStageId | AttentionPresetId;

/**
 * How much of a stage row fits before the funnel narrows past it.
 * `full` keeps the metric captions, `compact` drops them and
 * `minimal` collapses value + conversion into a single column.
 */
export type StageDetailLevel = 'full' | 'compact' | 'minimal';

export interface JourneyDeal {
  id: string;
  /** Account the opportunity belongs to */
  account: string;
  /** Opportunity name */
  name: string;
  /** Pre-formatted deal value, e.g. `₹8.4L` */
  value: string;
  /** Owning rep, or a weighting note in forecast cuts */
  owner: string;
  /** Age/urgency line, e.g. `11 days in stage` */
  age: string;
  /** Stage badge label */
  stage: string;
  /** Trailing qualifier, e.g. `80% · verbal yes` */
  note: string;
}

export interface JourneyStage {
  id: JourneyStageId;
  /** 1-based position, shown in the row badge */
  position: number;
  label: string;
  /** Open opportunities sitting in the stage */
  count: number;
  /** Pre-formatted stage value */
  value: string;
  /** Share of the stage that reaches the next one */
  conversion: number;
  /** Net opportunities gained (or lost) this week */
  movement: number;
  /** Funnel row width as a percentage of the widest row */
  widthPct: number;
  /** Horizontal inset of the trapezoid's bottom edge, in percent */
  taperPct: number;
  /** Tailwind `from-… to-…` pair for the row fill */
  gradient: string;
  /** Colour for the conversion figure against the row fill */
  conversionColor: string;
  detail: StageDetailLevel;
  /** Caption under the value on `minimal` rows */
  minimalCaption: string;
  /** Labels used by the hover tooltip's metric grid */
  tooltipLabels: { count: string; value: string; conversion: string };
  /** Closing line of the hover tooltip */
  tooltipFootnote: string;
  /** Terminal stage — squared-off bottom instead of a taper */
  isTerminal?: boolean;
}

/** Header copy for whatever the drawer is currently focused on. */
export interface JourneyFocusMeta {
  title: string;
  subtitle: string;
}

export interface MomentumMetric {
  id: string;
  label: string;
  /** Pre-formatted headline figure */
  value: string;
  /** Bar fill as a percentage */
  fillPct: number;
  /** Tailwind `from-… to-…` pair for the bar fill */
  gradient: string;
  /** Week-over-week change, e.g. `↑ 18%` */
  delta: string;
  /** `true` when the change is a good thing */
  positive: boolean;
}

export interface AttentionItem {
  id: string;
  /** Drawer cut opened by the card */
  preset: AttentionPresetId;
  title: string;
  detail: string;
  cta: string;
  /** Tailwind `from-… to-…` pair for the icon tile */
  gradient: string;
  /** Border colour on hover */
  hoverBorder: string;
  /** Shadow colour on hover */
  hoverShadow: string;
}

/** Headline counters the hero and KPI row animate up to on mount. */
export interface JourneyTotals {
  /** Total open pipeline in ₹ crore */
  pipelineCr: number;
  /** Open opportunities across every stage */
  openDeals: number;
  /** Win rate percentage */
  winRatePct: number;
  /** Progress toward the quarterly revenue goal, as a percentage */
  goalPct: number;
}

export interface JourneyGoal {
  /** Quarter label, e.g. `Q3 FY26` */
  period: string;
  /** Pre-formatted target */
  target: string;
  /** Pre-formatted amount won so far */
  won: string;
  /** Pre-formatted shortfall */
  gap: string;
  daysRemaining: number;
  wonThisMonth: string;
  expected: string;
  /** Closing nudge shown beneath the stat grid */
  headline: string;
  supporting: string;
}

/** One figure in the strip under the funnel. */
export interface JourneyFunnelStat {
  id: string;
  label: string;
  value: string;
  /** Renders the figure in the danger colour (e.g. the biggest stage drop) */
  danger?: boolean;
}

/** Copy + side tiles for the gradient hero banner. */
export interface JourneyHeroContent {
  /** Line under the greeting, e.g. `Q3 FY26, 41 days in.` */
  periodLine: string;
  /** Month-over-month pipeline change, e.g. `↑ 18% this month` */
  pipelineDelta: string;
  /** Goal caption under the progress bar */
  goalCaption: string;
  /** "Best next move" body copy */
  nextMove: string;
  /** Label on the button that opens the `closing` drawer cut */
  nextMoveCta: string;
  /** The two glass stat tiles beside the next-move card */
  tiles: { id: string; value: string; label: string }[];
}

export interface JourneyKpi {
  id: 'pipeline' | 'deals' | 'winRate' | 'goal';
  label: string;
  /** Change line under the headline figure */
  delta: string;
  /** `positive` renders green, `accent` renders brand purple */
  deltaTone: 'positive' | 'accent';
  /** Footnote under the card's mini chart */
  caption: string;
  /** Tailwind `from-… to-…` pair for the icon tile */
  iconGradient: string;
}

/**
 * What the page renders. `loading` and `empty` are reachable as soon as
 * `useJourneyData` is pointed at the real endpoint; today the mock data
 * resolves synchronously so `ready` is what you normally see.
 */
export type JourneyStatus = 'loading' | 'ready' | 'empty';
