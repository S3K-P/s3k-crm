import { test, expect, signIn, signOut } from './fixtures';

/**
 * The front door.
 *
 * Every other spec depends on sign-in working, so these run first and fail
 * loudly rather than letting a broken login surface as twenty confusing
 * failures elsewhere.
 */

test.describe('authentication', () => {
  test('an anonymous visitor is sent to the login form', async ({ page }) => {
    await page.goto('/opportunities');

    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
  });

  test('a wrong password is refused without saying which half was wrong', async ({
    page,
    tenant,
  }) => {
    await page.goto('/login');
    await page.getByLabel('Email').fill(tenant.rep.email);
    await page.getByLabel('Password').fill('DefinitelyWrong!9');
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('alert')).toBeVisible();
    // Still on the form, and the message must not confirm the address exists.
    await expect(page).toHaveURL(/\/login/);
    await expect(page.getByRole('alert')).not.toContainText(/password is incorrect/i);
  });

  test('a session survives a full page reload', async ({ page, tenant }) => {
    // The access token lives in memory; staying signed in across a reload is
    // the refresh cookie doing its job, and it is invisible until it breaks.
    await signIn(page, tenant.rep);

    await page.reload();

    await expect(page.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible();
    await expect(page).not.toHaveURL(/\/login/);
  });

  test('signing out ends the session for good', async ({ page, tenant }) => {
    await signIn(page, tenant.rep);

    await signOut(page);
    // Going back must not restore the session from cache.
    await page.goto('/opportunities');

    await expect(page).toHaveURL(/\/login/);
  });
});
