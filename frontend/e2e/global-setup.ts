import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

import { seedTenant } from './seed';
import { SEED_FILE } from './fixtures';

/**
 * Build the tenant once, before any spec runs.
 *
 * Written to disk rather than held in module state because Playwright runs
 * specs in separate worker processes, which do not share memory with this one.
 */
export default async function globalSetup(): Promise<void> {
  const seed = await seedTenant();
  mkdirSync(dirname(SEED_FILE), { recursive: true });
  writeFileSync(SEED_FILE, JSON.stringify(seed, null, 2), 'utf-8');
  console.log(`[e2e] seeded ${seed.organizationName}`);
}
