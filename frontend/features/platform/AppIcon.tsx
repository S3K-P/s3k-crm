'use client';

import {
  Boxes,
  KanbanSquare,
  Megaphone,
  TrendingUp,
  UserCog,
  Users,
  Wallet,
  type LucideIcon,
} from 'lucide-react';

/* ============================================================
   APP ICON

   The catalogue stores an icon *name*, so adding an app is a
   data change rather than a deploy. Names are resolved against
   this explicit allow-list and never used to build a dynamic
   import: the value arrives from the API, and a lookup table is
   the difference between "unknown name renders a fallback" and
   "server-supplied string reaches the module loader".

   An unrecognised name falls back to a neutral glyph rather
   than rendering nothing, so a catalogue entry added ahead of
   the frontend still draws a complete card.
   ============================================================ */

const ICONS: Record<string, LucideIcon> = {
  Boxes,
  KanbanSquare,
  Megaphone,
  TrendingUp,
  UserCog,
  Users,
  Wallet,
};

export function AppIcon({
  name,
  className,
}: {
  name: string;
  className?: string;
}) {
  const Icon = ICONS[name] ?? Boxes;
  return <Icon className={className} aria-hidden="true" />;
}

export default AppIcon;
