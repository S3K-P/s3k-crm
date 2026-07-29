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
  /** Gradient classes for the icon */
  gradient?: string;
  className?: string;
}

export default function QuickActionButton({
  label,
  icon: Icon,
  href,
  gradient = 'from-violet-600 to-indigo-600',
  className,
}: QuickActionButtonProps) {
  return (
    <Link
      href={href}
      className={cn(
        'surface bd flex items-center gap-3 rounded-xl border px-4 py-3 transition-all hover:-translate-y-0.5 hover:shadow-[0_12px_24px_-12px_rgba(50,30,90,0.2)]',
        className,
      )}
    >
      <div className={cn(
        'flex h-9 w-9 shrink-0 items-center justify-center rounded-[10px] bg-gradient-to-br',
        gradient,
      )}>
        <Icon className="h-[18px] w-[18px] text-white" />
      </div>
      <span className="txt text-[13px] font-semibold">{label}</span>
    </Link>
  );
}
