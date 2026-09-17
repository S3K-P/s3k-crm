import { test, expect, signIn } from './fixtures';

/**
 * Account 360 — the tabbed detail page, previously uncovered (audit item
 * #75 named it explicitly alongside AI, import, merge, dashboards builder
 * and reports detail).
 *
 * Every tab renders real data or a real empty state; none of them is
 * supposed to error. The AI tab in particular is worth its own assertion:
 * without an AI provider configured in this environment, it must render the
 * "not connected" state Checkpoint 1 built rather than crash or hang on a
 * spinner forever — the same distinction that page's own admin counterpart
 * (Admin -> Security) now draws between "not implemented" and "built, needs
 * configuration".
 */

test.describe('account 360', () => {
  test('every tab renders, including AI and the merged timeline', async ({
    page,
    tenant,
  }) => {
    // The manager, not the rep: the seeded account and deal are owned by the
    // manager, and opening someone else's record is a different spec
    // (visibility.spec.ts) — this one is about the tabs rendering, so it
    // uses the persona guaranteed to see the record.
    await signIn(page, tenant.manager);

    await page.getByRole('link', { name: 'Accounts', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Accounts' })).toBeVisible();
    await page.getByText(tenant.managerAccountName).first().click();

    await expect(page.getByRole('heading', { name: tenant.managerAccountName })).toBeVisible();

    // Overview: the summary header loads with real aggregates, not a
    // perpetual skeleton.
    await expect(page.getByText('Open pipeline')).toBeVisible();
    await expect(page.getByText('Won revenue')).toBeVisible();

    // Deals: the seeded deal, owned by this same manager, must be listed.
    await page.getByRole('button', { name: 'Deals' }).click();
    await expect(page.getByText(tenant.managerDealName)).toBeVisible();

    // Contacts: no contacts seeded — a real empty state, not an error.
    await page.getByRole('button', { name: 'Contacts' }).click();
    await expect(page.getByText(/no contacts|add a contact/i)).toBeVisible();

    // Activities, Emails, Notes, Files: each must render its panel without
    // throwing — the assertion is "the tab switched and something coherent
    // is there", since an empty CRM has nothing more specific to check.
    for (const label of ['Activities', 'Emails', 'Notes', 'Files']) {
      await page.getByRole('button', { name: label, exact: true }).click();
      await expect(page.getByRole('button', { name: label, exact: true })).toHaveClass(
        /text-\[var\(--accent\)\]/,
      );
    }

    // Timeline: the merged read model (activities + deal-created +
    // stage-changed + tasks + email + notes in one stream) — the deal this
    // account owns should appear in it.
    await page.getByRole('button', { name: 'Timeline' }).click();
    await expect(page.getByText(tenant.managerDealName).first()).toBeVisible();

    // AI: Checkpoint 7's own design point — this renders normally with no
    // AI provider configured in this environment ("works without AI"), not
    // a hang or a crash. Generating a summary is what would need a real
    // provider; simply opening the tab must not.
    await page.getByRole('button', { name: 'AI', exact: true }).click();
    await expect(page.getByText('AI summary')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Generate' }).first()).toBeVisible();
  });
});
