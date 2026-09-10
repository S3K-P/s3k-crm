import { test, expect, signIn } from './fixtures';
import { RUN_ID } from './seed';

/**
 * The journey a rep actually makes: create a lead, find it, work it.
 *
 * One test rather than four, because the steps are only meaningful in
 * sequence — a lead that cannot be found after being created is the failure
 * worth catching, and splitting it would need each step to re-create the
 * record it depends on.
 */

test.describe('the daily journey', () => {
  test('a rep creates a lead and finds it again', async ({ page, tenant }) => {
    const leadSurname = `Prospect${RUN_ID}`;

    await signIn(page, tenant.rep);
    await page.getByRole('link', { name: 'Leads', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Leads' })).toBeVisible();

    await page.getByRole('button', { name: /new lead|add lead/i }).first().click();
    await page.getByLabel(/first name/i).fill('Casey');
    await page.getByLabel(/last name/i).fill(leadSurname);
    // Anchored at both ends: the list screen also carries the saved-view
    // toolbar, whose "Save view" button an unanchored /^save/ would match too.
    await page.getByRole('button', { name: /^(save|create)$/i }).click();

    // Back on the list, with the new record on it.
    await expect(page.getByText(leadSurname).first()).toBeVisible();

    // And reachable from a fresh page load, which is what proves it persisted
    // rather than merely appearing in local state.
    await page.reload();
    await expect(page.getByText(leadSurname).first()).toBeVisible();
  });

  test('the dashboard and reports load for someone with no records', async ({
    page,
    tenant,
  }) => {
    // An empty tenant is where "no data" bugs live: a chart dividing by zero,
    // a total of undefined, a page that never leaves its skeleton.
    await signIn(page, tenant.rep);

    await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();

    await page.goto('/reports');
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Pipeline by stage' })).toBeVisible();
    // A table renders even with nothing in it.
    await expect(page.locator('table')).toBeVisible();
  });

  test('navigation only offers what the person may open', async ({ page, tenant }) => {
    // The rep holds no `users` permission, so Admin must not be in the nav.
    // Hiding it is a UX decision the API re-checks, but a nav that offers a
    // dead end is still a bug.
    await signIn(page, tenant.rep);

    await expect(page.getByRole('link', { name: 'Leads', exact: true })).toBeVisible();
    await expect(page.getByRole('link', { name: 'Admin', exact: true })).toHaveCount(0);
  });
});
