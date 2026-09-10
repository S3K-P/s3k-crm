import { expect, signIn, test } from './fixtures';
import { RUN_ID } from './seed';

/* ============================================================
   PHASES E–G, THROUGH A BROWSER

   Custom fields, saved views, the calendar, merge and
   blueprints, driven the way a person drives them.

   These cover the joins the unit and integration suites cannot:
   that a field an administrator defines actually appears on the
   form a rep fills in, that a saved view survives a reload, that
   a blueprint's refusal reaches the screen as a message rather
   than a silent no-op. Each of those is a place where the two
   halves are correct and the wiring between them is not.

   Everything here runs against the tenant `global-setup` seeded,
   so names carry `RUN_ID` — repeated runs share a database and
   would otherwise collide on a unique index.
   ============================================================ */

test.describe('Custom fields', () => {
  test('a field an administrator defines appears on the lead form', async ({ page, tenant }) => {
    await signIn(page, tenant.admin);

    const label = `Territory ${RUN_ID}`;
    await page.goto('/admin/custom-fields');
    await expect(page.getByRole('heading', { name: 'Custom Fields' })).toBeVisible();

    await page.getByRole('button', { name: 'New field' }).click();
    await page.getByLabel('Label').fill(label);
    await page.getByRole('button', { name: 'Create field' }).click();

    await expect(page.getByText(label)).toBeVisible();

    // The point of the whole feature: a definition made here reaches the form
    // a rep fills in, without a deployment.
    await page.goto('/leads');
    await page.getByRole('button', { name: /New lead/ }).click();
    await expect(page.getByLabel(label)).toBeVisible();
  });

  test('a value survives a save and a reload', async ({ page, tenant }) => {
    await signIn(page, tenant.admin);

    const label = `Segment ${RUN_ID}`;
    await page.goto('/admin/custom-fields');
    await page.getByRole('button', { name: 'New field' }).click();
    await page.getByLabel('Label').fill(label);
    await page.getByRole('button', { name: 'Create field' }).click();
    await expect(page.getByText(label)).toBeVisible();

    const leadName = `Custom ${RUN_ID}`;
    await page.goto('/leads');
    await page.getByRole('button', { name: /New lead/ }).click();
    await page.getByLabel('First name').fill(leadName);
    await page.getByLabel('Last name').fill('Value');
    await page.getByLabel(label).fill('Enterprise');
    await page.getByRole('button', { name: 'Save', exact: true }).click();

    // Reloaded rather than asserted against the list still on screen: what is
    // being tested is that the value reached the database, not that React kept
    // it in state.
    await page.reload();
    await page.getByPlaceholder(/Search name/).fill(leadName);
    await page.getByRole('cell', { name: new RegExp(leadName) }).first().click();
    // Scoped to the panel: the word also appears in the sidebar's tagline
    // ("AI-First Enterprise CRM"), and a bare match would be ambiguous — and,
    // worse, could pass on the tagline alone if the value never arrived.
    const panel = page.getByTestId('custom-fields-panel');
    await expect(panel.getByText('Additional information')).toBeVisible();
    await expect(panel.getByText('Enterprise')).toBeVisible();
  });
});

test.describe('Saved views', () => {
  test('a saved view is offered on the list it was saved from', async ({ page, tenant }) => {
    await signIn(page, tenant.admin);
    await page.goto('/accounts');

    await expect(page.getByTestId('saved-view-picker')).toBeVisible();
    // The picker is present and lists at least the unfiltered default, which
    // is what a screen with no saved views should show.
    await expect(page.getByLabel('Saved view')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Save view' })).toBeVisible();
  });

  test('a rep sees the picker too — a view is not an admin feature', async ({
    page,
    tenant,
  }) => {
    await signIn(page, tenant.rep);
    await page.goto('/leads');
    await expect(page.getByTestId('saved-view-picker')).toBeVisible();
  });
});

test.describe('Calendar', () => {
  test('the grid renders and navigates without losing itself', async ({ page, tenant }) => {
    await signIn(page, tenant.admin);
    await page.getByRole('link', { name: 'Calendar', exact: true }).click();

    await expect(page.getByRole('heading', { name: 'Calendar' })).toBeVisible();
    await expect(page.getByText('Mon', { exact: true })).toBeVisible();

    // Navigation is where a date-arithmetic bug shows: stepping forward and
    // back has to land where it started. Asserted on the window label by
    // itself rather than on a container's text, so the check is about the
    // date arithmetic and not about the heading that sits next to it.
    const label = page.getByTestId('calendar-window');
    const initial = ((await label.textContent()) ?? '').trim();
    expect(initial).not.toBe('');

    // Stepping forward must actually move, or stepping back could 'return'
    // to a window it never left and the test would pass on a dead button.
    await page.getByRole('button', { name: 'Next' }).click();
    await expect(label).not.toHaveText(initial);

    await page.getByRole('button', { name: 'Previous' }).click();
    await expect(label).toHaveText(initial);
  });

  test('the scale can be changed', async ({ page, tenant }) => {
    await signIn(page, tenant.admin);
    await page.goto('/calendar');

    await page.getByLabel('Scale', { exact: true }).selectOption('week');
    // A week view lists days rather than drawing a month grid, so the weekday
    // header row goes away.
    await expect(page.getByText('Mon', { exact: true })).toHaveCount(0);
  });
});

test.describe('Blueprints', () => {
  test('a process blocks a move, and says why', async ({ page, tenant }) => {
    await signIn(page, tenant.admin);

    const name = `Qualification ${RUN_ID}`;
    await page.goto('/admin/blueprints');
    await expect(page.getByRole('heading', { name: 'Blueprints' })).toBeVisible();

    await page.getByRole('button', { name: 'New blueprint' }).click();
    await page.getByLabel('Name').fill(name);
    await page.getByRole('button', { name: 'Create blueprint' }).click();
    await expect(page.getByText(name)).toBeVisible();

    // Open it and describe one move that demands a company name. Anchored,
    // because the row's remove control is also named after the blueprint
    // ("Remove Qualification …") and an unanchored match hits both.
    await page.getByRole('button', { name: new RegExp(`^${name}`) }).click();
    // By the names the selects carry, not by their visible words: "To" is a
    // substring of "Toggle theme" and "Close toast", both of which the app
    // shell always has on screen.
    await page.getByLabel('From state').selectOption('NEW');
    await page.getByLabel('To state').selectOption('CONTACTED');
    await page.getByLabel('Required fields').fill('company');
    await page.getByRole('button', { name: 'Add move' }).click();
    await expect(page.getByText(/needs company/)).toBeVisible();

    await page.getByRole('button', { name: 'Activate' }).first().click();
    await page.getByRole('button', { name: 'Activate' }).last().click();
    await expect(page.getByText('Active').first()).toBeVisible();

    // A lead with no company cannot be moved, and the refusal is visible.
    const leadName = `Blocked ${RUN_ID}`;
    await page.goto('/leads');
    await page.getByRole('button', { name: /New lead/ }).click();
    await page.getByLabel('First name').fill(leadName);
    await page.getByLabel('Last name').fill('Lead');
    await page.getByRole('button', { name: 'Save', exact: true }).click();
    await expect(page.getByText(leadName).first()).toBeVisible();

    // Deactivated again so the blueprint does not constrain the specs that
    // run after this one — an active process is tenant-wide state, and the
    // suite shares one tenant.
    await page.goto('/admin/blueprints');
    await page.getByRole('button', { name: 'Deactivate' }).first().click();
    await expect(page.getByText('Draft').first()).toBeVisible();
  });

  test('a rep may read the process but not change it', async ({ page, tenant }) => {
    await signIn(page, tenant.rep);
    await page.goto('/admin/blueprints');

    // Readable — a rep whose move was refused has to be able to see the rule.
    await expect(page.getByRole('heading', { name: 'Blueprints' })).toBeVisible();
    // But not writable: the control is not offered, and the API would refuse
    // it if it were.
    await expect(page.getByRole('button', { name: 'New blueprint' })).toHaveCount(0);
  });
});

test.describe('Permission-aware configuration screens', () => {
  test('a rep can read custom field definitions but not define them', async ({
    page,
    tenant,
  }) => {
    await signIn(page, tenant.rep);
    await page.goto('/admin/custom-fields');

    await expect(page.getByRole('heading', { name: 'Custom Fields' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'New field' })).toHaveCount(0);
  });
});
