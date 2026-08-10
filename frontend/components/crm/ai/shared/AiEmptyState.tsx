import { type LucideIcon } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ============================================================
   AI EMPTY STATE
   Compact, explanatory empty state used across the AI module —
   full-page (no results yet) and inline (no meetings logged).
   ============================================================ */

interface AiEmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: string;
  /** Optional call to action rendered beneath the description. */
  action?: React.ReactNode;
  size?: 'inline' | 'block';
  className?: string;
}

export default function AiEmptyState({
  icon: Icon,
  title,
  description,
  action,
  size = 'block',
  className,
}: AiEmptyStateProps) {
  const inline = size === 'inline';

  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        inline ? 'gap-1.5 py-7' : 'gap-2.5 py-14',
        className,
      )}
    >
      <div
        className={cn(
          'surface-2 bd grid place-items-center rounded-full border',
          inline ? 'h-9 w-9' : 'h-12 w-12',
        )}
      >
        <Icon
          className={cn('txt-faint', inline ? 'h-4 w-4' : 'h-5 w-5')}
          aria-hidden="true"
        />
      </div>
      <p className={cn('txt font-semibold', inline ? 'text-[13px]' : 'text-[14.5px]')}>{title}</p>
      <p className={cn('txt-muted max-w-md', inline ? 'text-[12px]' : 'text-[13px]')}>{description}</p>
      {action && <div className="mt-1.5">{action}</div>}
    </div>
  );
}
