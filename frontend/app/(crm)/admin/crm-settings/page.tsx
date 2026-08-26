'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Loader2, Settings } from 'lucide-react';

import SectionHeader from '@/components/crm/shared/SectionHeader';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { PartialDataNotice } from '@/components/crm/shared/NotConfigured';
import { describeApiError } from '@/features/shared/hooks/useCollection';
import { usePermissions } from '@/context/AuthContext';
import { listStages, type PipelineStage } from '@/features/crm/opportunities';
import { listLeadSources, type LeadSource } from '@/features/crm/lead-sources';
import { LEAD_STATUSES } from '@/features/crm/leads';
import { humanize } from '@/components/crm/shared/statusVariants';

/* ============================================================
   ADMIN — CRM SETTINGS

   Shows the configuration that actually exists: the pipeline
   stages seeded for this organization, and its lead sources.
   Both are read from the API, so the counts match reality rather
   than the "2 Active / 7 Stages / 5 Statuses" that were
   previously written into the markup.

   Editing stages is not offered because there is no endpoint for
   it — `GET /crm/opportunities/stages` is read-only. Lead
   sources *are* editable, so this page links to the screen that
   does it rather than duplicating the form.
   ============================================================ */

export default function AdminCRMSettingsPage() {
  const { can } = usePermissions();
  const mayViewStages = can('opportunities', 'VIEW');
  const mayViewSources = can('lead_sources', 'VIEW');

  const [stages, setStages] = useState<PipelineStage[] | null>(null);
  const [sources, setSources] = useState<LeadSource[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      const problems: string[] = [];

      if (mayViewStages) {
        try {
          const loaded = await listStages();
          if (!cancelled) setStages(loaded);
        } catch (caught) {
          problems.push(describeApiError(caught, 'pipeline stages'));
          if (!cancelled) setStages([]);
        }
      } else if (!cancelled) {
        setStages([]);
      }

      if (mayViewSources) {
        try {
          const page = await listLeadSources({ page_size: 200 });
          if (!cancelled) setSources(page.data);
        } catch {
          problems.push('lead sources');
          if (!cancelled) setSources([]);
        }
      } else if (!cancelled) {
        setSources([]);
      }

      if (!cancelled && problems.length > 0) {
        setError(`Could not load: ${problems.join(', ')}.`);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mayViewStages, mayViewSources]);

  const activeSources = (sources ?? []).filter((source) => source.status === 'ACTIVE');
  const loading = stages === null || sources === null;

  return (
    <div className="mx-auto flex h-full max-w-5xl flex-col space-y-6 p-6 lg:p-8">
      <div className="flex items-center gap-3.5">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-slate-600 to-gray-800">
          <Settings className="h-5 w-5 text-white" />
        </div>
        <div>
          <h1 className="font-display txt text-[22px] font-extrabold">CRM Settings</h1>
          <p className="txt-muted mt-0.5 text-[13px]">
            The pipeline and lead-source configuration in effect for this organization.
          </p>
        </div>
      </div>

      {error !== null && (
        <p role="alert" className="text-[12.5px] font-medium text-red-500">
          {error}
        </p>
      )}

      {loading ? (
        <div className="txt-muted flex items-center gap-2 py-8 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading configuration…
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-2">
          <div className="surface bd rounded-2xl border p-5">
            <SectionHeader title={`Pipeline stages (${stages.length})`} />
            <div className="mt-4 space-y-2">
              {stages.length === 0 ? (
                <p className="txt-faint py-4 text-center text-[12.5px]">
                  No pipeline stages are configured for this organization.
                </p>
              ) : (
                [...stages]
                  .sort((a, b) => a.sort_order - b.sort_order)
                  .map((stage) => (
                    <div
                      key={stage.id}
                      className="bd flex items-center justify-between rounded-xl border p-3"
                      style={{ background: 'var(--surface-2)' }}
                    >
                      <div className="flex items-center gap-2.5">
                        <span className="txt-faint w-4 text-[11px] font-bold tabular-nums">
                          {stage.sort_order}
                        </span>
                        <span className="txt text-[13px] font-semibold">{stage.name}</span>
                        {stage.is_won && <StatusBadge label="Won" variant="success" />}
                        {stage.is_lost && <StatusBadge label="Lost" variant="danger" />}
                      </div>
                      <span className="txt-muted text-[12px] tabular-nums">
                        {stage.default_probability !== null
                          ? `${stage.default_probability}%`
                          : '—'}
                      </span>
                    </div>
                  ))
              )}
            </div>
            <p className="txt-faint mt-4 text-[11.5px] leading-relaxed">
              Stages are seeded per organization and read-only here: the API exposes no endpoint for
              renaming or reordering them.
            </p>
          </div>

          <div className="flex flex-col gap-6">
            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader
                title={`Lead sources (${activeSources.length} active of ${sources.length})`}
              />
              <div className="mt-4 space-y-2">
                {sources.length === 0 ? (
                  <p className="txt-faint py-4 text-center text-[12.5px]">
                    No lead sources are configured.
                  </p>
                ) : (
                  sources.slice(0, 6).map((source) => (
                    <div
                      key={source.id}
                      className="bd flex items-center justify-between rounded-xl border p-3"
                      style={{ background: 'var(--surface-2)' }}
                    >
                      <span className="txt text-[13px] font-semibold">{source.name}</span>
                      <span className="txt-muted text-[12px] tabular-nums">
                        {source.lead_count} leads
                      </span>
                    </div>
                  ))
                )}
              </div>
              {mayViewSources && (
                <Link
                  href="/lead-sources"
                  className="mt-4 inline-flex items-center gap-1.5 text-[12.5px] font-semibold hover:underline"
                  style={{ color: 'var(--accent)' }}
                >
                  Manage lead sources <ArrowRight className="h-3.5 w-3.5" />
                </Link>
              )}
            </div>

            <div className="surface bd rounded-2xl border p-5">
              <SectionHeader title={`Lead statuses (${LEAD_STATUSES.length})`} />
              <div className="mt-4 flex flex-wrap gap-2">
                {LEAD_STATUSES.map((value) => (
                  <StatusBadge key={value} label={humanize(value)} variant="neutral" />
                ))}
              </div>
              <p className="txt-faint mt-4 text-[11.5px] leading-relaxed">
                Lead statuses are a fixed enum in the database with a transition state machine
                enforced by the backend. They are not configurable.
              </p>
            </div>
          </div>
        </div>
      )}

      <PartialDataNotice>
        Organization-level preferences — base currency, locale, fiscal year, email templates — are
        not shown because there is no settings API to read or write them. The organization record
        carries a settings field, but nothing exposes it.
      </PartialDataNotice>
    </div>
  );
}
