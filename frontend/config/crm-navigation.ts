import {
  LayoutDashboard,
  Megaphone,
  Users,
  Building2,
  Contact,
  Target,
  CheckCircle2,
  CalendarDays,
  Globe,
  ShieldCheck,
  Sparkles,
  ClipboardList,
  BrainCircuit,
  Zap,
  type LucideIcon,
} from 'lucide-react';

/* ============================================================
   CRM NAVIGATION CONFIG

   **Authoritative for the `(crm)` route group** — sidebar items,
   their grouping, and breadcrumb label resolution.

   Since `P3-W20-FE-02` this is the only file describing CRM
   navigation. `config/site.ts` holds the shared brand and nothing
   else; the UI-starter kit's tabs live in `starter-navigation.ts`
   and reach only the `(app)` group.

   `CRM_NAV_ITEMS` also backs the "Go to" section of the ⌘K
   palette. The palette's *record* results come from
   `/crm/search`, not from this file — pages are navigation, and
   records are data.
   ============================================================ */

export interface CrmNavItem {
  /** Unique key */
  id: string;
  /** Display label */
  label: string;
  /** Route href */
  href: string;
  /** Lucide icon component */
  icon: LucideIcon;
  /**
   * Backend permission module gating this item, e.g. `leads`.
   *
   * Hiding an entry is a **UX** decision only — the API re-checks the same
   * permission on every request, so navigating to a hidden route by typing its
   * URL still yields 403s rather than data. Items with no module are visible
   * to any authenticated member.
   */
  permissionModule?: string;
}

export interface CrmNavSection {
  /** Section heading shown in expanded sidebar */
  title: string;
  items: CrmNavItem[];
}

/** Sidebar navigation grouped by section */
export const CRM_NAV_SECTIONS: CrmNavSection[] = [
  {
    title: 'Overview',
    items: [
      { id: 'dashboard', label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard, permissionModule: 'dashboard' },
    ],
  },
  {
    title: 'Pipeline',
    items: [
      { id: 'lead-sources', label: 'Lead Sources', href: '/lead-sources', icon: Globe, permissionModule: 'lead_sources' },
      { id: 'leads', label: 'Leads', href: '/leads', icon: Users, permissionModule: 'leads' },
      { id: 'campaigns', label: 'Campaigns', href: '/campaigns', icon: Megaphone, permissionModule: 'campaigns' },
      { id: 'meetings', label: 'Meetings', href: '/meetings', icon: CalendarDays, permissionModule: 'activities' },
    ],
  },
  {
    title: 'Relationships',
    items: [
      { id: 'accounts', label: 'Accounts', href: '/accounts', icon: Building2, permissionModule: 'accounts' },
      { id: 'contacts', label: 'Contacts', href: '/contacts', icon: Contact, permissionModule: 'contacts' },
      { id: 'opportunities', label: 'Opportunities', href: '/opportunities', icon: Target, permissionModule: 'opportunities' },
      { id: 'tasks', label: 'Tasks', href: '/tasks', icon: ClipboardList, permissionModule: 'tasks' },
      { id: 'qualification', label: 'Qualification', href: '/qualification', icon: CheckCircle2, permissionModule: 'leads' },
    ],
  },
  {
    title: 'AI',
    items: [
      { id: 'ai-insights', label: 'AI Insights', href: '/ai/insights', icon: BrainCircuit, permissionModule: 'dashboard' },
      { id: 'ai-next-best-action', label: 'Next Best Action', href: '/ai/next-best-action', icon: Zap, permissionModule: 'opportunities' },
    ],
  },
  {
    title: 'System',
    items: [
      { id: 'admin', label: 'Admin', href: '/admin', icon: ShieldCheck, permissionModule: 'users' },
      { id: 'ai-settings', label: 'AI Settings', href: '/ai-settings', icon: Sparkles, permissionModule: 'users' },
    ],
  },
];

/** Flat list of all nav items (derived) */
export const CRM_NAV_ITEMS: CrmNavItem[] = CRM_NAV_SECTIONS.flatMap(s => s.items);

/**
 * Map a URL segment to a human-readable breadcrumb label.
 * Covers every CRM route segment plus common future sub-routes.
 */
export const BREADCRUMB_LABELS: Record<string, string> = {
  dashboard: 'Dashboard',
  'lead-sources': 'Lead Sources',
  leads: 'Leads',
  campaigns: 'Campaigns',
  meetings: 'Meetings',
  accounts: 'Accounts',
  contacts: 'Contacts',
  opportunities: 'Opportunities',
  qualification: 'Qualification',
  tasks: 'Tasks',
  admin: 'Admin',
  'ai-settings': 'AI Settings',
  ai: 'AI',
  insights: 'AI Insights',
  'next-best-action': 'Next Best Action',
};
