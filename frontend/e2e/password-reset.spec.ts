import { test, expect } from './fixtures';

/**
 * Recovering an account you cannot sign in to.
 *
 * **What these tests can and cannot reach.** The reset token exists in exactly
 * one place — the email — and deliberately nowhere else: the delivery log
 * stores a subject and a template name but never a body, precisely so that a
 * link which is a bearer credential is not sitting somewhere an administrator
 * can read it. So a browser has no way to obtain a real token, and no test
 * here completes a redemption. That half is covered by
 * `backend/tests/integration/test_password_reset.py`, which drains the outbox
 * and reads the token out of the message the provider was handed.
 *
 * What is left is the half only a browser can check, and it is not the lesser
 * half:
 *
 * * the flow is *reachable* — a link on the sign-in form, which is the whole
 *   difference between a feature and an endpoint;
 * * the confirmation screen is **identical** for an address with an account
 *   and one without. The backend answers 202 either way, and that care is
 *   undone the moment the UI renders two different screens. This is the one
 *   assertion in the suite that has to be made in the browser, because the
 *   leak would live in the browser;
 * * a broken or missing token fails on the screen that says so, rather than
 *   after somebody has chosen and typed a password twice.
 */

test.describe('password reset', () => {
  test('the sign-in form offers a way out', async ({ page }) => {
    // A recovery flow nobody can find is not a recovery flow. The link sits
    // beside the password field, which is where somebody looks the moment they
    // realise they cannot remember it.
    await page.goto('/login');

    await page.getByRole('link', { name: 'Forgot password?' }).click();

    await expect(page).toHaveURL(/\/forgot-password/);
    await expect(
      page.getByRole('heading', { name: 'Reset your password' }),
    ).toBeVisible();
  });

  test('a known and an unknown address are answered identically', async ({
    page,
    tenant,
  }) => {
    // The enumeration property, asserted where it could actually be lost.
    // The API returns an empty 202 for both, so the only way this leaks is a
    // UI that branches on the response — and the only way to catch that is to
    // compare the two rendered screens.
    const confirmationFor = async (email: string): Promise<string> => {
      await page.goto('/forgot-password');
      await page.getByLabel('Email').fill(email);
      await page.getByRole('button', { name: 'Send reset link' }).click();
      await expect(
        page.getByRole('heading', { name: 'Check your email' }),
      ).toBeVisible();
      // The whole page, not one element. A leak here would most likely be a
      // heading or a subtitle that quietly says "we sent it" for one address
      // and something else for the other, and narrowing the comparison to a
      // single container is how that gets missed.
      return page.locator('body').innerText();
    };

    const known = await confirmationFor(tenant.rep.email);
    const unknown = await confirmationFor(
      `definitely-not-registered-${Date.now()}@example.com`,
    );

    expect(unknown).toBe(known);
  });

  test('the confirmation promises only what we can promise', async ({
    page,
    tenant,
  }) => {
    // "Check your inbox" is a claim we cannot make for an address we will not
    // confirm exists. The wording has to stay conditional, and wording is the
    // sort of thing that gets tidied up by somebody who does not know why it
    // was phrased that way.
    await page.goto('/forgot-password');
    await page.getByLabel('Email').fill(tenant.admin.email);
    await page.getByRole('button', { name: 'Send reset link' }).click();

    await expect(page.getByText(/if that address has an S3K account/i)).toBeVisible();
  });

  test('a link with no token says so before anything is typed', async ({ page }) => {
    // Some mail clients truncate long links. Failing at the end — after the
    // person has chosen a password and typed it twice — would be the worst
    // available moment to tell them.
    await page.goto('/reset-password');

    await expect(
      page.getByRole('heading', { name: 'This link is incomplete' }),
    ).toBeVisible();
    await expect(page.getByRole('link', { name: 'Request a new link' })).toBeVisible();
    // `exact` throughout this file: `getByLabel` matches on substring, and
    // "New password" is a substring of "Confirm new password", so the plain
    // form resolves to both fields and fails on strict mode rather than on
    // anything the test meant to say.
    await expect(page.getByLabel('New password', { exact: true })).toHaveCount(0);
  });

  test('the password requirements are shown before submitting, not after', async ({
    page,
  }) => {
    await page.goto('/reset-password?token=not-a-real-token');

    const submit = page.getByRole('button', { name: 'Update password' });
    await expect(submit).toBeDisabled();

    await page.getByLabel('New password', { exact: true }).fill('short');
    // The unmet rules are still on screen; nothing has been sent anywhere.
    await expect(page.getByText('At least 12 characters')).toBeVisible();
    await expect(submit).toBeDisabled();

    await page.getByLabel('New password', { exact: true }).fill('Str0ngEnoughHere!');
    await page.getByLabel('Confirm new password').fill('Str0ngEnoughElse!');
    await expect(page.getByText('The two passwords do not match.')).toBeVisible();
    await expect(submit).toBeDisabled();

    await page.getByLabel('Confirm new password').fill('Str0ngEnoughHere!');
    await expect(submit).toBeEnabled();
  });

  test('a token the server rejects is reported on the form', async ({ page }) => {
    // The token is 48 bytes of entropy, so this is the case a stale or
    // already-used link produces. It has to land as an error the person can
    // act on — with the way to get a fresh link still on screen — rather than
    // as a blank page or a silent no-op.
    await page.goto('/reset-password?token=not-a-real-token');

    await page.getByLabel('New password', { exact: true }).fill('Str0ngEnoughHere!');
    await page.getByLabel('Confirm new password').fill('Str0ngEnoughHere!');
    await page.getByRole('button', { name: 'Update password' }).click();

    // Scoped to the form: Next mounts its own route announcer with
    // `role="alert"` on every page, so the unscoped locator matches two
    // elements and fails on strict mode — intermittently, depending on which
    // one is mounted first. "On the form" is what this test claims anyway.
    const formAlert = page.locator('form').getByRole('alert');
    await expect(formAlert).toBeVisible();
    await expect(formAlert).toContainText(/no longer valid/i);
    await expect(page).toHaveURL(/\/reset-password/);
  });

  test('a password is never left in the form after a failed attempt', async ({
    page,
  }) => {
    // A rejected link means starting over, and leaving the chosen password in
    // the fields invites a second identical attempt against the same dead
    // token — and leaves it sitting in the DOM of a page the person is about
    // to walk away from.
    await page.goto('/reset-password?token=not-a-real-token');

    await page.getByLabel('New password', { exact: true }).fill('Str0ngEnoughHere!');
    await page.getByLabel('Confirm new password').fill('Str0ngEnoughHere!');
    await page.getByRole('button', { name: 'Update password' }).click();

    await expect(page.locator('form').getByRole('alert')).toBeVisible();
    await expect(page.getByLabel('New password', { exact: true })).toHaveValue('');
    await expect(page.getByLabel('Confirm new password')).toHaveValue('');
  });

  test('every dead end leads back to the sign-in form', async ({ page }) => {
    await page.goto('/forgot-password');
    await page.getByRole('link', { name: 'Back to sign in' }).click();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();

    await page.goto('/reset-password?token=not-a-real-token');
    await page.getByRole('link', { name: 'Back to sign in' }).click();
    await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
  });
});
