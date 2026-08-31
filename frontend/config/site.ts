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

   What stays here is the brand — and since the CRM became one app
   on a platform, that is now **two** identities rather than one.

   Which to use is decided by the layer you are in, not by taste:

     `PLATFORM_BRAND`  the shell above the apps — sign-in, the
                       signup wizard, the workspace, the app
                       catalogue. A person here has not chosen an
                       app yet, so naming the page after one of
                       them is wrong.
     `BRAND`           the S3K CRM application itself: its sidebar,
                       its pages, and the marketing site that sells
                       it.

   They deliberately share `mark` and `footer`: the company is the
   same, only the product in front of you changes.
   ============================================================ */

/** The platform shell — everything above and between the apps. */
export const PLATFORM_BRAND = {
  /** Short mark shown in the square logo tile (2–3 chars looks best) */
  mark: 'S3K',
  /** Platform name next to the logo */
  name: 'S3K Platforms',
  /** Tiny uppercase tagline under the platform name */
  tagline: 'One account · every S3K app',
  /** Where clicking the logo goes */
  homeHref: '/workspace',
  /** Footer line */
  footer: 'S3K Technologies · All Rights Reserved',
};

/** The S3K CRM application. */
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
