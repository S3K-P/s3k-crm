// features/ai/insights — barrel export
// Frontend-only AI Insights module: types, curated demo reports and
// the local query-resolution utility. No backend or AI provider.
export * from './types';
export * from './generate';
export {
  ANALYSIS_CAPABILITIES,
  INSIGHT_REPORTS,
  STAGE_ORDER,
  SUGGESTED_PROMPTS,
} from './mock-data';
