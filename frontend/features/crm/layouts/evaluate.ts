/**
 * Conditional layout rule evaluation — mirrors
 * `backend/app/products/crm/layouts/evaluate.py` term for term.
 *
 * Exists so a form can react live, with no network round trip, while a user
 * is still typing. It is a convenience only: the backend runs the identical
 * logic again, authoritatively, on the actual create/update
 * (`CustomFieldValueService.resolve`) — this file deciding a field looks
 * required is never why a write is refused, and this file deciding a field
 * looks optional can never let a write skip a check the backend still makes.
 * See the operator semantics and precedence rules documented in the Python
 * module; they are restated here only where the two languages differ.
 */

export type RuleLogic = 'AND' | 'OR';

export interface LayoutFieldCondition {
  field_key: string;
  operator: string;
  value: unknown;
}

export interface LayoutFieldRule {
  target_field_key: string;
  logic: RuleLogic;
  conditions: LayoutFieldCondition[];
  effect_visible: boolean;
  effect_required: boolean | null;
  position: number;
}

export interface FieldState {
  visible: boolean;
  required: boolean | null;
}

function isEmpty(value: unknown): boolean {
  return value === null || value === undefined || value === '' || (Array.isArray(value) && value.length === 0);
}

function asText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  return String(value).trim().toLowerCase();
}

function asNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const n = Number(value);
  return Number.isNaN(n) ? null : n;
}

export function evaluateCondition(
  condition: LayoutFieldCondition,
  context: Record<string, unknown>,
): boolean {
  const actual = context[condition.field_key];
  const expected = condition.value;

  switch (condition.operator) {
    case 'is_empty':
      return isEmpty(actual);
    case 'is_not_empty':
      return !isEmpty(actual);
    case 'in':
    case 'not_in': {
      const options = Array.isArray(expected) ? expected : [expected];
      const member = options.map(asText).includes(asText(actual));
      return condition.operator === 'in' ? member : !member;
    }
    case 'contains':
    case 'not_contains': {
      const haystack = Array.isArray(actual) ? actual : [actual];
      const needle = asText(expected);
      const found = needle ? haystack.some((item) => asText(item).includes(needle)) : false;
      return condition.operator === 'contains' ? found : !found;
    }
    case 'greater_than':
    case 'less_than': {
      const a = asNumber(actual);
      const b = asNumber(expected);
      if (a === null || b === null) return false;
      return condition.operator === 'greater_than' ? a > b : a < b;
    }
    case 'equals':
      return asText(actual) === asText(expected);
    case 'not_equals':
      return asText(actual) !== asText(expected);
    default:
      return false;
  }
}

export function evaluateRule(rule: LayoutFieldRule, context: Record<string, unknown>): boolean {
  if (rule.conditions.length === 0) return false;
  const results = rule.conditions.map((condition) => evaluateCondition(condition, context));
  return rule.logic === 'AND' ? results.every(Boolean) : results.some(Boolean);
}

/**
 * Resolve every rule-governed field's final visible/required state.
 *
 * Precedence: base state, then matching rules in ascending `position` (later
 * wins), then "hidden implies not required" applied unconditionally last.
 * See the Python module's docstring for the full reasoning — this is the
 * same function, translated.
 */
export function effectiveFieldStates(
  rules: LayoutFieldRule[],
  context: Record<string, unknown>,
  baseVisible: Record<string, boolean> = {},
  baseRequired: Record<string, boolean> = {},
): Record<string, FieldState> {
  const targetKeys = new Set<string>([
    ...rules.map((rule) => rule.target_field_key),
    ...Object.keys(baseRequired),
    ...Object.keys(baseVisible),
  ]);

  const states: Record<string, FieldState> = {};
  for (const key of targetKeys) {
    states[key] = {
      visible: baseVisible[key] ?? true,
      required: baseRequired[key] ?? false,
    };
  }

  const ordered = [...rules].sort((a, b) => a.position - b.position);
  for (const rule of ordered) {
    if (!evaluateRule(rule, context)) continue;
    const current = states[rule.target_field_key] ?? { visible: true, required: null };
    states[rule.target_field_key] = {
      visible: rule.effect_visible,
      required: rule.effect_required !== null ? rule.effect_required : current.required,
    };
  }

  for (const key of Object.keys(states)) {
    if (!states[key].visible) {
      states[key] = { visible: false, required: false };
    }
  }

  return states;
}
