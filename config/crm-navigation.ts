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
  type LucideIcon,
} from 'lucide-react';

/* ============================================================
   CRM NAVIGATION CONFIG
   Single source of truth for sidebar items, grouping,
   and breadcrumb label resolution.
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
      { id: 'dashboard', label: 'Dashboard', href: '/dashboard', icon: LayoutDashboard },
    ],
  },
  {
    title: 'Pipeline',
    items: [
      { id: 'lead-sources', label: 'Lead Sources', href: '/lead-sources', icon: Globe },
      { id: 'leads', label: 'Leads', href: '/leads', icon: Users },
      { id: 'campaigns', label: 'Campaigns', href: '/campaigns', icon: Megaphone },
      { id: 'meetings', label: 'Meetings', href: '/meetings', icon: CalendarDays },
    ],
  },
  {
    title: 'Relationships',
    items: [
      { id: 'accounts', label: 'Accounts', href: '/accounts', icon: Building2 },
      { id: 'contacts', label: 'Contacts', href: '/contacts', icon: Contact },
      { id: 'opportunities', label: 'Opportunities', href: '/opportunities', icon: Target },
      { id: 'qualification', label: 'Qualification', href: '/qualification', icon: CheckCircle2 },
    ],
  },
  {
    title: 'System',
    items: [
      { id: 'admin', label: 'Admin', href: '/admin', icon: ShieldCheck },
      { id: 'ai-settings', label: 'AI Settings', href: '/ai-settings', icon: Sparkles },
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
  admin: 'Admin',
  'ai-settings': 'AI Settings',
};
