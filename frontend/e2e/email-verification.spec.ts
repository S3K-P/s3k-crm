import { test, expect, signIn } from './fixtures';

/**
 * Confirming an email address, in the browser.
 *
 * Like the password reset, a real verification token exists only inside the
 * email, which the browser cannot read, so no test here redeems one. That half
 * — the link arrives, works once, expires, and is superseded by a newer one —
 * is covered by `backend/tests/integration/test_email_verification.py`, which
 * drains the outbox and reads the token out of the delivered message.
 *
 * What only a browser can check:
 *
 * * the confirmation is a **deliberate click**, never a side effect of opening
 *   the page — a mail scanner that fetches links must not spend the token;
 * * a broken or spent link says so plainly;
 * * a signed-in person with an unverified address is told, and can ask for a
 *   new link without leaving the CRM.
 */

test.describe('email verification', () => {
  test('a link with no token says so', async ({ page }) => {
    await page.goto('/verify-email');

    await expect(page.getByRole('heading', { name: 'This link is incomplete' })).toBeVisible();
    await expect(
      page.getByRole('button', { name: 'Confirm my email address' }),
    ).toHaveCount(0);
  });

  test('opening the link spends nothing until the button is pressed', async ({ page }) => {
    const confirmations: string[] = [];
    page.on('request', (request) => {
      if (request.url().includes('/auth/verify-email/confirm')) confirmations.push(request.url());
    });

    await page.goto('/verify-email?token=not-a-real-token');
    await expect(
      page.getByRole('button', { name: 'Confirm my email address' }),
    ).toBeVisible();

    expect(confirmations).toHaveLength(0);
  });

  test('an invalid link is refused with a way forward', async ({ page }) => {
    await page.goto('/verify-email?token=not-a-real-token');

    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/auth/verify-email/confirm')),
      page.getByRole('button', { name: 'Confirm my email address' }).click(),
    ]);

    expect(response.status()).toBe(400);
    // Filtered: Next.js mounts its own empty route announcer with role=alert.
    await expect(page.getByRole('alert').filter({ hasText: 'no longer valid' })).toBeVisible();
    await expect(
      page.getByRole('heading', { name: 'Email address confirmed' }),
    ).toHaveCount(0);
  });

  test('an unverified user is told inside the CRM and can resend the link', async ({
    page,
    tenant,
  }) => {
    // The rep was provisioned by an administrator and has never opened a
    // verification link, so their address is unverified.
    await signIn(page, tenant.rep);

    const banner = page.getByRole('region', { name: 'Email verification' });
    await expect(banner).toContainText(tenant.rep.email);

    const [response] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/auth/verify-email/request')),
      banner.getByRole('button', { name: 'Resend link' }).click(),
    ]);

    expect(response.status()).toBe(202);
    await expect(banner.getByRole('status')).toContainText('A new link is on its way');
  });
});
