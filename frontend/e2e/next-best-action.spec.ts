import { test, expect, seed, signIn } from './fixtures';
import { RUN_ID, SeedClient } from './seed';

/**
 * Next Best Action — the ranked queue of real deals and leads.
 *
 * Seeds its own records through the API, as the manager, so every value the
 * page is asserted to show (name, account, reason, follow-up state) is one
 * this spec wrote — nothing here can pass against a fixture.
 *
 * No AI provider is configured in this environment. That is part of what is
 * covered: the queue, its reasons and "Take action" work without AI, and the
 * AI-dependent parts say so rather than hang or pretend.
 */

const isoDate = (offsetDays: number) => {
  const date = new Date();
  date.setDate(date.getDate() + offsetDays);
  return date.toISOString().slice(0, 10);
};

const dealName = `Overdue expansion ${RUN_ID}`;
const accountName = `Zephyr ${RUN_ID}`;
const leadFirstName = `Grace${RUN_ID}`;

test.describe('next best action', () => {
  test.beforeAll(async () => {
    const api = new SeedClient();
    await api.login(seed().manager);

    // Large, past its close date, likely to win, with an overdue task: every
    // one of those is a scoring rule, so the deal ranks High on facts alone.
    const account = await api.request<{ id: string }>('POST', '/crm/accounts', { name: accountName });
    const stages = await api.request<{ id: string; name: string }[]>('GET', '/crm/opportunities/stages');
    const proposal = stages.find((stage) => stage.name === 'Proposal') ?? stages[0];
    const deal = await api.request<{ id: string }>('POST', '/crm/opportunities', {
      name: dealName,
      account_id: account.id,
      stage_id: proposal.id,
      deal_value: '5000000',
      win_probability: 70,
      expected_close_date: isoDate(-3),
    });
    await api.request('POST', '/crm/tasks', {
      title: `Send revised pricing ${RUN_ID}`,
      due_date: new Date(Date.now() - 86_400_000).toISOString(),
      related_entity_type: 'OPPORTUNITY',
      related_entity_id: deal.id,
    });

    await api.request('POST', '/crm/leads', {
      first_name: leadFirstName,
      last_name: 'Hopper',
      company: `Hopper Systems ${RUN_ID}`,
      priority: 'HIGH',
      expected_deal_size: '2500000',
    });
  });

  test('ranks real records, filters them, explains and acts on one', async ({ page, tenant }) => {
    await signIn(page, tenant.manager);
    await page.getByRole('link', { name: 'Next Best Action', exact: true }).click();

    await expect(page.getByRole('heading', { name: 'Next Best Action', level: 1 })).toBeVisible();
    await expect(page.getByText('AI-powered recommendations for what to work on next.')).toBeVisible();
    await expect(page.getByText('Actions needed')).toBeVisible();

    // The seeded deal is queued with its own account, level and signals.
    const deal = page.getByRole('article', { name: dealName });
    await expect(deal).toBeVisible();
    await expect(deal.getByText(accountName)).toBeVisible();
    await expect(deal.getByText('High priority')).toBeVisible();
    await expect(deal.getByRole('listitem').filter({ hasText: 'Past close date' })).toBeVisible();
    await expect(deal.getByText('1 overdue · 1 open task')).toBeVisible();
    // Nothing generated yet — and no invented recommendation in its place.
    await expect(deal.getByText('No AI recommendation yet')).toBeVisible();

    // Record type narrows the queue without re-ranking it.
    const recordType = page.getByRole('group', { name: 'Record type' });
    const lead = page.getByRole('article', { name: new RegExp(leadFirstName) });
    await recordType.getByRole('button', { name: /^Leads/ }).click();
    await expect(lead).toBeVisible();
    await expect(lead.getByRole('listitem').filter({ hasText: 'Never contacted' })).toBeVisible();
    await expect(deal).toHaveCount(0);
    await recordType.getByRole('button', { name: /^All/ }).click();
    await expect(deal).toBeVisible();

    // Explain: the rule-based reasons render with AI disconnected, and the
    // AI part says why it cannot run instead of spinning.
    await deal.getByRole('button', { name: 'Explain' }).click();
    const ranked = page.locator('section', {
      has: page.getByRole('heading', { name: 'Why it’s ranked here' }),
    });
    await expect(ranked.getByText('Large deal', { exact: true })).toBeVisible();
    await expect(ranked.getByText('Overdue task(s)', { exact: true })).toBeVisible();
    await expect(page.getByText('AI is not connected').last()).toBeVisible();
    await page.keyboard.press('Escape');

    // Take action -> a real follow-up task, filed against the deal.
    await deal.getByRole('button', { name: 'Take action' }).click();
    await page.getByRole('menuitem', { name: 'Create follow-up task' }).click();
    await expect(page.getByRole('heading', { name: 'Create follow-up task' })).toBeVisible();
    await expect(page.getByLabel('Title')).toHaveValue(`Follow up: ${dealName}`);
    await page.getByRole('button', { name: 'Create task' }).click();
    await expect(page.getByText('Follow-up task created')).toBeVisible();

    // The queue reloads, and the deal's follow-up state counts the new task.
    await expect(deal.getByText('1 overdue · 2 open tasks')).toBeVisible();
  });
});
