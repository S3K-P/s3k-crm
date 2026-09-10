import { test, expect, signIn } from './fixtures';
import type { Page, Response } from '@playwright/test';
import { RUN_ID } from './seed';

/**
 * Writing a customer email, end to end, through the real UI.
 *
 * The one thing this suite is careful about: **nothing here asserts that a
 * message was "Sent"**. Sending is asynchronous — the request enqueues an
 * outbox event and a separate worker process delivers it — and the E2E stack
 * does not run that worker. A message therefore reaches `Queued` and stops,
 * which is exactly what a user sees while a relay is slow. Asserting "Sent"
 * would either fail here or force the UI to lie about what has happened, and
 * the delivery path itself is covered where it can be covered honestly:
 * `backend/tests/integration/test_crm_email.py` drains the outbox for real.
 *
 * **Every mutating click goes through `clickAndWait`.** Playwright's `click`
 * resolves when the click is *dispatched*, not when the request it triggers
 * completes, so a bare click followed by an assertion — or worse, by a
 * navigation — races the round trip. An earlier version of this file did
 * exactly that and cost a long hunt: `page.reload()` immediately after
 * pressing Send aborted the in-flight `POST /crm/emails` (the trace recorded
 * it with status `-1`, and the server never saw it), so the message genuinely
 * did not exist and the test failed pointing at the list. Synchronising on the
 * response is not a wait bolted on to paper over flake; it is the difference
 * between clicking a button and completing an action.
 */

/** Click something and resolve once the request it triggers has answered. */
async function clickAndWait(
  page: Page,
  click: () => Promise<void>,
  matches: (response: Response) => boolean,
): Promise<Response> {
  // The listener is registered before the click so a fast response cannot
  // land in the gap between the two.
  const [response] = await Promise.all([page.waitForResponse(matches), click()]);
  return response;
}

const isCompose = (response: Response): boolean =>
  response.request().method() === 'POST' && /\/crm\/emails$/.test(response.url());

const isSend = (response: Response): boolean =>
  response.request().method() === 'POST' && /\/crm\/emails\/[^/]+\/send$/.test(response.url());

const isTemplateCreate = (response: Response): boolean =>
  response.request().method() === 'POST' && /\/crm\/email-templates$/.test(response.url());

test.describe('customer email', () => {
  test('a rep saves a template, composes with it, and queues the message', async ({
    page,
    tenant,
  }) => {
    const templateName = `Follow up ${RUN_ID}`;
    const subject = `Proposal ${RUN_ID}`;

    await signIn(page, tenant.rep);

    // --- A template, with a placeholder the composer will fill in ---------
    await page.getByRole('link', { name: 'Email', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Email' })).toBeVisible();

    await page.getByRole('link', { name: 'Templates' }).click();
    await expect(page.getByRole('heading', { name: 'Email templates' })).toBeVisible();

    await page.getByRole('button', { name: 'New template' }).click();
    await page.getByLabel('Name', { exact: true }).fill(templateName);
    await page.getByLabel('Subject', { exact: true }).fill(subject);
    await page
      .getByLabel('Body', { exact: true })
      .fill('Hello {{record.first_name}},\n\nHere is the proposal.\n\n— {{sender.name}}');

    const templateSaved = await clickAndWait(
      page,
      () => page.getByRole('button', { name: 'Save template' }).click(),
      isTemplateCreate,
    );
    expect(templateSaved.status()).toBe(201);
    await expect(page.getByText(templateName)).toBeVisible();

    // --- Compose against it ------------------------------------------------
    await page.getByRole('link', { name: 'Email', exact: true }).click();
    await page.getByRole('button', { name: 'New email' }).click();

    await page.getByLabel('To', { exact: true }).fill('ravi@zephyr.example');
    await page.getByLabel('Subject', { exact: true }).fill(subject);
    await page.getByLabel('Message', { exact: true }).fill('Hello Ravi,\n\nHere is the proposal.');

    const composed = await clickAndWait(
      page,
      () => page.getByRole('button', { name: 'Send', exact: true }).click(),
      isCompose,
    );
    expect(composed.status()).toBe(201);

    // Queued, not Sent: the worker has not run, and the UI must not claim it
    // has. This is the assertion the whole file exists to make.
    //
    // Scoped to the row on purpose — a bare `getByText('Queued')` also matches
    // the hidden <option> in the status filter, which is present whether or
    // not a single message was ever sent and would make this assertion pass
    // for nothing.
    const row = page.locator('li').filter({ hasText: subject });
    await expect(row).toBeVisible();
    await expect(row.getByText('Queued')).toBeVisible();

    // And it survives a reload, which is what proves it is a row rather than
    // something the composer painted optimistically. Safe here because the
    // POST above has already answered — nothing is in flight to abort.
    await page.reload();
    const reloaded = page.locator('li').filter({ hasText: subject });
    await expect(reloaded).toBeVisible();
    await expect(reloaded.getByText('Queued')).toBeVisible();
  });

  test('a draft is saved without being sent, then queued from the list', async ({
    page,
    tenant,
  }) => {
    // Deliberately does not contain the word "Draft": the subject and the
    // status badge share a row, so a subject echoing a status name makes every
    // status assertion ambiguous.
    const subject = `Unsent ${RUN_ID}`;

    await signIn(page, tenant.rep);
    await page.getByRole('link', { name: 'Email', exact: true }).click();

    await page.getByRole('button', { name: 'New email' }).click();
    await page.getByLabel('To', { exact: true }).fill('anita@nova.example');
    await page.getByLabel('Subject', { exact: true }).fill(subject);
    await page.getByLabel('Message', { exact: true }).fill('Still thinking about how to phrase this.');

    const saved = await clickAndWait(
      page,
      () => page.getByRole('button', { name: 'Save draft' }).click(),
      isCompose,
    );
    expect(saved.status()).toBe(201);

    const row = page.locator('li').filter({ hasText: subject });
    await expect(row.getByText('Draft')).toBeVisible();

    // Sending it from the list moves it on. The control is named per message,
    // so this cannot pick up another row's button.
    const sent = await clickAndWait(
      page,
      () => row.getByRole('button', { name: `Send ${subject}` }).click(),
      isSend,
    );
    expect(sent.status()).toBe(200);

    await expect(row.getByText('Queued')).toBeVisible();
    // The control belonged to the draft state and goes with it.
    await expect(row.getByRole('button', { name: `Send ${subject}` })).toHaveCount(0);
  });

  test('blind copies are collected but never shown back as addresses', async ({
    page,
    tenant,
  }) => {
    const subject = `Confidential ${RUN_ID}`;

    await signIn(page, tenant.rep);
    await page.getByRole('link', { name: 'Email', exact: true }).click();
    await page.getByRole('button', { name: 'New email' }).click();

    await page.getByLabel('To', { exact: true }).fill('ravi@zephyr.example');
    await page.getByRole('button', { name: 'Add Cc / Bcc' }).click();
    await page.getByLabel('Bcc', { exact: true }).fill('legal@ourcompany.example');
    await page.getByLabel('Subject', { exact: true }).fill(subject);
    await page.getByLabel('Message', { exact: true }).fill('For the record.');

    // `exact` so this is the composer's Send, never a row's — those are named
    // "Send <subject>".
    const composed = await clickAndWait(
      page,
      () => page.getByRole('button', { name: 'Send', exact: true }).click(),
      isCompose,
    );
    expect(composed.status()).toBe(201);

    // The list shows a count, and the address itself appears nowhere on the
    // page — the sender may read it on the message, but the list is a shared
    // surface and prints only how many there were.
    const row = page.locator('li').filter({ hasText: subject });
    await expect(row).toContainText('Bcc 1');
    await expect(page.getByText('legal@ourcompany.example')).toHaveCount(0);
  });

  test('email appears on the record it was filed against', async ({ page, tenant }) => {
    const subject = `Account note ${RUN_ID}`;

    await signIn(page, tenant.manager);

    // The manager holds VIEW_ALL, so the seeded account is theirs to open.
    await page.getByRole('link', { name: 'Accounts', exact: true }).click();
    await page.getByText(tenant.managerAccountName).first().click();

    // The record page carries exactly one "New email" control — the emails
    // panel's — so it identifies the panel without a brittle DOM path.
    await expect(page.getByRole('button', { name: 'New email' })).toBeVisible();
    await page.getByRole('button', { name: 'New email' }).click();

    await page.getByLabel('To', { exact: true }).fill('ops@zephyr.example');
    await page.getByLabel('Subject', { exact: true }).fill(subject);
    await page.getByLabel('Message', { exact: true }).fill('Filed against this account.');

    const composed = await clickAndWait(
      page,
      () => page.getByRole('button', { name: 'Send', exact: true }).click(),
      isCompose,
    );
    expect(composed.status()).toBe(201);

    // Back on the record, the message is part of its history.
    await expect(page.getByText(subject)).toBeVisible();
  });
});
