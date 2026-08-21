'use client';

import { useEffect, useMemo, useState } from 'react';

import FormField, { FormSelect } from '@/components/crm/forms/FormField';
import { usePermissions } from '@/context/AuthContext';
import { listAccounts } from '@/features/crm/accounts';
import { listContacts } from '@/features/crm/contacts';
import { listLeads } from '@/features/crm/leads';
import { listOpportunities } from '@/features/crm/opportunities';
import { listCampaigns } from '@/features/crm/campaigns';
import type { CrmEntityType } from '@/features/crm/tasks';

/* ============================================================
   RELATED RECORD FIELDS

   Activities, tasks and notes all attach to a CRM record through
   the same polymorphic pair — `related_entity_type` plus
   `related_entity_id`. The backend validates that the target
   exists *inside the caller's organization* on every write
   (`resolve_related_entity`), so a stale or foreign id is
   rejected rather than stored.

   This component is the one picker for that pair. Before it,
   tasks could be created but never linked to anything, so a task
   never appeared on any record's timeline — the relationship
   existed in the schema and in the API and was simply
   unreachable from the UI.

   Each entity type is fetched only if the caller may read it.
   Someone without `opportunities.VIEW` sees no Opportunity
   option rather than an option that returns 403 on submit.
   ============================================================ */

export interface RelatedOption {
  id: string;
  label: string;
}

export interface RelatedRecordOptions {
  byType: Record<CrmEntityType, RelatedOption[]>;
  /** Entity types the caller may actually read. */
  available: CrmEntityType[];
  /** Display name for a stored pair; falls back to the raw id. */
  label: (entityType: CrmEntityType, entityId: string) => string;
  loading: boolean;
}

const ENTITY_LABELS: Record<CrmEntityType, string> = {
  ACCOUNT: 'Account',
  CONTACT: 'Contact',
  LEAD: 'Lead',
  OPPORTUNITY: 'Opportunity',
  CAMPAIGN: 'Campaign',
};

/** How many candidates to offer per type. Enough for a picker, not a report. */
const WINDOW = 200;

const EMPTY: Record<CrmEntityType, RelatedOption[]> = {
  ACCOUNT: [],
  CONTACT: [],
  LEAD: [],
  OPPORTUNITY: [],
  CAMPAIGN: [],
};

export function useRelatedRecordOptions(): RelatedRecordOptions {
  const { can } = usePermissions();

  const mayAccounts = can('accounts', 'VIEW');
  const mayContacts = can('contacts', 'VIEW');
  const mayLeads = can('leads', 'VIEW');
  const mayOpportunities = can('opportunities', 'VIEW');
  const mayCampaigns = can('campaigns', 'VIEW');

  const [byType, setByType] = useState<Record<CrmEntityType, RelatedOption[]>>(EMPTY);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      setLoading(true);
      const next: Record<CrmEntityType, RelatedOption[]> = { ...EMPTY };

      // Each lookup is independent: one failing (or being forbidden) must not
      // empty the others, so results are settled rather than awaited together.
      const jobs: Promise<void>[] = [];

      if (mayAccounts) {
        jobs.push(
          listAccounts({ page_size: WINDOW, sort_by: 'name', sort_dir: 'asc' })
            .then((page) => {
              next.ACCOUNT = page.data.map((row) => ({ id: row.id, label: row.name }));
            })
            .catch(() => undefined),
        );
      }
      if (mayContacts) {
        jobs.push(
          listContacts({ page_size: WINDOW, sort_by: 'last_name', sort_dir: 'asc' })
            .then((page) => {
              next.CONTACT = page.data.map((row) => ({ id: row.id, label: row.full_name }));
            })
            .catch(() => undefined),
        );
      }
      if (mayLeads) {
        jobs.push(
          listLeads({ page_size: WINDOW, sort_by: 'created_at', sort_dir: 'desc' })
            .then((page) => {
              next.LEAD = page.data.map((row) => ({
                id: row.id,
                label: [`${row.first_name} ${row.last_name}`.trim(), row.company]
                  .filter(Boolean)
                  .join(' — '),
              }));
            })
            .catch(() => undefined),
        );
      }
      if (mayOpportunities) {
        jobs.push(
          listOpportunities({ page_size: WINDOW, sort_by: 'created_at', sort_dir: 'desc' })
            .then((page) => {
              next.OPPORTUNITY = page.data.map((row) => ({ id: row.id, label: row.name }));
            })
            .catch(() => undefined),
        );
      }
      if (mayCampaigns) {
        jobs.push(
          listCampaigns({ page_size: WINDOW, sort_by: 'created_at', sort_dir: 'desc' })
            .then((page) => {
              next.CAMPAIGN = page.data.map((row) => ({ id: row.id, label: row.name }));
            })
            .catch(() => undefined),
        );
      }

      await Promise.all(jobs);
      if (!cancelled) {
        setByType(next);
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mayAccounts, mayContacts, mayLeads, mayOpportunities, mayCampaigns]);

  const available = useMemo(() => {
    const types: CrmEntityType[] = [];
    if (mayAccounts) types.push('ACCOUNT');
    if (mayContacts) types.push('CONTACT');
    if (mayLeads) types.push('LEAD');
    if (mayOpportunities) types.push('OPPORTUNITY');
    if (mayCampaigns) types.push('CAMPAIGN');
    return types;
  }, [mayAccounts, mayContacts, mayLeads, mayOpportunities, mayCampaigns]);

  const index = useMemo(() => {
    const map = new Map<string, string>();
    for (const [type, options] of Object.entries(byType)) {
      for (const option of options) map.set(`${type}:${option.id}`, option.label);
    }
    return map;
  }, [byType]);

  return {
    byType,
    available,
    loading,
    // A linked record outside the fetched window still renders — as its id,
    // which is honest, rather than as "Unknown".
    label: (entityType, entityId) => index.get(`${entityType}:${entityId}`) ?? entityId,
  };
}

export default function RelatedRecordFields({
  options,
  entityType,
  entityId,
  onChange,
  label = 'Linked record',
  hint = 'Attaching this to a record makes it appear on that record’s timeline.',
}: {
  options: RelatedRecordOptions;
  entityType: CrmEntityType | '';
  entityId: string;
  onChange: (entityType: CrmEntityType | '', entityId: string) => void;
  label?: string;
  hint?: string;
}) {
  const candidates = entityType ? options.byType[entityType] : [];

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <FormField label={label} hint={hint}>
        <FormSelect
          value={entityType}
          onChange={(event) => onChange(event.target.value as CrmEntityType | '', '')}
          placeholder="Not linked"
          options={options.available.map((value) => ({
            value,
            label: ENTITY_LABELS[value],
          }))}
        />
      </FormField>

      <FormField label={entityType ? ENTITY_LABELS[entityType] : 'Record'}>
        <FormSelect
          value={entityId}
          onChange={(event) => onChange(entityType, event.target.value)}
          disabled={!entityType || options.loading}
          placeholder={
            options.loading
              ? 'Loading…'
              : entityType
                ? candidates.length === 0
                  ? 'None available'
                  : 'Choose a record…'
                : 'Pick a type first'
          }
          options={candidates.map((option) => ({ value: option.id, label: option.label }))}
        />
      </FormField>
    </div>
  );
}
