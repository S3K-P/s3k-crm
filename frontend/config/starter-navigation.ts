import {
  Sparkles, Wand2, Settings, LayoutDashboard, ClipboardList,
  Boxes, Cpu, type LucideIcon,
} from 'lucide-react';

/* ============================================================
   STARTER NAVIGATION — the `(app)` route group only.

   These are the UI-starter kit's own pages: the component
   gallery, the sample form, the starter settings screen. They
   are reached through `components/Header.tsx` and nothing else.

   **This file has no authority over the CRM.** Navigation for
   the `(crm)` group lives in `crm-navigation.ts` and is rendered
   by the CRM sidebar; the ⌘K palette in that group searches real
   records through `/crm/search`. Editing anything here changes
   the starter pages and nothing a customer sees.

   Split out of `config/site.ts` by `P3-W20-FE-02`, which existed
   because one file exporting both `TABS`/`SUBNAV`/`SEARCH_ITEMS`
   and the shared brand read like the app's navigation config —
   so a change meant for the CRM landed somewhere with no effect
   on it, and the two lists drifted apart unnoticed. `site.ts`
   now holds the brand alone, which genuinely is shared.
   ============================================================ */

export type TabId = 'home' | 'tools' | 'settings';

export interface Tab {
  id: TabId;
  label: string;
  icon: LucideIcon;
  /** Route prefixes that make this tab active */
  match: string[];
}

export const TABS: Tab[] = [
  { id: 'home',     label: 'Home',     icon: Sparkles, match: ['/dashboard'] },
  { id: 'tools',    label: 'Tools',    icon: Wand2,    match: ['/tools'] },
  { id: 'settings', label: 'Settings', icon: Settings, match: ['/settings'] },
];

export interface SubItem { label: string; href: string }

/** Second-row navigation per tab. A tab with one item shows no sub-nav bar. */
export const SUBNAV: Record<TabId, SubItem[]> = {
  home: [
    { label: 'Dashboard', href: '/dashboard' },
  ],
  tools: [
    { label: 'Sample Tool', href: '/tools/sample-form' },
    { label: 'Components',  href: '/tools/components' },
  ],
  settings: [
    { label: 'Settings', href: '/settings' },
  ],
};

export interface SearchItem { label: string; href: string; icon: LucideIcon; group: string }

/**
 * Entries for the starter header's ⌘K modal. Keep in sync with SUBNAV.
 *
 * This is a list of *page names*, which is all the starter kit has to offer.
 * The CRM's palette does not use it — see `components/crm/topbar/CommandPalette.tsx`.
 */
export const SEARCH_ITEMS: SearchItem[] = [
  { label: 'Dashboard',   href: '/dashboard',         icon: LayoutDashboard, group: 'Home' },
  { label: 'Sample Tool', href: '/tools/sample-form', icon: ClipboardList,   group: 'Tools' },
  { label: 'Components',  href: '/tools/components',  icon: Boxes,           group: 'Tools' },
  { label: 'Settings',    href: '/settings',          icon: Cpu,             group: 'Settings' },
];
