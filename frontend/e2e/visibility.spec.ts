import { test, expect, signIn, signOut } from './fixtures';

/**
 * Record-level visibility, seen through the browser.
 *
 * The backend has thorough coverage of this rule; what it cannot cover is
 * whether the screens honour it — whether a list, a total and a chart all
 * agree about what this person may see. That is the assertion here, and until
 * now nothing checked it above the API.
 *
 * The seeded deal is owned by the manager. The manager holds VIEW_ALL and must
 * see it; the rep owns nothing and must see neither the record nor its value
 * anywhere on the screen.
 */

test.describe('record visibility', () => {
  test('a manager sees the deal they own', async ({ page, tenant }) => {
    await signIn(page, tenant.manager);

    await page.getByRole('link', { name: 'Opportunities', exact: true }).click();

    await expect(page.getByText(tenant.managerDealName)).toBeVisible();
  });

  test('a rep does not see a colleague’s deal in the list', async ({ page, tenant }) => {
    await signIn(page, tenant.rep);

    await page.getByRole('link', { name: 'Opportunities', exact: true }).click();
    // Wait for the list to settle before asserting an absence, or the
    // assertion passes against a screen that has not loaded yet.
    await expect(page.getByRole('heading', { name: 'Opportunities' })).toBeVisible();

    await expect(page.getByText(tenant.managerDealName)).toHaveCount(0);
  });

  test('the same report totals differently for each of them', async ({ page, tenant }) => {
    // The property the whole reporting layer rests on: a shared report is a
    // question, and the answer belongs to whoever asked it.
    // A currency total carries the CRM's display currency, so an empty one
    // reads "₹0" rather than a bare "0" (see `frontend/lib/currency.ts`).
    const EMPTY_TOTAL = '₹0';

    await signIn(page, tenant.manager);
    await page.goto('/reports');
    await page.getByRole('button', { name: 'Pipeline by stage' }).click();
    const managerTotal = page.locator('tfoot tr td').last();
    await expect(managerTotal).not.toHaveText(EMPTY_TOTAL);
    const managerValue = await managerTotal.textContent();

    await signOut(page);

    await signIn(page, tenant.rep);
    await page.goto('/reports');
    await page.getByRole('button', { name: 'Pipeline by stage' }).click();
    const repTotal = page.locator('tfoot tr td').last();

    await expect(repTotal).toHaveText(EMPTY_TOTAL);
    expect(managerValue).not.toBe(EMPTY_TOTAL);
  });

  test('a rep cannot reach a colleague’s deal by typing its URL', async ({ page, tenant }) => {
    // Hiding it in the list is presentation; refusing it on direct request is
    // the actual control. Asked through the API the page itself uses.
    await signIn(page, tenant.manager);
    await page.goto('/opportunities');
    await page.getByText(tenant.managerDealName).click();
    await expect(page).toHaveURL(/\/opportunities\/[0-9a-f-]{36}/);
    const dealUrl = page.url();

    await signOut(page);
    await signIn(page, tenant.rep);
    await page.goto(dealUrl);

    // A 404 state, not the record. The exact copy is the app's to choose, so
    // this asserts the record's name is absent rather than pinning a message.
    await expect(page.getByText(tenant.managerDealName)).toHaveCount(0);
  });
});
