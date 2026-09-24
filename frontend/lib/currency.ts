/**
 * The CRM's display currency — the one place it is decided.
 *
 * Every monetary figure in the product renders through these helpers, in
 * Indian Rupees with Indian digit grouping (1,26,45,000) and Indian compact
 * units (₹1.26Cr, ₹4.5L).
 *
 * This is display only. Stored amounts are never converted: a deal saved as
 * 50000 renders as ₹50,000, whatever currency code the record carries.
 */

export const CRM_CURRENCY = 'INR';
export const CRM_CURRENCY_LOCALE = 'en-IN';
export const CRM_CURRENCY_SYMBOL = '₹';

type Amount = number | string | null | undefined;

function toAmount(value: Amount): number | null {
  if (value === null || value === undefined || value === '') return null;
  const amount = Number(value);
  return Number.isFinite(amount) ? amount : null;
}

/** ₹12,50,000 — full figure, no decimals unless asked for. */
export function formatCurrency(value: Amount, fractionDigits = 0): string {
  const amount = toAmount(value);
  if (amount === null) return '—';
  return new Intl.NumberFormat(CRM_CURRENCY_LOCALE, {
    style: 'currency',
    currency: CRM_CURRENCY,
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(amount);
}

/** ₹1.26Cr / ₹4.5L / ₹85K — for KPI tiles, headline figures and chart axes. */
export function formatCompactCurrency(value: Amount): string {
  const amount = toAmount(value);
  if (amount === null) return '—';
  return new Intl.NumberFormat(CRM_CURRENCY_LOCALE, {
    style: 'currency',
    currency: CRM_CURRENCY,
    notation: 'compact',
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  }).format(amount);
}
