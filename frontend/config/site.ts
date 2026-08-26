/* ============================================================
   SITE CONFIG — brand identity, shared by every route group.

   Navigation deliberately does **not** live here any more.

   It used to, and that was the "dual navigation config" that
   `P3-W20-FE-02` retired: this file described tabs, sub-nav and a
   ⌘K list for the UI-starter pages, while `crm-navigation.ts`
   described the CRM's own sidebar. Both read like *the* site
   navigation, so an edit intended for the CRM could land here and
   change nothing anyone uses.

   Where navigation lives now:

     `crm-navigation.ts`        authoritative for the `(crm)` group
     `starter-navigation.ts`    the `(app)` starter pages only

   What stays here is the brand, which is genuinely shared — the
   login screen, the landing pages, the CRM sidebar and the footer
   all read it.
   ============================================================ */

export const BRAND = {
  /** Short mark shown in the square logo tile (2–3 chars looks best) */
  mark: 'S3K',
  /** Product name next to the logo */
  name: 'S3K CRM',
  /** Tiny uppercase tagline under the product name */
  tagline: 'AI-First Enterprise CRM',
  /** Where clicking the logo goes */
  homeHref: '/dashboard',
  /** Footer line */
  footer: 'S3K Technologies · All Rights Reserved',
};
