import { test, expect, signIn, signOut } from './fixtures';
import { currentTotpCode } from './totp';
import type { SeededPerson } from './seed';

/**
 * Two-factor authentication, end to end (Checkpoint 8).
 *
 * One long test rather than several short ones, same reasoning as the daily
 * journey spec: enrollment, sign-out, the login challenge and disabling are
 * only meaningful as a sequence against the *same* account, and splitting
 * them would mean each re-doing enrollment to set up its own precondition.
 *
 * Runs against the rep, not the admin or manager: MFA is a per-identity
 * setting, not a role-gated feature, and using the least-privileged persona
 * is what proves that.
 */

const API_URL = process.env.E2E_API_URL ?? 'http://127.0.0.1:8100';
const PREFIX = process.env.E2E_API_PREFIX ?? '/api/v1';

/**
 * Guarantees the rep leaves this file with MFA off, even if an assertion
 * mid-test fails first. `tenant.rep` is a shared fixture several other spec
 * files sign in as through the plain login form, which does not know about
 * an MFA challenge — a test that enables MFA and then fails before disabling
 * it again would strand every spec that runs after this one, turning one
 * clear failure into a confusing cascade of unrelated-looking ones.
 */
async function ensureMfaDisabled(person: SeededPerson): Promise<void> {
  const loginResponse = await fetch(`${API_URL}${PREFIX}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: person.email, password: person.password }),
  });
  if (!loginResponse.ok) return; // Nothing this cleanup can do about a broken login.
  const body = (await loginResponse.json()) as { access_token?: string };
  if (!body.access_token) return; // Still mid-challenge; nothing more to clean up here.

  await fetch(`${API_URL}${PREFIX}/auth/mfa/disable`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${body.access_token}`,
    },
    body: JSON.stringify({ current_password: person.password }),
  });
  // A 409 here means it was already disabled — the expected, common case.
}

test.describe('two-factor authentication', () => {
  test.afterEach(async ({ tenant }) => {
    await ensureMfaDisabled(tenant.rep);
  });


  test('enroll, sign out, clear the login challenge, then disable', async ({
    page,
    tenant,
  }) => {
    // Six-plus full sign-in cycles, each hashing a real password with argon2
    // (deliberately slow, doc 13) — legitimately heavier than any other spec,
    // which signs in once. The default 60s budget is for that common case,
    // not this one.
    test.setTimeout(150_000);

    await signIn(page, tenant.rep);
    await page.goto('/account/security');
    await expect(page.getByRole('heading', { name: 'Security' })).toBeVisible();
    await expect(page.getByText('Not enabled.')).toBeVisible();

    // --- Enroll -------------------------------------------------------
    await page.getByRole('button', { name: 'Enable two-factor authentication' }).click();

    // The secret is shown as plain text for manual entry — the only way a
    // test (or a person without a phone camera) can get at it.
    const secretBlock = page.locator('code');
    await expect(secretBlock).toBeVisible();
    const secret = (await secretBlock.textContent())?.trim();
    if (!secret) throw new Error('Enrollment did not render a secret.');

    // Recovery codes render as a grid of ten upper-case tokens.
    const recoveryCodes = await page
      .locator('span.font-mono, .font-mono span')
      .allTextContents();
    expect(recoveryCodes.length).toBeGreaterThanOrEqual(10);

    await page.getByPlaceholder('123456').fill(currentTotpCode(secret));
    await page.getByRole('button', { name: 'Confirm' }).click();

    await expect(page.getByText(/Enabled — a code is required/)).toBeVisible();
    // Lets the confirm mutation's re-render settle before the account menu
    // is clicked — without it, a click landing mid-render has intermittently
    // hit a stale node and left the menu open instead of signing out.
    await page.waitForTimeout(500);

    // --- Sign out, sign back in: the login form now owes a second factor ---
    await signOut(page);

    await page.goto('/login');
    await page.getByLabel('Email').fill(tenant.rep.email);
    await page.getByLabel('Password').fill(tenant.rep.password);
    await page.getByRole('button', { name: 'Sign in' }).click();

    await expect(page.getByRole('heading', { name: 'Enter your code' })).toBeVisible();

    // A wrong code is refused and leaves the challenge open.
    await page.getByLabel('Code').fill('000000');
    await page.getByRole('button', { name: 'Verify' }).click();
    await expect(page.getByRole('alert').or(page.getByText(/incorrect or has expired/))).toBeVisible();

    // The right code completes sign-in.
    await page.getByLabel('Code').fill(currentTotpCode(secret));
    await page.getByRole('button', { name: 'Verify' }).click();
    await expect(page.getByRole('region', { name: 'Your apps' })).toBeVisible();
    await page.waitForTimeout(500);

    // --- A recovery code works exactly once ---------------------------
    await signOut(page);
    await page.goto('/login');
    await page.getByLabel('Email').fill(tenant.rep.email);
    await page.getByLabel('Password').fill(tenant.rep.password);
    await page.getByRole('button', { name: 'Sign in' }).click();

    const [recoveryCode] = recoveryCodes;
    if (!recoveryCode) throw new Error('No recovery code was captured to spend.');
    await page.getByLabel('Code').fill(recoveryCode);
    await page.getByRole('button', { name: 'Verify' }).click();
    await expect(page.getByRole('region', { name: 'Your apps' })).toBeVisible();
    await page.waitForTimeout(500);

    await signOut(page);
    await page.goto('/login');
    await page.getByLabel('Email').fill(tenant.rep.email);
    await page.getByLabel('Password').fill(tenant.rep.password);
    await page.getByRole('button', { name: 'Sign in' }).click();
    await page.getByLabel('Code').fill(recoveryCode);
    await page.getByRole('button', { name: 'Verify' }).click();
    await expect(page.getByText(/incorrect or has expired/)).toBeVisible();

    // Clear the stuck challenge with a fresh code, then disable.
    await page.getByLabel('Code').fill(currentTotpCode(secret));
    await page.getByRole('button', { name: 'Verify' }).click();
    await expect(page.getByRole('region', { name: 'Your apps' })).toBeVisible();

    await page.goto('/account/security');
    await page.getByRole('button', { name: 'Disable' }).click();
    await page.getByLabel('Current password').fill(tenant.rep.password);
    await page.getByRole('button', { name: 'Confirm disable' }).click();

    await expect(page.getByText('Not enabled.')).toBeVisible();
  });
});
