'use client';

import { useCallback, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Megaphone, Plus, Pencil, Trash2, Loader2, LayoutGrid, LayoutList } from 'lucide-react';

import DataTable, { type ColumnDef } from '@/components/crm/tables/DataTable';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import SearchInput from '@/components/crm/forms/SearchInput';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { humanize, statusVariant } from '@/components/crm/shared/statusVariants';
import { FormError, ListEmpty, ListError, ResultCount } from '@/components/crm/shared/ListStates';
import { usePermissions } from '@/context/AuthContext';
import { useCollection, useMutation } from '@/features/shared/hooks/useCollection';
import { listLeadSources, type LeadSource } from '@/features/crm/lead-sources';
import {
  CAMPAIGN_STATUSES,
  CAMPAIGN_TYPES,
  archiveCampaign,
  createCampaign,
  listCampaigns,
  updateCampaign,
  type Campaign,
  type CampaignInput,
  type CampaignStatus,
  type CampaignType,
} from '@/features/crm/campaigns';
import { useEffect } from 'react';

/* ============================================================
   CAMPAIGNS

   Every row comes from `GET /api/v1/crm/campaigns`, scoped by
   the backend to the caller's organization.

   `leads_generated`, `opportunities_generated`, `conversion_rate`
   and `roi` are backend-owned and read-only here. They are shown
   exactly as the API reports them — which for a new campaign is
   zero, because the job that recomputes them (P2-W15-BE-05) has
   not been built. Showing a real zero is the point: an invented
   "185% ROI" is indistinguishable from a measured one.
   ============================================================ */

type ViewMode = 'table' | 'cards';

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...CAMPAIGN_STATUSES.map((value) => ({ value, label: humanize(value) })),
];

const TYPE_OPTIONS = [
  { value: '', label: 'All types' },
  ...CAMPAIGN_TYPES.map((value) => ({ value, label: humanize(value) })),
];

const EMPTY_FORM: CampaignInput = {
  name: '',
  type: 'EMAIL',
  status: 'PLANNING',
  start_date: '',
  end_date: '',
  budget: '',
  expected_revenue: '',
  target_audience: '',
  lead_source_id: '',
  products: '',
  notes: '',
};

/** Money arrives as a decimal string so precision survives the wire. */
function formatMoney(value: string | null): string {
  if (value === null || value === '') return '—';
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return amount.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  });
}

function formatPercent(value: string | null): string {
  if (value === null || value === '') return '—';
  const rate = Number(value);
  if (Number.isNaN(rate)) return value;
  return `${rate.toFixed(1)}%`;
}

export default function CampaignsPage() {
  const router = useRouter();
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayCreate = can('campaigns', 'CREATE');
  const mayEdit = can('campaigns', 'EDIT');
  const mayDelete = can('campaigns', 'DELETE');
  const mayViewSources = can('lead_sources', 'VIEW');

  const [view, setView] = useState<ViewMode>('cards');
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [page, setPage] = useState(1);

  const fetcher = useCallback(
    () =>
      listCampaigns({
        page,
        page_size: 25,
        search: search.trim() || null,
        status: (statusFilter || null) as CampaignStatus | null,
        type: (typeFilter || null) as CampaignType | null,
        sort_by: 'created_at',
        sort_dir: 'desc',
      }),
    [page, search, statusFilter, typeFilter],
  );

  const { status, items, pagination, error, reload, refreshing } = useCollection<Campaign>(
    fetcher,
    [page, search, statusFilter, typeFilter],
    { errorMessage: 'Something went wrong loading campaigns.' },
  );

  /* ---- Lead sources for the attribution picker ---- */
  const [sources, setSources] = useState<LeadSource[]>([]);
  useEffect(() => {
    if (!mayViewSources) return;
    let cancelled = false;
    void (async () => {
      try {
        const result = await listLeadSources({ page_size: 200, status: 'ACTIVE' });
        if (!cancelled) setSources(result.data);
      } catch {
        // A campaign can be saved without a source; the picker simply stays empty.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [mayViewSources]);

  const sourceNames = useMemo(
    () => new Map(sources.map((source) => [source.id, source.name])),
    [sources],
  );

  /* ---- Drawer ---- */
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState<Campaign | null>(null);
  const [form, setForm] = useState<CampaignInput>(EMPTY_FORM);
  const { pending, error: saveError, clearError, run } = useMutation();

  const openAdd = () => {
    setEditing(null);
    setForm(EMPTY_FORM);
    clearError();
    setDrawerOpen(true);
  };

  const openEdit = (row: Campaign) => {
    setEditing(row);
    setForm({
      name: row.name,
      type: row.type,
      status: row.status,
      start_date: row.start_date ?? '',
      end_date: row.end_date ?? '',
      budget: row.budget ?? '',
      expected_revenue: row.expected_revenue ?? '',
      target_audience: row.target_audience ?? '',
      lead_source_id: row.lead_source_id ?? '',
      products: row.products ?? '',
      notes: row.notes ?? '',
    });
    clearError();
    setDrawerOpen(true);
  };

  const handleSave = async () => {
    if (!form.name.trim()) return;
    // Empty strings are dropped rather than sent: the backend types these as
    // optional dates and decimals, and "" is neither.
    const body: CampaignInput = {
      name: form.name.trim(),
      type: form.type,
      status: form.status,
      start_date: form.start_date || null,
      end_date: form.end_date || null,
      budget: form.budget || null,
      expected_revenue: form.expected_revenue || null,
      target_audience: form.target_audience?.trim() || null,
      lead_source_id: form.lead_source_id || null,
      products: form.products?.trim() || null,
      notes: form.notes?.trim() || null,
    };
    const saved = await run(() =>
      editing ? updateCampaign(editing.id, body) : createCampaign(body),
    );
    if (saved === undefined) return;
    setDrawerOpen(false);
    notifySuccess(editing ? 'Campaign updated' : 'Campaign created', body.name);
    reload();
  };

  const handleDelete = async (row: Campaign) => {
    const ok = await confirm({
      title: `Archive ${row.name}?`,
      description:
        'The campaign leaves lists and reports. Leads already attributed to it keep the attribution, so its historical influence is not rewritten.',
      confirmLabel: 'Archive campaign',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archiveCampaign(row.id);
      notifySuccess('Campaign archived', row.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'The campaign could not be archived.');
    }
  };

  const columns = useMemo<ColumnDef<Campaign>[]>(
    () => [
      { key: 'name', label: 'Campaign', minWidth: '200px' },
      {
        key: 'type',
        label: 'Type',
        hideBelow: 'md',
        render: (row) => <span className="txt-muted text-[12.5px]">{humanize(row.type)}</span>,
      },
      {
        key: 'status',
        label: 'Status',
        render: (row) => (
          <StatusBadge label={humanize(row.status)} variant={statusVariant(row.status)} />
        ),
      },
      {
        key: 'budget',
        label: 'Budget',
        align: 'right',
        hideBelow: 'lg',
        render: (row) => <span className="tabular-nums">{formatMoney(row.budget)}</span>,
      },
      {
        key: 'leads_generated',
        label: 'Leads',
        align: 'right',
        render: (row) => <span className="tabular-nums">{row.leads_generated}</span>,
      },
      {
        key: 'member_count',
        label: 'Members',
        align: 'right',
        hideBelow: 'md',
        render: (row) => <span className="tabular-nums">{row.member_count}</span>,
      },
      {
        key: 'actions',
        label: '',
        align: 'right',
        render: (row) => (
          <div className="flex items-center justify-end gap-1">
            {mayEdit && (
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
    [mayEdit, mayDelete],
  );

  const emptyState = (
    <ListEmpty
      title="No campaigns yet"
      hint={
        search || statusFilter || typeFilter
          ? 'No campaign matches those filters.'
          : 'Create a campaign to group the leads and contacts a piece of marketing produced.'
      }
    />
  );

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-fuchsia-500 to-purple-600">
            <Megaphone className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Campaigns</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              Marketing programmes and the pipeline they produce.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="bd flex rounded-lg border p-0.5">
            <button
              type="button"
              onClick={() => setView('cards')}
              aria-pressed={view === 'cards'}
              aria-label="Card view"
              className={`rounded-md p-1.5 transition ${view === 'cards' ? 'surface-2 txt' : 'txt-faint'}`}
            >
              <LayoutGrid className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => setView('table')}
              aria-pressed={view === 'table'}
              aria-label="Table view"
              className={`rounded-md p-1.5 transition ${view === 'table' ? 'surface-2 txt' : 'txt-faint'}`}
            >
              <LayoutList className="h-4 w-4" />
            </button>
          </div>
          {mayCreate && (
            <button
              type="button"
              onClick={openAdd}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              <Plus className="h-4 w-4" /> New campaign
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
          placeholder="Search campaigns…"
        />
        <FilterSelect
          value={statusFilter}
          onChange={(event) => {
            setStatusFilter(event.target.value);
            setPage(1);
          }}
          options={STATUS_OPTIONS}
        />
        <FilterSelect
          value={typeFilter}
          onChange={(event) => {
            setTypeFilter(event.target.value);
            setPage(1);
          }}
          options={TYPE_OPTIONS}
        />
        {refreshing && (
          <Loader2 className="txt-faint h-4 w-4 motion-safe:animate-spin" aria-label="Refreshing" />
        )}
        <div className="ml-auto">
          <ResultCount shown={items.length} total={pagination?.total ?? 0} />
        </div>
      </div>

      {status === 'error' && error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : view === 'table' ? (
        <DataTable
          columns={columns}
          data={items}
          rowKey={(row) => row.id}
          loading={status === 'loading'}
          skeletonRows={6}
          onRowClick={(row) => router.push(`/campaigns/${row.id}`)}
          emptyState={emptyState}
        />
      ) : status === 'loading' ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }, (_, index) => (
            <div
              key={index}
              className="motion-safe:animate-pulse h-[168px] rounded-2xl"
              style={{ background: 'var(--surface-2)' }}
            />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="surface bd rounded-2xl border">{emptyState}</div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((campaign) => (
            <button
              key={campaign.id}
              type="button"
              onClick={() => router.push(`/campaigns/${campaign.id}`)}
              className="surface bd flex flex-col gap-3 rounded-2xl border p-5 text-left transition hover:border-[var(--accent)]"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="txt truncate text-[14px] font-bold">{campaign.name}</p>
                  <p className="txt-muted mt-0.5 text-[12px]">{humanize(campaign.type)}</p>
                </div>
                <StatusBadge
                  label={humanize(campaign.status)}
                  variant={statusVariant(campaign.status)}
                />
              </div>

              <div className="grid grid-cols-3 gap-2 pt-1">
                <div>
                  <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wide">Leads</p>
                  <p className="txt mt-0.5 text-[15px] font-bold tabular-nums">
                    {campaign.leads_generated}
                  </p>
                </div>
                <div>
                  <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wide">Deals</p>
                  <p className="txt mt-0.5 text-[15px] font-bold tabular-nums">
                    {campaign.opportunities_generated}
                  </p>
                </div>
                <div>
                  <p className="txt-faint text-[10.5px] font-bold uppercase tracking-wide">Conv.</p>
                  <p className="txt mt-0.5 text-[15px] font-bold tabular-nums">
                    {formatPercent(campaign.conversion_rate)}
                  </p>
                </div>
              </div>

              <div className="bd flex items-center justify-between border-t pt-2.5 text-[11.5px]">
                <span className="txt-muted">
                  {campaign.lead_source_id
                    ? (sourceNames.get(campaign.lead_source_id) ?? 'Attributed source')
                    : 'No source'}
                </span>
                <span className="txt-faint tabular-nums">{campaign.member_count} members</span>
              </div>
            </button>
          ))}
        </div>
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title={editing ? 'Edit campaign' : 'New campaign'}
        subtitle={editing ? editing.name : 'Plan a marketing programme.'}
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
              disabled={pending || !form.name.trim()}
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
              placeholder="Q3 enterprise outreach"
            />
          </FormField>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Type" required>
              <FormSelect
                value={form.type}
                onChange={(event) =>
                  setForm({ ...form, type: event.target.value as CampaignType })
                }
                options={CAMPAIGN_TYPES.map((value) => ({ value, label: humanize(value) }))}
              />
            </FormField>
            <FormField label="Status">
              <FormSelect
                value={form.status ?? 'PLANNING'}
                onChange={(event) =>
                  setForm({ ...form, status: event.target.value as CampaignStatus })
                }
                options={CAMPAIGN_STATUSES.map((value) => ({ value, label: humanize(value) }))}
              />
            </FormField>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Starts">
              <FormInput
                type="date"
                value={form.start_date ?? ''}
                onChange={(event) => setForm({ ...form, start_date: event.target.value })}
              />
            </FormField>
            <FormField label="Ends" hint="Must not fall before the start date.">
              <FormInput
                type="date"
                value={form.end_date ?? ''}
                onChange={(event) => setForm({ ...form, end_date: event.target.value })}
              />
            </FormField>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Budget">
              <FormInput
                type="number"
                min="0"
                step="0.01"
                value={form.budget ?? ''}
                onChange={(event) => setForm({ ...form, budget: event.target.value })}
                placeholder="15000"
              />
            </FormField>
            <FormField label="Expected revenue">
              <FormInput
                type="number"
                min="0"
                step="0.01"
                value={form.expected_revenue ?? ''}
                onChange={(event) => setForm({ ...form, expected_revenue: event.target.value })}
                placeholder="150000"
              />
            </FormField>
          </div>

          <FormField
            label="Attributed lead source"
            hint="Leads created from this campaign roll up to the source you pick."
          >
            <FormSelect
              value={form.lead_source_id ?? ''}
              onChange={(event) => setForm({ ...form, lead_source_id: event.target.value })}
              placeholder="No source"
              disabled={!mayViewSources}
              options={sources.map((source) => ({ value: source.id, label: source.name }))}
            />
          </FormField>

          <FormField label="Target audience">
            <FormInput
              value={form.target_audience ?? ''}
              onChange={(event) => setForm({ ...form, target_audience: event.target.value })}
              placeholder="CTOs, IT directors"
            />
          </FormField>

          <FormField label="Products">
            <FormInput
              value={form.products ?? ''}
              onChange={(event) => setForm({ ...form, products: event.target.value })}
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
