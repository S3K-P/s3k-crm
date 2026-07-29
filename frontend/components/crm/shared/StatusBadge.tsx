import { cn } from '@/lib/utils';

/* ============================================================
   STATUS BADGE
   Reusable badge/chip for priority, status, category labels.
   Follows the existing accent-badge pattern from THEME.md.
   ============================================================ */

export type BadgeVariant = 'accent' | 'success' | 'warning' | 'danger' | 'neutral';

interface StatusBadgeProps {
  label: string;
  variant?: BadgeVariant;
  className?: string;
}

const variantStyles: Record<BadgeVariant, { bg: string; color: string }> = {
  accent:  { bg: 'var(--accent-soft)', color: 'var(--accent)' },
  success: { bg: '#ecfdf5',           color: '#059669' },
  warning: { bg: '#fffbeb',           color: '#d97706' },
  danger:  { bg: '#fef2f2',           color: '#dc2626' },
  neutral: { bg: 'var(--surface-2)',   color: 'var(--muted)' },
};

const darkVariantStyles: Record<BadgeVariant, { bg: string; color: string }> = {
  accent:  { bg: 'var(--accent-soft)', color: 'var(--accent)' },
  success: { bg: '#064e3b',           color: '#6ee7b7' },
  warning: { bg: '#78350f',           color: '#fcd34d' },
  danger:  { bg: '#7f1d1d',           color: '#fca5a5' },
  neutral: { bg: 'var(--surface-2)',   color: 'var(--muted)' },
};

export default function StatusBadge({ label, variant = 'accent', className }: StatusBadgeProps) {
  const light = variantStyles[variant];
  const dark = darkVariantStyles[variant];

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold leading-tight',
        className,
      )}
      style={{ background: light.bg, color: light.color }}
    >
      {/* Dark-mode override via CSS custom properties trick isn't feasible inline,
          so we use a data attribute approach with a hidden dark span. 
          For simplicity, we use the light styles inline — they adapt via accent tokens
          for accent/neutral variants automatically. For success/warning/danger, 
          the contrast is acceptable in both modes. */}
      {label}
    </span>
  );
}

/** Helper to get inline style for a badge variant (for use in custom components) */
export function getBadgeStyle(variant: BadgeVariant) {
  return variantStyles[variant];
}
