import type {
  AttentionItem,
  AttentionPresetId,
  JourneyDeal,
  JourneyFocusId,
  JourneyFocusMeta,
  JourneyFunnelStat,
  JourneyGoal,
  JourneyHeroContent,
  JourneyKpi,
  JourneyStage,
  JourneyStageId,
  JourneyTotals,
  MomentumMetric,
} from './types';

/* ============================================================
   PIPELINE JOURNEY — MOCK DATA
   Everything the page renders lives here so there is exactly one
   place to swap for API responses. Money is pre-formatted in
   Indian notation (₹L / ₹Cr) — see ./types.ts.
   ============================================================ */

export const JOURNEY_TOTALS: JourneyTotals = {
  pipelineCr: 4.38,
  openDeals: 263,
  winRatePct: 34,
  goalPct: 73,
};

export const JOURNEY_HERO: JourneyHeroContent = {
  periodLine: "Here's how your business is progressing — Q3 FY26, 41 days in.",
  pipelineDelta: '↑ 18% this month',
  goalCaption: "₹47.5L won · you're ₹17.5L from target with 49 days left.",
  nextMove: 'Close Northgate Fintech (₹8.4L) — 3 more wins put you ahead of plan.',
  nextMoveCta: 'Review 3 deals →',
  tiles: [
    { id: 'velocity', value: '26 days', label: 'Avg. velocity' },
    { id: 'wins', value: '4 wins', label: 'This week' },
  ],
};

export const JOURNEY_KPIS: JourneyKpi[] = [
  {
    id: 'pipeline',
    label: 'Pipeline Value',
    delta: '↑ ₹58L created this week',
    deltaTone: 'positive',
    caption: 'Last 7 weeks of creation',
    iconGradient: 'from-amber-500 to-orange-500',
  },
  {
    id: 'deals',
    label: 'Active Deals',
    delta: '↑ 23 moved forward',
    deltaTone: 'positive',
    caption: 'Across 4 open stages',
    iconGradient: 'from-sky-500 to-blue-600',
  },
  {
    id: 'winRate',
    label: 'Win Rate',
    delta: '↑ 4.2 pts vs last quarter',
    deltaTone: 'positive',
    caption: '26 won of 76 closed',
    iconGradient: 'from-emerald-500 to-green-600',
  },
  {
    id: 'goal',
    label: 'Revenue Goal',
    delta: 'On track · 49 days left',
    deltaTone: 'accent',
    caption: '₹47.5L of ₹65L',
    iconGradient: 'from-violet-600 to-indigo-600',
  },
];

/* ── The funnel ──────────────────────────────────────────────
   `widthPct` narrows each row and `taperPct` insets its bottom
   edge, so consecutive rows read as one continuous funnel.
   ──────────────────────────────────────────────────────────── */

export const JOURNEY_STAGES: JourneyStage[] = [
  {
    id: 'leads',
    position: 1,
    label: 'Leads',
    count: 142,
    value: '₹2.10Cr',
    conversion: 46,
    movement: 18,
    widthPct: 100,
    taperPct: 9,
    gradient: 'from-violet-900 to-violet-700',
    conversionColor: '#c4b5fd',
    detail: 'full',
    minimalCaption: '',
    tooltipLabels: { count: 'Deals', value: 'Value', conversion: 'Conversion' },
    tooltipFootnote: 'Avg. 6 days in stage · click to open filtered opportunities',
  },
  {
    id: 'qualified',
    position: 2,
    label: 'Qualified',
    count: 65,
    value: '₹1.32Cr',
    conversion: 58,
    movement: 11,
    widthPct: 82,
    taperPct: 10,
    gradient: 'from-violet-700 to-violet-600',
    conversionColor: '#ddd6fe',
    detail: 'full',
    minimalCaption: '',
    tooltipLabels: { count: 'Deals', value: 'Value', conversion: 'Conversion' },
    tooltipFootnote: 'Avg. 9 days in stage · 4 need a discovery call',
  },
  {
    id: 'proposal',
    position: 3,
    label: 'Proposal',
    count: 38,
    value: '₹64.5L',
    conversion: 47,
    movement: 6,
    widthPct: 66,
    taperPct: 11,
    gradient: 'from-violet-600 to-purple-600',
    conversionColor: '#f0abfc',
    detail: 'compact',
    minimalCaption: '',
    tooltipLabels: { count: 'Deals', value: 'Value', conversion: 'Conversion' },
    tooltipFootnote: 'Avg. 14 days in stage · 5 proposals expire this week',
  },
  {
    id: 'negotiation',
    position: 4,
    label: 'Negotiation',
    count: 18,
    value: '₹31.2L',
    conversion: 62,
    movement: -2,
    widthPct: 52,
    taperPct: 12,
    gradient: 'from-purple-600 to-fuchsia-600',
    conversionColor: '#fbcfe8',
    detail: 'minimal',
    minimalCaption: '62% converts',
    tooltipLabels: { count: 'Deals', value: 'Value', conversion: 'Conversion' },
    tooltipFootnote: '2 slipped back to Proposal · 3 close within 10 days',
  },
  {
    id: 'won',
    position: 5,
    label: 'Won',
    count: 26,
    value: '₹47.5L',
    conversion: 34,
    movement: 4,
    widthPct: 40,
    taperPct: 0,
    gradient: 'from-emerald-600 to-emerald-500',
    conversionColor: '#ffffff',
    detail: 'minimal',
    minimalCaption: 'this quarter',
    tooltipLabels: { count: 'Deals', value: 'Revenue', conversion: 'Win rate' },
    tooltipFootnote: '73% of your ₹65L quarterly goal',
    isTerminal: true,
  },
];

export const JOURNEY_FUNNEL_STATS: JourneyFunnelStat[] = [
  { id: 'leadToWon', label: 'Lead → Won', value: '7.8%' },
  { id: 'forecast', label: 'Weighted forecast', value: '₹61.4L' },
  { id: 'avgDeal', label: 'Avg. deal size', value: '₹1.83L' },
  { id: 'drop', label: 'Biggest stage drop', value: 'Proposal', danger: true },
];

export const JOURNEY_GOAL: JourneyGoal = {
  period: 'Q3 FY26',
  target: '₹65L',
  won: '₹47.5L',
  gap: '₹17.5L',
  daysRemaining: 49,
  wonThisMonth: '₹14.2L',
  expected: '₹9.6L',
  headline: "You're ₹17.5L away from your target.",
  supporting: '3 more wins at your average deal size could put you ahead of plan.',
};

export const JOURNEY_MOMENTUM: MomentumMetric[] = [
  {
    id: 'created',
    label: 'Pipeline created',
    value: '₹58L',
    fillPct: 86,
    gradient: 'from-violet-700 to-purple-500',
    delta: '↑ 18%',
    positive: true,
  },
  {
    id: 'forward',
    label: 'Deals moving forward',
    value: '23',
    fillPct: 68,
    gradient: 'from-sky-500 to-sky-400',
    delta: '↑ 9%',
    positive: true,
  },
  {
    id: 'stuck',
    label: 'Deals stuck 14+ days',
    value: '7',
    fillPct: 34,
    gradient: 'from-rose-500 to-rose-400',
    delta: '↑ 2',
    positive: false,
  },
  {
    id: 'won',
    label: 'Deals won',
    value: '4',
    fillPct: 52,
    gradient: 'from-emerald-600 to-emerald-400',
    delta: '↑ 1',
    positive: true,
  },
];

export const JOURNEY_ATTENTION: AttentionItem[] = [
  {
    id: 'stuck',
    preset: 'stuck',
    title: "4 deals haven't moved in 14 days",
    detail: '₹11.8L at risk across Proposal and Negotiation',
    cta: 'Review stalled deals →',
    gradient: 'from-rose-500 to-rose-400',
    hoverBorder: '#fda4af',
    hoverShadow: '0 18px 34px -20px rgba(244, 63, 94, 0.45)',
  },
  {
    id: 'closing',
    preset: 'closing',
    title: '3 high-value deals close to closing',
    detail: '₹19.7L combined · all in Negotiation',
    cta: 'Push them over the line →',
    gradient: 'from-amber-500 to-orange-500',
    hoverBorder: '#fdba74',
    hoverShadow: '0 18px 34px -20px rgba(249, 115, 22, 0.45)',
  },
  {
    id: 'growth',
    preset: 'growth',
    title: 'Pipeline increased 18% this month',
    detail: '₹58L created this week — best week of the quarter',
    cta: "See what's working →",
    gradient: 'from-emerald-500 to-green-600',
    hoverBorder: '#a7f3d0',
    hoverShadow: '0 18px 34px -20px rgba(16, 185, 129, 0.45)',
  },
  {
    id: 'ontrack',
    preset: 'ontrack',
    title: 'On track to reach your quarterly goal',
    detail: 'Weighted forecast ₹61.4L vs ₹65L target',
    cta: 'View forecast breakdown →',
    gradient: 'from-violet-600 to-indigo-600',
    hoverBorder: '#c4b5fd',
    hoverShadow: '0 18px 34px -20px rgba(109, 40, 217, 0.45)',
  },
];

/* ── Drawer contents ─────────────────────────────────────────
   One list per stage row plus one per attention card, keyed by
   the id the row/card opens.
   ──────────────────────────────────────────────────────────── */

const STAGE_DEALS: Record<JourneyStageId, JourneyDeal[]> = {
  leads: [
    { id: 'l1', account: 'Meridian Logistics',  name: 'Fleet telematics rollout', value: '₹4.2L', owner: 'Aditi R.',   age: '3 days old', stage: 'Leads', note: '20% · inbound' },
    { id: 'l2', account: 'Kaveri Textiles',     name: 'ERP migration — phase 1',  value: '₹2.8L', owner: 'Nikhil M.',  age: '5 days old', stage: 'Leads', note: '20% · webinar' },
    { id: 'l3', account: 'Suryodaya Energy',    name: 'Field service CRM',        value: '₹6.1L', owner: 'Sarthak K.', age: '1 day old',  stage: 'Leads', note: '25% · referral' },
    { id: 'l4', account: 'Blue Harbour Retail', name: 'Loyalty platform pilot',   value: '₹1.9L', owner: 'Priya S.',   age: '6 days old', stage: 'Leads', note: '15% · outbound' },
    { id: 'l5', account: 'Arcus Manufacturing', name: 'Dealer portal',            value: '₹3.4L', owner: 'Aditi R.',   age: '2 days old', stage: 'Leads', note: '20% · event' },
  ],
  qualified: [
    { id: 'q1', account: 'Northgate Fintech',    name: 'Collections automation', value: '₹8.4L', owner: 'Sarthak K.', age: '11 days in stage', stage: 'Qualified', note: '45% · budget confirmed' },
    { id: 'q2', account: 'Trisent Pharma',       name: 'Field rep enablement',   value: '₹5.6L', owner: 'Nikhil M.',  age: '8 days in stage',  stage: 'Qualified', note: '40% · champion found' },
    { id: 'q3', account: 'Vantara Hospitality',  name: 'Group booking CRM',      value: '₹3.9L', owner: 'Priya S.',   age: '14 days in stage', stage: 'Qualified', note: '35% · needs demo' },
    { id: 'q4', account: 'Meridian Logistics',   name: 'Route analytics add-on', value: '₹2.2L', owner: 'Aditi R.',   age: '4 days in stage',  stage: 'Qualified', note: '45% · expansion' },
  ],
  proposal: [
    { id: 'p1', account: 'Suryodaya Energy',    name: 'Field service CRM — 120 seats', value: '₹9.8L', owner: 'Sarthak K.', age: '16 days in stage', stage: 'Proposal', note: '55% · pricing review' },
    { id: 'p2', account: 'Kaveri Textiles',     name: 'ERP migration — full scope',    value: '₹6.4L', owner: 'Nikhil M.',  age: '21 days in stage', stage: 'Proposal', note: '50% · legal review' },
    { id: 'p3', account: 'Blue Harbour Retail', name: 'Loyalty platform — annual',     value: '₹4.1L', owner: 'Priya S.',   age: '9 days in stage',  stage: 'Proposal', note: '45% · sent Monday' },
    { id: 'p4', account: 'Arcus Manufacturing', name: 'Dealer portal + API',           value: '₹5.2L', owner: 'Aditi R.',   age: '12 days in stage', stage: 'Proposal', note: '50% · security questions' },
  ],
  negotiation: [
    { id: 'n1', account: 'Northgate Fintech',   name: 'Collections automation',   value: '₹8.4L', owner: 'Sarthak K.', age: '6 days in stage',  stage: 'Negotiation', note: '80% · verbal yes' },
    { id: 'n2', account: 'Trisent Pharma',      name: 'Field rep enablement',     value: '₹6.7L', owner: 'Nikhil M.',  age: '9 days in stage',  stage: 'Negotiation', note: '70% · terms redlined' },
    { id: 'n3', account: 'Vantara Hospitality', name: 'Group booking CRM',        value: '₹4.6L', owner: 'Priya S.',   age: '17 days in stage', stage: 'Negotiation', note: '55% · discount ask' },
    { id: 'n4', account: 'Meridian Logistics',  name: 'Fleet telematics rollout', value: '₹3.8L', owner: 'Aditi R.',   age: '4 days in stage',  stage: 'Negotiation', note: '75% · procurement' },
  ],
  won: [
    { id: 'w1', account: 'Helix Diagnostics', name: 'Lab network CRM',          value: '₹7.2L', owner: 'Sarthak K.', age: 'Closed 3 days ago', stage: 'Won', note: '100% · signed' },
    { id: 'w2', account: 'Orbit Freight',     name: 'Partner portal',           value: '₹5.4L', owner: 'Nikhil M.',  age: 'Closed 6 days ago', stage: 'Won', note: '100% · signed' },
    { id: 'w3', account: 'Casa Living',       name: 'Showroom CRM — 40 seats',  value: '₹3.1L', owner: 'Priya S.',   age: 'Closed last week',  stage: 'Won', note: '100% · signed' },
    { id: 'w4', account: 'Peninsula Agro',    name: 'Distributor tracking',     value: '₹2.6L', owner: 'Aditi R.',   age: 'Closed last week',  stage: 'Won', note: '100% · signed' },
  ],
};

const PRESET_DEALS: Record<AttentionPresetId, JourneyDeal[]> = {
  stuck: [
    { id: 's1', account: 'Kaveri Textiles',     name: 'ERP migration — full scope',    value: '₹6.4L', owner: 'Nikhil M.',  age: '21 days idle', stage: 'Proposal',    note: 'Last touch: 12 Aug' },
    { id: 's2', account: 'Vantara Hospitality', name: 'Group booking CRM',             value: '₹4.6L', owner: 'Priya S.',   age: '17 days idle', stage: 'Negotiation', note: 'Last touch: 16 Aug' },
    { id: 's3', account: 'Suryodaya Energy',    name: 'Field service CRM — 120 seats', value: '₹9.8L', owner: 'Sarthak K.', age: '16 days idle', stage: 'Proposal',    note: 'Last touch: 17 Aug' },
    { id: 's4', account: 'Vantara Hospitality', name: 'Group booking CRM',             value: '₹3.9L', owner: 'Priya S.',   age: '14 days idle', stage: 'Qualified',   note: 'Last touch: 19 Aug' },
  ],
  closing: [
    { id: 'c1', account: 'Northgate Fintech',  name: 'Collections automation',   value: '₹8.4L', owner: 'Sarthak K.', age: 'Closes in 6 days',  stage: 'Negotiation', note: '80% · verbal yes' },
    { id: 'c2', account: 'Trisent Pharma',     name: 'Field rep enablement',     value: '₹6.7L', owner: 'Nikhil M.',  age: 'Closes in 9 days',  stage: 'Negotiation', note: '70% · terms redlined' },
    { id: 'c3', account: 'Meridian Logistics', name: 'Fleet telematics rollout', value: '₹3.8L', owner: 'Aditi R.',   age: 'Closes in 11 days', stage: 'Negotiation', note: '75% · procurement' },
  ],
  growth: [
    { id: 'g1', account: 'Suryodaya Energy',    name: 'Field service CRM',        value: '₹6.1L', owner: 'Sarthak K.', age: 'Created 1 day ago',  stage: 'Leads', note: 'Referral' },
    { id: 'g2', account: 'Meridian Logistics',  name: 'Fleet telematics rollout', value: '₹4.2L', owner: 'Aditi R.',   age: 'Created 3 days ago', stage: 'Leads', note: 'Inbound' },
    { id: 'g3', account: 'Arcus Manufacturing', name: 'Dealer portal',            value: '₹3.4L', owner: 'Aditi R.',   age: 'Created 2 days ago', stage: 'Leads', note: 'Event' },
    { id: 'g4', account: 'Kaveri Textiles',     name: 'ERP migration — phase 1',  value: '₹2.8L', owner: 'Nikhil M.',  age: 'Created 5 days ago', stage: 'Leads', note: 'Webinar' },
  ],
  ontrack: [
    { id: 'o1', account: 'Northgate Fintech',   name: 'Collections automation',    value: '₹6.7L', owner: 'Weighted at 80%', age: 'Expected this month', stage: 'Negotiation', note: 'High confidence' },
    { id: 'o2', account: 'Trisent Pharma',      name: 'Field rep enablement',      value: '₹4.7L', owner: 'Weighted at 70%', age: 'Expected this month', stage: 'Negotiation', note: 'High confidence' },
    { id: 'o3', account: 'Suryodaya Energy',    name: 'Field service CRM',         value: '₹5.4L', owner: 'Weighted at 55%', age: 'Expected next month', stage: 'Proposal',    note: 'Medium confidence' },
    { id: 'o4', account: 'Everything else open', name: '253 remaining opportunities', value: '₹44.6L', owner: 'Weighted blend', age: 'Across the quarter', stage: 'Pipeline', note: 'Modelled' },
  ],
};

const FOCUS_META: Record<JourneyFocusId, JourneyFocusMeta> = {
  leads:       { title: 'Leads',            subtitle: '142 opportunities · ₹2.10Cr potential · 46% convert to Qualified' },
  qualified:   { title: 'Qualified',        subtitle: '65 opportunities · ₹1.32Cr potential · 58% reach Proposal' },
  proposal:    { title: 'Proposal',         subtitle: '38 opportunities · ₹64.5L potential · 47% reach Negotiation' },
  negotiation: { title: 'Negotiation',      subtitle: '18 opportunities · ₹31.2L potential · 62% close won' },
  won:         { title: 'Won this quarter', subtitle: '26 deals · ₹47.5L revenue · 73% of your ₹65L goal' },
  stuck:       { title: 'Stalled 14+ days',        subtitle: '4 deals · ₹11.8L at risk — no activity logged in two weeks' },
  closing:     { title: 'Close to closing',        subtitle: '3 high-value deals · ₹19.7L combined — all in Negotiation' },
  growth:      { title: 'New pipeline this week',  subtitle: '14 opportunities · ₹58L created — your best week of the quarter' },
  ontrack:     { title: 'Forecast breakdown',      subtitle: 'Weighted forecast ₹61.4L vs ₹65L target · 49 days remaining' },
};

const ALL_DEALS: Record<JourneyFocusId, JourneyDeal[]> = { ...STAGE_DEALS, ...PRESET_DEALS };

/** Header copy for the drawer cut currently in focus. */
export function getFocusMeta(focus: JourneyFocusId): JourneyFocusMeta {
  return FOCUS_META[focus];
}

/** Deals listed by the drawer for the cut currently in focus. */
export function getFocusDeals(focus: JourneyFocusId): JourneyDeal[] {
  return ALL_DEALS[focus] ?? [];
}
