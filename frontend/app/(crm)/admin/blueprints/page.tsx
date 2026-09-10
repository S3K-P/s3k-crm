'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { GitBranch, Loader2, Plus, Trash2 } from 'lucide-react';

import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import { FormError, ListError } from '@/components/crm/shared/ListStates';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError, useMutation } from '@/features/shared/hooks/useCollection';
import {
  ANY_STATE,
  BLUEPRINT_FIELDS,
  FIELD_LABELS,
  addTransition,
  archiveBlueprint,
  createBlueprint,
  describeRequirements,
  getBlueprint,
  listBlueprintStates,
  listBlueprints,
  removeTransition,
  stateLabel,
  updateBlueprint,
  type Blueprint,
  type BlueprintField,
  type BlueprintState,
  type BlueprintTransition,
} from '@/features/crm/blueprints';

/* ============================================================
   ADMIN — BLUEPRINTS

   Where an organization describes its own process: which moves
   through a lead's status or a deal's stage it allows, and what
   must be true before each one.

   **The screen never pretends a blueprint can widen anything.**
   The API refuses a rule for a move the built-in state machine
   would not allow, and the error says so; there is no client-side
   list of "legal moves" here, because a second copy of that rule
   would eventually disagree with the one that decides.

   States are fetched per field rather than compiled in. An
   opportunity's states are the tenant's own pipeline stages, and
   offering one that was retired last week is exactly how an
   unsatisfiable process gets built.

   Activation is a separate act from creation, and the screen says
   what it means: from that moment the process starts refusing
   colleagues' work.
   ============================================================ */

const FIELD_OPTIONS = BLUEPRINT_FIELDS.map((value) => ({
  value,
  label: FIELD_LABELS[value],
}));

export default function AdminBlueprintsPage() {
  const confirm = useConfirm();
  const { can } = usePermissions();
  const mayView = can('blueprints', 'VIEW');
  const mayCreate = can('blueprints', 'CREATE');
  const mayEdit = can('blueprints', 'EDIT');
  const mayDelete = can('blueprints', 'DELETE');

  const [blueprints, setBlueprints] = useState<Blueprint[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  const [expanded, setExpanded] = useState<Blueprint | null>(null);
  const [states, setStates] = useState<BlueprintState[]>([]);

  useEffect(() => {
    if (!mayView) return;
    let cancelled = false;

    void (async () => {
      try {
        const loaded = await listBlueprints();
        if (cancelled) return;
        setBlueprints(loaded);
        setError(null);
      } catch (caught) {
        if (cancelled) return;
        setBlueprints([]);
        setError(describeApiError(caught, 'Blueprints could not be loaded.'));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [mayView, attempt]);

  const open = async (blueprint: Blueprint) => {
    try {
      // Both at once: the rule list needs the states to render a label, and
      // neither request depends on the other's result.
      const [detail, available] = await Promise.all([
        getBlueprint(blueprint.id),
        listBlueprintStates(blueprint.field),
      ]);
      setExpanded(detail);
      setStates(available.states);
    } catch (caught) {
      notifyError(caught, 'The blueprint could not be opened.');
    }
  };

  const refreshOpen = async () => {
    if (!expanded) return;
    try {
      setExpanded(await getBlueprint(expanded.id));
    } catch (caught) {
      notifyError(caught, 'The blueprint could not be reloaded.');
    }
    reload();
  };

  const toggleActive = async (blueprint: Blueprint) => {
    if (!blueprint.is_active) {
      const ok = await confirm({
        title: `Activate "${blueprint.name}"?`,
        description:
          'From now on this process decides which moves colleagues may make on these records, and what they must fill in first. Records already in a state the process does not describe are left alone.',
        confirmLabel: 'Activate',
      });
      if (!ok) return;
    }
    try {
      await updateBlueprint(blueprint.id, { is_active: !blueprint.is_active });
      notifySuccess(
        blueprint.is_active ? 'Blueprint deactivated' : 'Blueprint activated',
        blueprint.name,
      );
      if (expanded?.id === blueprint.id) await refreshOpen();
      else reload();
    } catch (caught) {
      // Activation validates the whole process server-side; the message names
      // what is wrong (no moves, a stale state, another blueprint already
      // active) and is worth showing verbatim.
      notifyError(caught, 'The blueprint could not be activated.');
    }
  };

  const archive = async (blueprint: Blueprint) => {
    const ok = await confirm({
      title: `Remove "${blueprint.name}"?`,
      description:
        'It stops constraining records immediately. No record is changed — a blueprint decides what may happen, not what has.',
      confirmLabel: 'Remove blueprint',
      tone: 'danger',
    });
    if (!ok) return;
    try {
      await archiveBlueprint(blueprint.id);
      notifySuccess('Blueprint removed', blueprint.name);
      if (expanded?.id === blueprint.id) setExpanded(null);
      reload();
    } catch (caught) {
      notifyError(caught, 'The blueprint could not be removed.');
    }
  };

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [form, setForm] = useState({
    name: '',
    field: 'LEAD_STATUS' as BlueprintField,
    description: '',
  });
  const { pending, error: saveError, clearError, run } = useMutation();

  const save = async () => {
    if (!form.name.trim()) return;
    const created = await run(() =>
      createBlueprint({
        name: form.name.trim(),
        field: form.field,
        description: form.description.trim() || null,
      }),
    );
    if (created === undefined) return;
    setDrawerOpen(false);
    notifySuccess('Blueprint created', `${created.name} — add its moves, then activate it.`);
    reload();
  };

  if (!mayView) {
    return (
      <div className="p-6 lg:p-8">
        <h1 className="font-display txt text-[22px] font-extrabold">Blueprints</h1>
        <p className="txt-muted mt-1 text-[13px]">
          You do not have permission to view this organization&apos;s processes.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-amber-500 to-orange-600">
            <GitBranch className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Blueprints</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              Which moves through a lifecycle your organization allows, and what must be
              filled in first.
            </p>
          </div>
        </div>
        {mayCreate && (
          <button
            type="button"
            onClick={() => {
              setForm({ name: '', field: 'LEAD_STATUS', description: '' });
              clearError();
              setDrawerOpen(true);
            }}
            className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90"
            style={{ background: 'var(--accent)' }}
          >
            <Plus className="h-4 w-4" /> New blueprint
          </button>
        )}
      </div>

      {error !== null ? (
        <ListError message={error} onRetry={reload} />
      ) : blueprints === null ? (
        <Loader2 className="txt-faint h-5 w-5 motion-safe:animate-spin" aria-label="Loading" />
      ) : blueprints.length === 0 ? (
        <p className="txt-muted text-[13px]">
          No blueprints yet. Records follow the product&apos;s built-in lifecycle until you
          add one.
        </p>
      ) : (
        <ul className="space-y-2" data-testid="blueprint-list">
          {blueprints.map((blueprint) => (
            <li key={blueprint.id} className="ctl rounded-lg px-4 py-3">
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  onClick={() => void open(blueprint)}
                  className="min-w-0 flex-1 text-left"
                  aria-expanded={expanded?.id === blueprint.id}
                >
                  <p className="txt text-[13px] font-semibold">{blueprint.name}</p>
                  <p className="txt-faint text-[11px]">
                    {FIELD_LABELS[blueprint.field]} · {blueprint.transition_count} move
                    {blueprint.transition_count === 1 ? '' : 's'}
                  </p>
                </button>
                <StatusBadge
                  label={blueprint.is_active ? 'Active' : 'Draft'}
                  variant={blueprint.is_active ? 'success' : 'neutral'}
                />
                {mayEdit && (
                  <button
                    type="button"
                    onClick={() => void toggleActive(blueprint)}
                    className="txt-faint text-[12px] underline transition hover:opacity-70"
                  >
                    {blueprint.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                )}
                {mayDelete && (
                  <button
                    type="button"
                    aria-label={`Remove ${blueprint.name}`}
                    onClick={() => void archive(blueprint)}
                    className="ctl rounded-lg p-1.5 text-red-500 transition hover:opacity-70"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>

              {expanded?.id === blueprint.id && (
                <TransitionList
                  blueprint={expanded}
                  states={states}
                  mayEdit={mayEdit}
                  onChanged={() => void refreshOpen()}
                />
              )}
            </li>
          ))}
        </ul>
      )}

      <SlideDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        title="New blueprint"
        subtitle="Created as a draft. Add its moves, then activate it."
        footer={
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setDrawerOpen(false)}
              className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold transition hover:opacity-80"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={pending}
              className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:opacity-60"
              style={{ background: 'var(--accent)' }}
            >
              {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" />}
              Create blueprint
            </button>
          </div>
        }
      >
        <div className="space-y-4">
          <FormError message={saveError} />
          <FormField label="Name" required>
            <FormInput
              value={form.name}
              onChange={(event) => setForm({ ...form, name: event.target.value })}
              placeholder="Lead qualification process"
            />
          </FormField>
          <FormField
            label="Governs"
            required
            hint="Which state field this process describes. It cannot be changed later — the moves name states of that field."
          >
            <FormSelect
              value={form.field}
              onChange={(event) =>
                setForm({ ...form, field: event.target.value as BlueprintField })
              }
              options={FIELD_OPTIONS}
            />
          </FormField>
          <FormField label="Description">
            <FormTextarea
              rows={2}
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
            />
          </FormField>
        </div>
      </SlideDrawer>
    </div>
  );
}

function TransitionList({
  blueprint,
  states,
  mayEdit,
  onChanged,
}: {
  blueprint: Blueprint;
  states: BlueprintState[];
  mayEdit: boolean;
  onChanged: () => void;
}) {
  const [from, setFrom] = useState(ANY_STATE);
  const [to, setTo] = useState('');
  const [requiredFields, setRequiredFields] = useState('');
  const [requireNote, setRequireNote] = useState(false);
  const [adding, setAdding] = useState(false);

  const stateOptions = useMemo(
    () => [
      { value: ANY_STATE, label: 'Any state' },
      ...states.map((state) => ({ value: state.value, label: state.label })),
    ],
    [states],
  );

  const add = async () => {
    if (!to) return;
    setAdding(true);
    try {
      await addTransition(blueprint.id, {
        from_state: from,
        to_state: to,
        required_fields: requiredFields
          .split(',')
          .map((name) => name.trim())
          .filter(Boolean),
        require_note: requireNote,
      });
      setTo('');
      setRequiredFields('');
      setRequireNote(false);
      onChanged();
    } catch (caught) {
      // The API refuses a move the built-in machine would not allow, and says
      // why. Shown verbatim rather than replaced with a generic message.
      notifyError(caught, 'The move could not be added.');
    } finally {
      setAdding(false);
    }
  };

  const remove = async (transition: BlueprintTransition) => {
    try {
      await removeTransition(blueprint.id, transition.id);
      onChanged();
    } catch (caught) {
      notifyError(caught, 'The move could not be removed.');
    }
  };

  return (
    <div className="bd mt-3 space-y-2 border-t pt-3">
      {(blueprint.transitions ?? []).length === 0 && (
        <p className="txt-faint text-[12px]">
          No moves yet. A blueprint with none cannot be activated — it would constrain
          nothing.
        </p>
      )}

      {(blueprint.transitions ?? []).map((transition) => (
        <div key={transition.id} className="flex flex-wrap items-center gap-2 text-[12px]">
          <span className="txt font-medium">
            {stateLabel(states, transition.from_state)} → {stateLabel(states, transition.to_state)}
          </span>
          <span className="txt-faint">{describeRequirements(transition)}</span>
          {mayEdit && (
            <button
              type="button"
              aria-label={`Remove the move to ${stateLabel(states, transition.to_state)}`}
              onClick={() => void remove(transition)}
              className="ctl ml-auto rounded-lg p-1 text-red-500 transition hover:opacity-70"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          )}
        </div>
      ))}

      {mayEdit && (
        <div className="flex flex-wrap items-end gap-2 pt-2">
          {/* Named explicitly. `FormField` wraps its label *around* the control,
              so a select's accessible name is the label's text followed by the
              selected option's — "To" announces as "ToChoose…", which is not a
              name anybody can act on. The visible word is contained in the name
              given here, as WCAG's label-in-name rule requires. */}
          <FormField label="From" className="w-[150px]">
            <FormSelect
              aria-label="From state"
              value={from}
              onChange={(event) => setFrom(event.target.value)}
              options={stateOptions}
            />
          </FormField>
          <FormField label="To" className="w-[150px]">
            <FormSelect
              aria-label="To state"
              value={to}
              onChange={(event) => setTo(event.target.value)}
              placeholder="Choose…"
              options={states.map((state) => ({ value: state.value, label: state.label }))}
            />
          </FormField>
          <FormField
            label="Required fields"
            className="w-[220px]"
            hint="Comma-separated API names, built-in or custom."
          >
            <FormInput
              value={requiredFields}
              onChange={(event) => setRequiredFields(event.target.value)}
              placeholder="company, region"
            />
          </FormField>
          <label className="flex items-center gap-2 pb-2.5 text-[12px]">
            <input
              type="checkbox"
              checked={requireNote}
              onChange={(event) => setRequireNote(event.target.checked)}
              className="h-3.5 w-3.5"
            />
            <span className="txt font-medium">Needs a note</span>
          </label>
          <button
            type="button"
            onClick={() => void add()}
            disabled={adding || !to}
            className="mb-2 rounded-lg px-3 py-1.5 text-[12px] font-semibold text-white transition hover:opacity-90 disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            Add move
          </button>
        </div>
      )}

      <p className="txt-faint pt-1 text-[11px]">
        A blueprint narrows what is possible; it never widens it. A move the product does not
        allow cannot be added here, and a state this process never mentions stays open — so
        activating one does not freeze records it says nothing about.
      </p>
    </div>
  );
}
