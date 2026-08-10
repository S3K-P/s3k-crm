import { buildNbaDetail } from './detail';
import { NBA_RECORDS, REGENERATION_POOL } from './mock-data';
import type { NbaDetail, NbaRecord, RegeneratedRecommendation } from './types';

/* ============================================================
   NEXT BEST ACTION — LOCAL GENERATION UTILITIES

   These functions are the single boundary between the UI and
   the data source. They resolve entirely in the browser: no
   fetch, no API route, no AI provider, no environment config.

   The short delays exist only so the interface can demonstrate
   its loading states. Replacing these three functions with real
   calls later requires no change to the components above them.
   ============================================================ */

/** Artificial latency, used purely to exercise loading/skeleton UI. */
function delay(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/** Returns the full Next Best Action working set. */
export async function getMockNBARecords(): Promise<NbaRecord[]> {
  await delay(650);
  return NBA_RECORDS.map(record => ({ ...record }));
}

/** Synchronous accessor for derived values that must not wait (KPI seeding, tests). */
export function getNBARecordsSync(): NbaRecord[] {
  return NBA_RECORDS.map(record => ({ ...record }));
}

/** Builds the drawer-level opportunity intelligence for a single record. */
export async function getMockNBADetail(record: NbaRecord): Promise<NbaDetail> {
  await delay(320);
  return buildNbaDetail(record);
}

/**
 * Selects an alternate recommendation for the "Regenerate" demo action.
 * The alternate is drawn from a stage-appropriate pool so the replacement
 * stays commercially sensible for the record it belongs to.
 */
export async function generateMockNBARecommendation(
  record: NbaRecord,
): Promise<RegeneratedRecommendation> {
  await delay(900);

  const pool = REGENERATION_POOL[record.stage] ?? REGENERATION_POOL.Proposal;
  const alternatives = pool.filter(item => item.recommendation !== record.recommendation);
  const candidates = alternatives.length > 0 ? alternatives : pool;

  if (candidates.length === 0) {
    throw new Error('No alternate recommendation available for this stage');
  }

  // Rotate deterministically through the pool so repeated regeneration varies.
  const rotation = record.aiNotes.length % candidates.length;
  return candidates[rotation];
}
