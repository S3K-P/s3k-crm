'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { LayoutGrid, Lock, Plus, Star, Users } from 'lucide-react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { ListEmpty, ListError } from '@/components/crm/shared/ListStates';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import {
  createDashboard,
  listDashboards,
  type Dashboard,
} from '@/features/crm/dashboards';
import type { ShareScope } from '@/features/crm/reports/library';

/* ============================================================
   DASHBOARDS

   The index. A dashboard is a named arrangement of saved
   reports; this screen creates them and lists the ones you can
   open — your own, plus anything a colleague has shared.

   The tiles themselves live on the detail page, because that is
   where they have room to be read.
   ============================================================ */

export default function DashboardsPage() {
  const [dashboards, setDashboards] = useState<Dashboard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<ShareScope>('PRIVATE');
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Loading lives in the effect rather than in a callback the effect invokes:
  // `react-hooks/set-state-in-effect` reads through a `useCallback` and flags
  // the setState it can reach, and it is right to — a fetch that resolves
  // after the user has navigated away should not touch state, which is what
  // the `cancelled` flag is for.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const page = await listDashboards();
        if (cancelled) return;
        setDashboards(page.data);
        setError(null);
      } catch (cause) {
        if (!cancelled) setError(describeApiError(cause, 'Unable to load dashboards.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reload]);

  const refresh = useCallback(() => setReload(count => count + 1), []);

  const submit = async () => {
    setBusy(true);
    setFormError(null);
    try {
      await createDashboard({
        name: name.trim(),
        description: description.trim() || null,
        visibility,
      });
      setName('');
      setDescription('');
      setVisibility('PRIVATE');
      setOpen(false);
      refresh();
    } catch (cause) {
      setFormError(describeApiError(cause, 'Unable to create this dashboard.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full flex-col space-y-5 p-4 sm:p-6 lg:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-500 to-indigo-600">
            <LayoutGrid className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold leading-tight tracking-tight">
              Dashboards
            </h1>
            <p className="txt-muted mt-0.5 text-[13px] font-medium">
              Arrange saved reports. Everyone who opens one sees their own numbers.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => {
            setFormError(null);
            setOpen(true);
          }}
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-[12.5px] font-semibold text-white transition hover:opacity-90"
          style={{ background: 'var(--accent)' }}
        >
          <Plus className="h-4 w-4" /> New dashboard
        </button>
      </div>

      {error && (
        <ListError message={error} onRetry={() => setReload(count => count + 1)} />
      )}

      {dashboards?.length === 0 && (
        <ListEmpty
          title="No dashboards yet"
          hint="Save a report first, then build a dashboard from it."
        />
      )}

      {dashboards && dashboards.length > 0 && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {dashboards.map(dashboard => (
            <Link
              key={dashboard.id}
              href={`/dashboards/${dashboard.id}`}
              className="surface bd group rounded-2xl border p-5 transition hover:border-[var(--accent)]"
            >
              <div className="flex items-start justify-between gap-3">
                <h2 className="txt font-display text-[15px] font-bold group-hover:text-[var(--accent)]">
                  {dashboard.name}
                </h2>
                <div className="flex shrink-0 items-center gap-1.5">
                  {dashboard.is_default && (
                    <Star
                      className="h-3.5 w-3.5 fill-amber-400 text-amber-400"
                      aria-label="Your default"
                    />
                  )}
                  {dashboard.visibility === 'SHARED' ? (
                    <Users className="txt-faint h-3.5 w-3.5" aria-label="Shared" />
                  ) : (
                    <Lock className="txt-faint h-3.5 w-3.5" aria-label="Private" />
                  )}
                </div>
              </div>
              {dashboard.description && (
                <p className="txt-muted mt-1.5 line-clamp-2 text-[12.5px]">
                  {dashboard.description}
                </p>
              )}
            </Link>
          ))}
        </div>
      )}

      <SlideDrawer
        open={open}
        onClose={() => setOpen(false)}
        title="New dashboard"
        subtitle="Add tiles once it exists."
        footer={
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[12.5px] font-semibold"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={busy || !name.trim()}
              onClick={() => void submit()}
              className="rounded-lg px-4 py-2 text-[12.5px] font-semibold text-white disabled:opacity-60"
              style={{ background: 'var(--accent)' }}
            >
              {busy ? 'Creating…' : 'Create'}
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          {formError && (
            <p role="alert" className="text-[12.5px] text-rose-500">
              {formError}
            </p>
          )}
          <label className="block">
            <span className="txt-faint mb-1 block text-[10.5px] font-bold uppercase tracking-wider">
              Name
            </span>
            <input
              value={name}
              onChange={event => setName(event.target.value)}
              maxLength={120}
              className="ctl txt w-full px-3 py-2 text-[13px]"
            />
          </label>
          <label className="block">
            <span className="txt-faint mb-1 block text-[10.5px] font-bold uppercase tracking-wider">
              Description
            </span>
            <textarea
              value={description}
              onChange={event => setDescription(event.target.value)}
              rows={2}
              className="ctl txt w-full px-3 py-2 text-[13px]"
            />
          </label>
          <label className="block">
            <span className="txt-faint mb-1 block text-[10.5px] font-bold uppercase tracking-wider">
              Visibility
            </span>
            <select
              value={visibility}
              onChange={event => setVisibility(event.target.value as ShareScope)}
              className="ctl txt w-full px-3 py-2 text-[13px]"
            >
              <option value="PRIVATE">Private — only you</option>
              <option value="SHARED">Shared — everyone in the organization</option>
            </select>
            <p className="txt-faint mt-1 text-[11.5px]">
              Sharing a dashboard shares the layout, not the figures — each tile runs
              as whoever is looking at it.
            </p>
          </label>
        </div>
      </SlideDrawer>
    </div>
  );
}
