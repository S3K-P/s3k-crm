import {
  BarChart3,
  BookUser,
  CalendarDays,
  Clock,
  ClipboardList,
  Filter,
  Target,
  UserPlus,
  Zap,
  type LucideIcon,
} from 'lucide-react';

import type { HomeCardType } from '@/features/crm/dashboard';

/* ============================================================
   CARD CATALOG
   Title and icon for every home-dashboard card type, shared by
   the "Add Card" picker and anywhere else that needs to label a
   card without rendering it (e.g. a hidden card in customize
   mode). Each card component still owns its own on-screen title
   — this is metadata, not a render registry, since the cards
   differ too much in their data needs to share one.
   ============================================================ */

export const CARD_CATALOG: Record<HomeCardType, { title: string; icon: LucideIcon }> = {
  MY_LEADS: { title: 'My Leads', icon: UserPlus },
  MY_DEALS: { title: 'My Open Deals', icon: Target },
  MY_CONTACTS: { title: 'My Contacts', icon: BookUser },
  PIPELINE_BY_STAGE: { title: 'Pipeline by Stage', icon: Filter },
  TASKS_FOLLOW_UPS: { title: 'Tasks & Follow-ups', icon: ClipboardList },
  RECENT_RECORDS: { title: 'Recent Records', icon: BarChart3 },
  ACTIVITY_TIMELINE: { title: 'Activity Timeline', icon: Clock },
  UPCOMING_MEETINGS: { title: 'Upcoming Meetings', icon: CalendarDays },
  QUICK_ACTIONS: { title: 'Quick Actions', icon: Zap },
};
