'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Loader2, Pencil, Plus, RotateCcw, Trash2, Workflow, X } from 'lucide-react';

import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import FilterSelect from '@/components/crm/forms/FilterSelect';
import FormField, { FormInput, FormSelect, FormTextarea } from '@/components/crm/forms/FormField';
import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import { FormError, ListError } from '@/components/crm/shared/ListStates';
import StatusBadge from '@/components/crm/shared/StatusBadge';
import { describeApiError, useMutation } from '@/features/shared/hooks/useCollection';
import {
  createNbaRule,
  deleteNbaRule,
  getNbaCatalog,
  listNbaRules,
  overrideBuiltinRule,
  resetBuiltinRule,
  updateNbaRule,
  type NbaCatalog,
  type NbaCategory,
  type NbaCondition,
  type NbaRecordKind,
  type NbaRule,
  type NbaRuleInput,
} from '@/features/ai/ai-insights';
import { cn } from '@/lib/utils';
import {
  APPLIES_TO_LABEL,
  CATEGORY_LABEL,
  CATEGORY_ORDER,
  CATEGORY_VARIANT,
  LIST_OPERATORS,
  OPERATOR_LABEL,
  PRIORITY_LABEL,
  PRIORITY_VARIANT,
  VALUELESS_OPERATORS,
  conditionValueText,
} from './nba-helpers';

/* ============================================================
   NBA RULES ENGINE (Level 1)

   The built-in rules ("No follow-up for 5 days -> Send follow-up
   email", "Proposal opened 3+ times -> Call customer", …) and the
   tenant's own, read from `GET /nba/rules`.

   Anyone who can see AI Insights can read them — it is the
   "why" behind every rule-based action. Changing them needs
   `ai_insights.ADMIN`, the same gate the API enforces:
   - built-ins can be switched off, re-prioritised or re-thresholded
     (`PUT /rules/builtin/{key}`) and reset to the default;
   - custom rules are created, edited and deleted outright.
   ============================================================ */

type Priority = NbaRule['priority'];
type AppliesTo = NbaRecordKind | 'BOTH';

interface DraftCondition {
  field_key: string;
  operator: string;
  value: string;
}

interface Loaded {
  catalog: NbaCatalog;
  rules: NbaRule[];
}

const PRIORITIES: Priority[] = ['HIGH', 'MEDIUM', 'LOW'];
const APPLIES: AppliesTo[] = ['BOTH', 'OPPORTUNITY', 'LEAD'];

function toDraft(condition: NbaCondition): DraftCondition {
  return { field_key: condition.field_key, operator: condition.operator, value: conditionValueText(condition.value) };
}

function fromDraft(draft: DraftCondition, kind: string | undefined): NbaCondition {
  if (VALUELESS_OPERATORS.has(draft.operator)) return { ...draft, value: null };
  const one = (raw: string): unknown => {
    const text = raw.trim();
    if (kind === 'number') return text === '' || Number.isNaN(Number(text)) ? text : Number(text);
    if (kind === 'boolean') return text === 'true' || text === 'yes';
    return text;
  };
  if (LIST_OPERATORS.has(draft.operator)) {
    return { ...draft, value: draft.value.split(',').map(one).filter((value) => value !== '') };
  }
  return { ...draft, value: one(draft.value) };
}

/* ---- Rule editor ---------------------------------------------------------- */

type EditorTarget = { mode: 'create' } | { mode: 'edit'; rule: NbaRule };

function RuleEditor({
  target,
  catalog,
  onClose,
  onSaved,
}: {
  target: EditorTarget;
  catalog: NbaCatalog;
  onClose: () => void;
  onSaved: () => void;
}) {
  const rule = target.mode === 'edit' ? target.rule : null;
  const builtin = rule?.source === 'BUILTIN';

  const [name, setName] = useState(rule?.name ?? '');
  const [description, setDescription] = useState(rule?.description ?? '');
  const [appliesTo, setAppliesTo] = useState<AppliesTo>(rule?.applies_to ?? 'BOTH');
  const [logic, setLogic] = useState<'AND' | 'OR'>(rule?.logic ?? 'AND');
  const [conditions, setConditions] = useState<DraftCondition[]>(
    rule?.conditions.map(toDraft) ?? [{ field_key: '', operator: 'greater_than', value: '' }],
  );
  const [actionCode, setActionCode] = useState(rule?.action_code ?? '');
  const [priority, setPriority] = useState<Priority>(rule?.priority ?? 'MEDIUM');
  const [reason, setReason] = useState(rule?.reason ?? '');
  const [timing, setTiming] = useState(rule?.timing ?? '');
  const [dueInHours, setDueInHours] = useState(rule?.due_in_hours ? String(rule.due_in_hours) : '');
  const [cooldown, setCooldown] = useState(String(rule?.cooldown_days ?? 3));
  const [active, setActive] = useState(rule?.is_active ?? true);
  const [validation, setValidation] = useState<string | null>(null);
  const { pending, error, run } = useMutation();

  const signalKind = useMemo(() => new Map(catalog.signals.map((signal) => [signal.key, signal.kind])), [catalog]);
  const fits = (applies: NbaRecordKind[]) =>
    appliesTo === 'BOTH' ? applies.includes('OPPORTUNITY') && applies.includes('LEAD') : applies.includes(appliesTo);
  const signalOptions = catalog.signals
    .filter((signal) => builtin || fits(signal.applies_to))
    .map((signal) => ({ value: signal.key, label: signal.label }));
  const actionOptions = CATEGORY_ORDER.flatMap((category) =>
    catalog.actions
      .filter((action) => action.category === category && fits(action.applies_to))
      .map((action) => ({ value: action.code, label: `${CATEGORY_LABEL[category]} · ${action.label}` })),
  );
  const operatorOptions = catalog.operators.map((operator) => ({
    value: operator,
    label: OPERATOR_LABEL[operator] ?? operator,
  }));

  const setCondition = (index: number, patch: Partial<DraftCondition>) =>
    setConditions((previous) => previous.map((condition, i) => (i === index ? { ...condition, ...patch } : condition)));

  const save = async () => {
    const built = conditions.map((condition) => fromDraft(condition, signalKind.get(condition.field_key)));
    if (built.length === 0 || built.some((condition) => !condition.field_key)) {
      setValidation('Every condition needs a signal.');
      return;
    }
    const cooldownDays = Number(cooldown);
    if (!Number.isInteger(cooldownDays) || cooldownDays < 0 || cooldownDays > 90) {
      setValidation('Cooldown must be a whole number of days between 0 and 90.');
      return;
    }
    if (!builtin && (!name.trim() || !actionCode || !reason.trim())) {
      setValidation('A name, an action and a reason are required.');
      return;
    }
    setValidation(null);

    const saved = await run(async () => {
      if (builtin && rule) {
        return overrideBuiltinRule(rule.key, {
          is_active: active,
          priority,
          logic,
          conditions: built,
          cooldown_days: cooldownDays,
        });
      }
      const body: NbaRuleInput = {
        name: name.trim(),
        description: description.trim() || null,
        applies_to: appliesTo,
        logic,
        conditions: built,
        action_code: actionCode,
        priority,
        reason: reason.trim(),
        timing: timing.trim() || null,
        due_in_hours: dueInHours ? Number(dueInHours) : null,
        cooldown_days: cooldownDays,
        is_active: active,
      };
      return rule?.id ? updateNbaRule(rule.id, body) : createNbaRule(body);
    });
    if (saved === undefined) return;
    notifySuccess(rule ? 'Rule updated' : 'Rule created', saved.name);
    onSaved();
    onClose();
  };

  return (
    <SlideDrawer
      open
      onClose={onClose}
      title={rule ? `Edit rule: ${rule.name}` : 'New rule'}
      subtitle={
        builtin
          ? 'A built-in rule: its thresholds, priority, cooldown and on/off state can be tuned for your organisation.'
          : 'When every (or any) condition holds for an open deal or lead, the engine recommends the action.'
      }
      width="max-w-2xl"
      footer={
        <>
          <button type="button" onClick={onClose} className="ctl px-4 py-2 text-[13px] font-semibold transition hover:opacity-80">
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void save()}
            disabled={pending}
            className="inline-flex items-center gap-1.5 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            {pending && <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
            Save rule
          </button>
        </>
      }
    >
      <div className="space-y-4">
        {builtin && rule ? (
          <div className="surface bd rounded-xl border p-3 text-[12.5px]">
            <p className="txt font-semibold">{rule.name}</p>
            <p className="txt-muted mt-0.5">
              Recommends <span className="txt font-semibold">{rule.action_label}</span> · {rule.reason}
            </p>
          </div>
        ) : (
          <>
            <FormField label="Name" required>
              <FormInput value={name} maxLength={160} onChange={(event) => setName(event.target.value)} />
            </FormField>
            <FormField label="Description">
              <FormInput value={description} maxLength={500} onChange={(event) => setDescription(event.target.value)} />
            </FormField>
            <FormField label="Applies to">
              <FormSelect
                value={appliesTo}
                onChange={(event) => setAppliesTo(event.target.value as AppliesTo)}
                options={APPLIES.map((value) => ({ value, label: APPLIES_TO_LABEL[value] }))}
              />
            </FormField>
          </>
        )}

        <fieldset className="surface bd rounded-xl border p-3">
          <legend className="txt px-1 text-[12.5px] font-bold">Conditions</legend>
          <div className="mb-2 flex items-center gap-2 text-[12.5px]">
            <span className="txt-muted">Recommend when</span>
            <FilterSelect
              aria-label="Condition logic"
              value={logic}
              onChange={(event) => setLogic(event.target.value as 'AND' | 'OR')}
              options={[
                { value: 'AND', label: 'all conditions hold' },
                { value: 'OR', label: 'any condition holds' },
              ]}
            />
          </div>
          <div className="space-y-2">
            {conditions.map((condition, index) => {
              const kind = signalKind.get(condition.field_key);
              return (
                <div key={index} className="grid gap-2 sm:grid-cols-[minmax(0,5fr)_minmax(0,4fr)_minmax(0,3fr)_auto]">
                  <FormSelect
                    aria-label={`Condition ${index + 1} signal`}
                    value={condition.field_key}
                    onChange={(event) => setCondition(index, { field_key: event.target.value })}
                    options={[{ value: '', label: 'Choose a signal…' }, ...signalOptions]}
                  />
                  <FormSelect
                    aria-label={`Condition ${index + 1} operator`}
                    value={condition.operator}
                    onChange={(event) => setCondition(index, { operator: event.target.value })}
                    options={operatorOptions}
                  />
                  {VALUELESS_OPERATORS.has(condition.operator) ? (
                    <span />
                  ) : kind === 'boolean' && !LIST_OPERATORS.has(condition.operator) ? (
                    <FormSelect
                      aria-label={`Condition ${index + 1} value`}
                      value={condition.value === 'yes' ? 'true' : condition.value === 'no' ? 'false' : condition.value}
                      onChange={(event) => setCondition(index, { value: event.target.value })}
                      options={[
                        { value: '', label: 'Choose…' },
                        { value: 'true', label: 'Yes' },
                        { value: 'false', label: 'No' },
                      ]}
                    />
                  ) : (
                    <FormInput
                      aria-label={`Condition ${index + 1} value`}
                      inputMode={kind === 'number' ? 'decimal' : undefined}
                      placeholder={LIST_OPERATORS.has(condition.operator) ? 'a, b, c' : kind === 'number' ? '0' : ''}
                      value={condition.value}
                      onChange={(event) => setCondition(index, { value: event.target.value })}
                    />
                  )}
                  <button
                    type="button"
                    disabled={conditions.length === 1}
                    onClick={() => setConditions((previous) => previous.filter((_, i) => i !== index))}
                    aria-label={`Remove condition ${index + 1}`}
                    className="txt-muted grid h-9 w-9 place-items-center rounded-lg transition hover:bg-[var(--surface-2)] disabled:opacity-40"
                  >
                    <X className="h-4 w-4" aria-hidden="true" />
                  </button>
                </div>
              );
            })}
          </div>
          <button
            type="button"
            disabled={conditions.length >= 10}
            onClick={() => setConditions((previous) => [...previous, { field_key: '', operator: 'equals', value: '' }])}
            className="txt-muted mt-2 inline-flex items-center gap-1 text-[12px] font-semibold transition hover:text-[var(--text)] disabled:opacity-40"
          >
            <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add condition
          </button>
        </fieldset>

        {!builtin && (
          <>
            <FormField label="Recommended action" required>
              <FormSelect
                value={actionCode}
                onChange={(event) => setActionCode(event.target.value)}
                options={[{ value: '', label: 'Choose an action…' }, ...actionOptions]}
              />
            </FormField>
            <FormField label="Reason shown to the rep" required>
              <FormTextarea
                rows={2}
                maxLength={500}
                value={reason}
                placeholder="e.g. No reply for {days_since_last_outbound} days after the proposal."
                onChange={(event) => setReason(event.target.value)}
              />
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField label="Timing">
                <FormInput value={timing} maxLength={80} placeholder="Within 48 hours" onChange={(event) => setTiming(event.target.value)} />
              </FormField>
              <FormField label="Due in (hours)">
                <FormInput type="number" min={1} max={720} value={dueInHours} onChange={(event) => setDueInHours(event.target.value)} />
              </FormField>
            </div>
          </>
        )}

        <div className="grid gap-4 sm:grid-cols-3">
          <FormField label="Priority">
            <FormSelect
              value={priority}
              onChange={(event) => setPriority(event.target.value as Priority)}
              options={PRIORITIES.map((value) => ({ value, label: PRIORITY_LABEL[value] }))}
            />
          </FormField>
          <FormField label="Cooldown (days)">
            <FormInput type="number" min={0} max={90} value={cooldown} onChange={(event) => setCooldown(event.target.value)} />
          </FormField>
          <FormField label="Status">
            <FormSelect
              value={active ? 'on' : 'off'}
              onChange={(event) => setActive(event.target.value === 'on')}
              options={[
                { value: 'on', label: 'Active' },
                { value: 'off', label: 'Off' },
              ]}
            />
          </FormField>
        </div>
        <FormError message={validation ?? error} />
      </div>
    </SlideDrawer>
  );
}

/* ---- Rules list ------------------------------------------------------------ */

function conditionsText(rule: NbaRule, labels: ReadonlyMap<string, string>): string {
  return rule.conditions
    .map((condition) => {
      const value = conditionValueText(condition.value);
      return [labels.get(condition.field_key) ?? condition.field_key, OPERATOR_LABEL[condition.operator] ?? condition.operator, value]
        .filter(Boolean)
        .join(' ');
    })
    .join(rule.logic === 'AND' ? ' and ' : ' or ');
}

export default function NbaRulesPanel({ canAdmin }: { canAdmin: boolean }) {
  const confirm = useConfirm();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [token, setToken] = useState(0);
  const [category, setCategory] = useState<NbaCategory | ''>('');
  const [source, setSource] = useState<'' | NbaRule['source']>('');
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  const reload = useCallback(() => setToken((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [catalog, rules] = await Promise.all([getNbaCatalog(), listNbaRules()]);
        if (cancelled) return;
        setLoaded({ catalog, rules });
        setLoadError(null);
      } catch (caught) {
        if (!cancelled) setLoadError(describeApiError(caught, 'Could not load the rules.'));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const labels = useMemo(
    () => new Map((loaded?.catalog.signals ?? []).map((signal) => [signal.key, signal.label])),
    [loaded],
  );

  if (!loaded) {
    return loadError ? (
      <ListError message={loadError} onRetry={reload} />
    ) : (
      <p role="status" className="txt-muted flex items-center gap-2 p-4 text-[12.5px]">
        <Loader2 className="h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" /> Loading rules…
      </p>
    );
  }

  const rules = loaded.rules.filter(
    (rule) => (!category || rule.category === category) && (!source || rule.source === source),
  );

  const act = async (rule: NbaRule, work: () => Promise<unknown>, done: string) => {
    setBusyKey(rule.key);
    try {
      await work();
      notifySuccess(done, rule.name);
      reload();
    } catch (caught) {
      notifyError(caught, 'Could not update the rule.');
    } finally {
      setBusyKey(null);
    }
  };

  const toggle = (rule: NbaRule) =>
    act(
      rule,
      () =>
        rule.source === 'BUILTIN'
          ? overrideBuiltinRule(rule.key, { is_active: !rule.is_active })
          : updateNbaRule(rule.id as string, { is_active: !rule.is_active }),
      rule.is_active ? 'Rule switched off' : 'Rule switched on',
    );

  const remove = async (rule: NbaRule) => {
    const ok = await confirm({
      title: rule.source === 'BUILTIN' ? 'Reset this rule to its default?' : 'Delete this rule?',
      description:
        rule.source === 'BUILTIN'
          ? 'Your thresholds, priority, cooldown and on/off state for it are discarded.'
          : 'The engine stops recommending its action. Past action history is kept.',
      confirmLabel: rule.source === 'BUILTIN' ? 'Reset' : 'Delete',
      tone: rule.source === 'BUILTIN' ? 'warning' : 'danger',
    });
    if (!ok) return;
    await act(
      rule,
      () => (rule.source === 'BUILTIN' ? resetBuiltinRule(rule.key) : deleteNbaRule(rule.id as string)),
      rule.source === 'BUILTIN' ? 'Rule reset' : 'Rule deleted',
    );
  };

  const customCount = loaded.rules.filter((rule) => rule.source === 'CUSTOM').length;

  return (
    <section aria-labelledby="nba-rules-heading" className="space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <h2 id="nba-rules-heading" className="txt font-display flex items-center gap-2 text-[16px] font-bold">
            <Workflow className="h-4 w-4" style={{ color: 'var(--accent)' }} aria-hidden="true" /> Rules engine
          </h2>
          <p className="txt-muted text-[12.5px]">
            {loaded.rules.length - customCount} built-in and {customCount} custom rules turn CRM signals into
            recommended actions.
            {!canAdmin && ' Changing them needs AI Insights admin access.'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FilterSelect
            aria-label="Filter rules by category"
            value={category}
            onChange={(event) => setCategory(event.target.value as NbaCategory | '')}
            options={[
              { value: '', label: 'All categories' },
              ...CATEGORY_ORDER.map((value) => ({ value, label: CATEGORY_LABEL[value] })),
            ]}
          />
          <FilterSelect
            aria-label="Filter rules by source"
            value={source}
            onChange={(event) => setSource(event.target.value as '' | NbaRule['source'])}
            options={[
              { value: '', label: 'Built-in and custom' },
              { value: 'BUILTIN', label: 'Built-in' },
              { value: 'CUSTOM', label: 'Custom' },
            ]}
          />
          {canAdmin && (
            <button
              type="button"
              onClick={() => setEditor({ mode: 'create' })}
              className="inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-[12.5px] font-semibold text-white transition hover:opacity-90"
              style={{ background: 'var(--accent)' }}
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> New rule
            </button>
          )}
        </div>
      </div>

      {rules.length === 0 ? (
        <p className="surface bd txt-muted rounded-2xl border p-4 text-[12.5px]">No rules match these filters.</p>
      ) : (
        <ul className="space-y-2">
          {rules.map((rule) => {
            const busy = busyKey === rule.key;
            return (
              <li
                key={rule.key}
                className={cn('surface bd rounded-2xl border p-4', !rule.is_active && 'opacity-70')}
                aria-label={rule.name}
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <p className="txt font-display text-[13.5px] font-bold">{rule.name}</p>
                      <StatusBadge
                        label={rule.source === 'BUILTIN' ? (rule.is_overridden ? 'Built-in · tuned' : 'Built-in') : 'Custom'}
                        variant={rule.source === 'BUILTIN' ? 'neutral' : 'accent'}
                      />
                      {!rule.is_active && <StatusBadge label="Off" variant="neutral" />}
                    </div>
                    <p className="txt-muted mt-1 text-[12.5px]">
                      <span className="txt font-semibold">If </span>
                      {conditionsText(rule, labels)}
                    </p>
                    <p className="txt-muted mt-0.5 flex flex-wrap items-center gap-1.5 text-[12.5px]">
                      <span className="txt font-semibold">Then</span> {rule.action_label}
                      {rule.category && (
                        <StatusBadge
                          label={CATEGORY_LABEL[rule.category]}
                          variant={CATEGORY_VARIANT[rule.category]}
                        />
                      )}
                      <StatusBadge label={PRIORITY_LABEL[rule.priority]} variant={PRIORITY_VARIANT[rule.priority]} />
                    </p>
                    <p className="txt-faint mt-1 text-[11.5px]">
                      {APPLIES_TO_LABEL[rule.applies_to]}
                      {rule.timing ? ` · ${rule.timing}` : ''} · cooldown {rule.cooldown_days} day
                      {rule.cooldown_days === 1 ? '' : 's'}
                    </p>
                  </div>

                  {canAdmin && (
                    <div className="flex shrink-0 items-center gap-1.5">
                      {busy && <Loader2 className="txt-faint h-3.5 w-3.5 motion-safe:animate-spin" aria-hidden="true" />}
                      <button
                        type="button"
                        role="switch"
                        aria-checked={rule.is_active}
                        aria-label={`${rule.name} active`}
                        disabled={busy}
                        onClick={() => void toggle(rule)}
                        className={cn(
                          'relative h-5 w-9 rounded-full transition disabled:opacity-50',
                          rule.is_active ? '' : 'bg-[var(--border)]',
                        )}
                        style={rule.is_active ? { background: 'var(--accent)' } : undefined}
                      >
                        <span
                          className={cn(
                            'absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-all',
                            rule.is_active ? 'left-[18px]' : 'left-0.5',
                          )}
                        />
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => setEditor({ mode: 'edit', rule })}
                        aria-label={`Edit ${rule.name}`}
                        className="txt-muted grid h-8 w-8 place-items-center rounded-lg transition hover:bg-[var(--surface-2)]"
                      >
                        <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                      </button>
                      {(rule.source === 'CUSTOM' || rule.is_overridden) && (
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => void remove(rule)}
                          aria-label={rule.source === 'BUILTIN' ? `Reset ${rule.name}` : `Delete ${rule.name}`}
                          className="txt-muted grid h-8 w-8 place-items-center rounded-lg transition hover:bg-[var(--surface-2)]"
                        >
                          {rule.source === 'BUILTIN' ? (
                            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5 text-rose-600" aria-hidden="true" />
                          )}
                        </button>
                      )}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {editor && (
        <RuleEditor target={editor} catalog={loaded.catalog} onClose={() => setEditor(null)} onSaved={reload} />
      )}
    </section>
  );
}
