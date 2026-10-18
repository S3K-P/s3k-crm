import { cn } from '@/lib/utils';

/* ============================================================
   DASHBOARD AVATAR
   Small initials circle for list rows (leads, contacts, recent
   records). Same gradient treatment as the topbar account menu,
   so a person's initials look the same wherever they appear.
   ============================================================ */

function initialsFrom(label: string): string {
  const parts = label.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
  return `${parts[0]![0]}${parts[parts.length - 1]![0]}`.toUpperCase();
}

interface DashboardAvatarProps {
  /** Full display name/label the initials are drawn from. */
  label: string;
  /** `'person'` (default): accent gradient circle. `'tile'`: neutral square, for non-person records. */
  variant?: 'person' | 'tile';
  className?: string;
}

export default function DashboardAvatar({ label, variant = 'person', className }: DashboardAvatarProps) {
  if (variant === 'tile') {
    return (
      <span
        className={cn('grid h-7 w-7 shrink-0 place-items-center rounded-lg text-[11px] font-bold', className)}
        style={{ background: 'var(--surface-2)', color: 'var(--accent)' }}
      >
        {initialsFrom(label)}
      </span>
    );
  }

  return (
    <span
      className={cn(
        'grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-[11px] font-bold text-white',
        className,
      )}
    >
      {initialsFrom(label)}
    </span>
  );
}
