import { cn } from '@/lib/utils';

/* ============================================================
   STATUS BADGE
   Reusable badge/chip for priority, status, category labels.
   Follows the existing accent-badge pattern from THEME.md.

   Both palettes are handed to CSS as custom properties and the
   `.dark` rule in globals.css picks between them. The previous
   version computed the dark palette and then dropped it,
   applying light colours in both themes — which put #ecfdf5 on
   a dark surface for every success, warning and danger badge.

   Inline styles cannot carry a media query or a class selector,
   but a custom property set inline *is* visible to a stylesheet
   rule, so the choice moves to CSS where the theme is known.
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

/** The four custom properties `.status-badge` reads, for one variant. */
export function badgeThemeVars(variant: BadgeVariant): React.CSSProperties {
  const light = variantStyles[variant];
  const dark = darkVariantStyles[variant];
  return {
    '--badge-bg': light.bg,
    '--badge-fg': light.color,
    '--badge-bg-dark': dark.bg,
    '--badge-fg-dark': dark.color,
  } as React.CSSProperties;
}

export default function StatusBadge({ label, variant = 'accent', className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        'status-badge inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold leading-tight',
        className,
      )}
      style={badgeThemeVars(variant)}
    >
      {label}
    </span>
  );
}

/** Helper to get inline style for a badge variant (for use in custom components) */
export function getBadgeStyle(variant: BadgeVariant) {
  return variantStyles[variant];
}
