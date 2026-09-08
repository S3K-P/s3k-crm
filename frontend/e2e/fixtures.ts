import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { test as base, expect, type Page } from '@playwright/test';

import type { SeedResult, SeededPerson } from './seed';

/** Where `global-setup` leaves the seeded tenant for the workers to read. */
export const SEED_FILE = join(process.cwd(), '.playwright', 'seed.json');

export function seed(): SeedResult {
  return JSON.parse(readFileSync(SEED_FILE, 'utf-8')) as SeedResult;
}

/**
 * Sign in through the real login form.
 *
 * Deliberately not a token injected into storage: the login form and the
 * cookie exchange behind it are themselves part of what these tests cover,
 * and every spec that skipped them would stop noticing when they broke.
 */
export async function signIn(page: Page, person: SeededPerson): Promise<void> {
  await page.goto('/login');
  await page.getByLabel('Email').fill(person.email);
  await page.getByLabel('Password').fill(person.password);
  await page.getByRole('button', { name: 'Sign in' }).click();

  // S3K is a platform with products in it, so signing in lands on the app
  // picker rather than inside the CRM. Asserting that step rather than
  // skipping past it means a regression that strands people on the workspace
  // shows up here.
  await expect(page.getByRole('region', { name: 'Your apps' })).toBeVisible();
  await openCrm(page);
}

/** Enter the CRM from the workspace. */
export async function openCrm(page: Page): Promise<void> {
  await page.getByRole('link', { name: /S3K CRM/ }).click();
  await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible();
}

export async function signOut(page: Page): Promise<void> {
  await page.getByRole('button', { name: /^Account menu for/ }).click();
  await page.getByRole('menuitem', { name: 'Sign out' }).click();
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
}

/** Adds the seeded tenant to every test, so no spec re-reads the file itself. */
export const test = base.extend<{ tenant: SeedResult }>({
  tenant: async ({}, use) => {
    await use(seed());
  },
});

export { expect } from '@playwright/test';
