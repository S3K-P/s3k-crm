import Link from 'next/link';
import { cn } from '@/lib/utils';
import { type LucideIcon } from 'lucide-react';

/* ============================================================
   QUICK ACTION BUTTON
   Launcher-style action tile for the Quick Actions panel.
   Based on the existing launcher-tile pattern from THEME.md.
   Reusable in Dashboard, empty states, and onboarding flows.
   ============================================================ */

interface QuickActionButtonProps {
  label: string;
  icon: LucideIcon;
  href: string;
  className?: string;
}

export default function QuickActionButton({
  label,
  icon: Icon,
  href,
  className,
}: QuickActionButtonProps) {
  return (
    <Link
      href={href}
      className={cn(
        'surface bd flex items-center gap-3 rounded-xl border px-4 py-3 transition-all hover:-translate-y-0.5 hover:shadow-[0_12px_24px_-12px_rgba(30,35,90,0.2)]',
        className,
      )}
    >
      <div className="surface-2 flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px]">
        <Icon className="h-[18px] w-[18px]" style={{ color: 'var(--accent)' }} />
      </div>
      <span className="txt text-[13px] font-semibold">{label}</span>
    </Link>
  );
}
