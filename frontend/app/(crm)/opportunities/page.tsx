'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Target, Plus, Pencil, Trash2, Loader2, LayoutList, LayoutGrid } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import KanbanBoard, { type KanbanColumnDef } from '@/components/crm/kanban/KanbanBoard';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { FormError, ListEmpty, ListError, ResultCount } from '@/components/crm/shared/ListStates';
import { usePermissions } from '@/context/AuthContext';
import { useCollection, useMutation } from '@/features/shared/hooks/useCollection';
import { listAccounts, type Account } from '@/features/crm/accounts';
import {
  archiveOpportunity,
  changeStage,
  createOpportunity,
  isClosed,
  listOpportunities,
  listStages,
  updateOpportunity,
  type Opportunity,
  type OpportunityInput,
  type PipelineStage,
} from '@/features/crm/opportunities';

/* ============================================================
   OPPORTUNITIES

   Rows come from `GET /api/v1/crm/opportunities`. Stages come
   from `GET /crm/opportunities/stages` — the seeded pipeline in
   the database, not a hardcoded list, which is what resolves the
   dashboard/opportunity stage mismatch (risk R23).

   Moving a deal posts to `/stage`, the only path that writes
   stage history and enforces the win/loss rules. A stage marked
   lost requires a reason; the backend returns 422 without one
   and that message is shown rather than guessed at.
   ============================================================ */

const EMPTY_FORM: OpportunityInput = {
  name: '',
  account_id: '',
  deal_value: '',
  expected_close_date: '',
  notes: '',
};

type ViewMode = 'table' | 'kanban';

function formatMoney(value: string | null, currency: string): string {
  if (value === null) return '—';
  const amount = Number(value);
  if (Number.isNaN(amount)) return '—';
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency,
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    // An unknown ISO code must not blank the column.
    return `${currency} ${amount.toLocaleString()}`;
  }
}

export default function OpportunitiesPage() {
  const router = useRouter();
  const { can } = usePermissions();
  const mayCreate = can('opportunities', 'CREATE');
  const mayEdit = can('opportunities', 'EDIT');
  const mayDelete = can('opportunities', 'DELETE');
  const mayViewAccounts = can('accounts', 'VIEW');

  const [view, setView] = useState<ViewMode>('table');
  const [search, setSearch] = useState('');
  const [stageFilter, setStageFilter] = useState('');
  const [page, setPage] = useState(1);
  const pageSize = view === 'kanban' ? 200 : 25;

  const fetcher = useCallback(
    () =>
      listOpportunities({
        page: view === 'kanban' ? 1 : page,
        page_size: pageSize,
        search: search.trim() || null,
        stage_id: stageFilter || null,
        sort_by: 'expected_close_date',
        sort_dir: 'asc',
      }),
    [page, pageSize, search, stageFilter, view],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<Opportunity>(
    fetcher,
    [page, pageSize, search, stageFilter, view],
    { errorMessage: 'Something went wrong loading opportunities.' },
  );

  /* ---- Reference data ---- */
  const [stages, setStages] = useState<PipelineStage[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const result = await listStages();
        if (!cancelled) setStages(result);
      } catch {
        // Without stages the board cannot render; the table still can.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!mayViewAccounts) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await listAccounts({ page_size: 200, sort_by: 'name', sort_dir: 'asc' });
        if (!cancelled) setAccounts(result.data);
      } catch {
        // Non-fatal — the picker is empty and the form says so.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayViewAccounts]);

  const stageNames = useMemo(
    () => new Map(stages.map((stage) => [stage.id, stage.name])),
    [stages],
  );
  const accountNames = useMemo(
    () => new Map(accounts.map((account) => [account.id, account.name])),
    [accounts],
  );
  const openStages = useMemo(() => stages.filter((s) => !s.is_won && !s.is_lost), [stages]);

  const kanbanColumns = useMemo<KanbanColumnDef<Opportunity>[]>(
    () =>
      stages.map((stage) => ({
        id: stage.id,
        label: stage.name,
        color: stage.is_won ? '#059669' : stage.is_lost ? '#dc2626' : 'var(--accent)',
      })),
    [stages],
  );

  /* ---- Drawer ---- */
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Opportunity | null>(null);
  const [form, setForm] = useState<OpportunityInput>(EMPTY_FORM);
  const { pending, error: saveError, clearError, run } = useMutation();
  const [boardError, setBoardError] = useState<string | null>(null);

  const openAdd = () => {
    setEditing(null);
    setForm({ ...EMPTY_FORM, stage_id: openStages[0]?.id ?? '' });
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = (row: Opportunity) => {
    setEditing(row);
    setForm({
      name: row.name,
      account_id: row.account_id,
      deal_value: row.deal_value ?? '',
      expected_close_date: row.expected_close_date ?? '',
      notes: row.notes ?? '',
    });
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim() || !form.account_id) return;
    const body: OpportunityInput = {
      name: form.name.trim(),
      account_id: form.account_id,
      deal_value: form.deal_value || null,
      expected_close_date: form.expected_close_date || null,
      notes: form.notes?.trim() || null,
    };
    // `stage_id` is only meaningful at creation: a PATCH deliberately ignores
    // it so a stage move cannot skip history recording.
    if (!editing && form.stage_id) body.stage_id = form.stage_id;

    const saved = await run(() =>
      editing ? updateOpportunity(editing.id, body) : createOpportunity(body),
    );
    if (saved === undefined) return;
    setDrawerOpen(false);
    reload();
  };

  const handleStageChange = async (row: Opportunity, stageId: string) => {
    setBoardError(null);
    const target = stages.find((stage) => stage.id === stageId);
    // The backend requires a reason for a lost stage. Ask here rather than
    // letting the request fail, but still let the server be the authority.
    let lossReason: string | null = null;
    if (target?.is_lost) {
      lossReason = window.prompt('Why was this deal lost?')?.trim() || null;
      if (!lossReason) return;
    }
    try {
      await changeStage(row.id, { stage_id: stageId, loss_reason: lossReason });
      reload();
    } catch (caught) {
      setBoardError(
        caught instanceof Error ? caught.message : 'That stage change was rejected.',
      );
      reload();
    }
  };

  const handleDelete = async (row: Opportunity) => {
    const done = await run(() => archiveOpportunity(row.id));
    if (done !== undefined) reload();
  };

  const columns = useMemo<ColumnDef<Opportunity>[]>(
    () => [
      { key: 'name', label: 'Opportunity', minWidth: '200px' },
      {
        key: 'account_id',
        label: 'Account',
        hideBelow: 'md',
        render: (row) => accountNames.get(row.account_id) ?? <span className="txt-faint">—</span>,
      },
      {
        key: 'deal_value',
        label: 'Value',
        align: 'right',
        render: (row) => (
          <span className="tabular-nums">{formatMoney(row.deal_value, row.currency)}</span>
        ),
      },
      {
        key: 'expected_close_date',
        label: 'Close',
        hideBelow: 'lg',
        render: (row) => row.expected_close_date ?? <span className="txt-faint">—</span>,
      },
      {
        key: 'stage_id',
        label: 'Stage',
        render: (row) => (
          <StatusBadge
            label={stageNames.get(row.stage_id) ?? 'Unknown'}
            variant={row.won_at ? 'success' : row.lost_at ? 'danger' : 'accent'}
          />
        ),
      },
      {
        key: 'actions',
        label: '',
        align: 'right',
        render: (row) => (
          <div className="flex items-center justify-end gap-1">
            {mayEdit && !isClosed(row) && (
              <button
                type="button"
                aria-label={`Edit ${row.name}`}
                onClick={(event) => {
                  event.stopPropagation();
                  openEdit(row);
                }}
                className="ctl rounded-lg p-1.5 transition hover:opacity-70"
              >
                <Pencil className="h-3.5 w-3.5" />
              </button>
            )}
            {mayDelete && (
              <button
                type="button"
                aria-label={`Archive ${row.name}`}
                onClick={(event) => {
                  event.stopPropagation();
                  void handleDelete(row);
                }}
                className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mayEdit, mayDelete, accountNames, stageNames],
  );

  const stageFilterOptions = useMemo(
    () => [
      { value: '', label: 'All stages' },
      ...stages.map((stage) => ({ value: stage.id, label: stage.name })),
    ],
    [stages],
  );

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-sky-500 to-blue-600">
            <Target className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Opportunities</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              Live deals and the pipeline they sit in.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="ctl bd flex items-center rounded-lg border p-0.5">
            <button
              type="button"
              aria-label="Table view"
              aria-pressed={view === 'table'}
              onClick={() => setView('table')}
              className={`rounded-md p-1.5 transition ${view === 'table' ? 'bg-[var(--surface-2)]' : 'opacity-60'}`}
            >
              <LayoutList className="h-4 w-4" />
            </button>
            <button
              type="button"
              aria-label="Board view"
              aria-pressed={view === 'kanban'}
              onClick={() => setView('kanban')}
              className={`rounded-md p-1.5 transition ${view === 'kanban' ? 'bg-[var(--surface-2)]' : 'opacity-60'}`}
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
          </div>
          {mayCreate && (
            <button
              type="button"
              onClick={openAdd}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              <Plus className="h-4 w-4" /> New opportunity
            </button>
          )}
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <SearchInput
          value={search}
          onChange={(event) => {
            setSearch(event.target.value);
            setPage(1);
          }}
          placeholder="Search opportunities…"
        />
        <FilterSelect
          value={stageFilter}
          onChange={(event) => {
            setStageFilter(event.target.value);
            setPage(1);
          }}
          options={stageFilterOptions}
        />
        {refreshing && (
          <Loader2 className="txt-faint h-4 w-4 motion-safe:animate-spin" aria-label="Refreshing" />
        )}
        <div className="ml-auto">
          <ResultCount shown={items.length} total={pagination?.total ?? 0} />
        </div>
      </div>

      {boardError && (
        <p role="alert" className="text-[12.5px] font-medium text-red-500">
          {boardError}
        </p>
      )}

      {status === 'error' && error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : view === 'table' ? (
        <DataTable
          columns={columns}
          data={items}
          rowKey={(row) => row.id}
          onRowClick={(row) => router.push(`/opportunities/${row.id}`)}
          loading={status === 'loading'}
          skeletonRows={6}
          emptyState={
            <ListEmpty
              title="No opportunities yet"
              hint={
                search || stageFilter
                  ? 'No opportunity matches those filters.'
                  : 'Create a deal, or convert a qualified lead with “create opportunity” ticked.'
              }
            />
          }
        />
      ) : status === 'loading' ? (
        <div className="txt-muted flex items-center gap-2 py-12 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading board…
        </div>
      ) : (
        <KanbanBoard
          columns={kanbanColumns}
          data={items}
          groupBy={(opportunity) => opportunity.stage_id}
          renderCard={(opportunity) => (
            <div className="surface bd rounded-xl border p-3">
              <button
                type="button"
                onClick={() => router.push(`/opportunities/${opportunity.id}`)}
                className="txt block text-left text-[13.5px] font-semibold hover:opacity-70"
              >
                {opportunity.name}
              </button>
              <p className="txt-muted mt-0.5 text-[12px]">
                {formatMoney(opportunity.deal_value, opportunity.currency)}
              </p>
              {mayEdit && !isClosed(opportunity) && (
                <FilterSelect
                  className="mt-2 w-full"
                  value={opportunity.stage_id}
                  onChange={(event) =>
                    void handleStageChange(opportunity, event.target.value)
                  }
                  aria-label={`Change stage for ${opportunity.name}`}
                  options={stages.map((stage) => ({ value: stage.id, label: stage.name }))}
                />
              )}
            </div>
          )}
        />
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? 'Edit opportunity' : 'New opportunity'}
        subtitle={
          editing ? editing.name : 'A deal always belongs to an account.'
        }
        footer={
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void handleSave()}
              disabled={pending || !form.name.trim() || !form.account_id}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              {pending ? 'Saving…' : 'Save'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <FormField label="Name" required>
            <FormInput
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Acme — platform rollout"
            />
          </FormField>
          <FormField
            label="Account"
            required
            hint={
              accounts.length === 0
                ? 'Create an account first — a deal cannot exist without one.'
                : undefined
            }
          >
            <FormSelect
              value={form.account_id}
              onChange={(event) => setForm({ ...form, account_id: event.target.value })}
              placeholder="Select an account"
              disabled={!mayViewAccounts}
              options={accounts.map((account) => ({
                value: account.id,
                label: account.name,
              }))}
            />
          </FormField>
          {!editing && (
            <FormField label="Starting stage">
              <FormSelect
                value={form.stage_id ?? ''}
                onChange={(event) => setForm({ ...form, stage_id: event.target.value })}
                options={openStages.map((stage) => ({
                  value: stage.id,
                  label: stage.name,
                }))}
              />
            </FormField>
          )}
          <FormField label="Deal value">
            <FormInput
              type="number"
              min="0"
              step="0.01"
              value={form.deal_value ?? ''}
              onChange={(event) => setForm({ ...form, deal_value: event.target.value })}
            />
          </FormField>
          <FormField label="Expected close">
            <FormInput
              type="date"
              value={form.expected_close_date ?? ''}
              onChange={(event) =>
                setForm({ ...form, expected_close_date: event.target.value })
              }
            />
          </FormField>
          <FormField label="Notes">
            <FormTextarea
              value={form.notes ?? ''}
              onChange={(event) => setForm({ ...form, notes: event.target.value })}
              rows={3}
            />
          </FormField>
          <FormError message={saveError} />
        </div>
      </SlideDrawer>
    </div>
  );
}
