import {
  Sparkles, Wand2, Settings, LayoutDashboard, ClipboardList,
  Boxes, Cpu, LucideIcon,
} from 'lucide-react';

/* ============================================================
   SITE CONFIG — the ONE file to edit for a new project.
   Brand, navigation tabs, sub-nav and ⌘K search all live here.
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

/** Entries for the ⌘K quick-search modal. Keep in sync with SUBNAV. */
export const SEARCH_ITEMS: SearchItem[] = [
  { label: 'Dashboard',   href: '/dashboard',         icon: LayoutDashboard, group: 'Home' },
  { label: 'Sample Tool', href: '/tools/sample-form', icon: ClipboardList,   group: 'Tools' },
  { label: 'Components',  href: '/tools/components',  icon: Boxes,           group: 'Tools' },
  { label: 'Settings',    href: '/settings',          icon: Cpu,             group: 'Settings' },
];
