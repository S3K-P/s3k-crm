/* ============================================================
   CURRENCY

   One place says what money is in this application. Screens
   format through these constants rather than repeating an ISO
   code and a locale, so the next currency change is one edit
   instead of a search across the app — which is how `USD` came
   to be written out in eight separate files.

   `MONEY_LOCALE` is pinned rather than left to the reader's
   browser because grouping is part of how a figure reads:
   ₹12,50,000 and ₹1,250,000 are the same number, and only one
   of them is legible to the people using this CRM.

   `DEFAULT_CURRENCY` is a fallback, not a rule. An opportunity
   carries its own ISO code and is always formatted with it —
   the default applies to a figure that has none of its own,
   and to the value a new record starts with.
   ============================================================ */

export const MONEY_LOCALE = 'en-IN';

export const DEFAULT_CURRENCY = 'INR';
