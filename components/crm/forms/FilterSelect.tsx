import { cn } from '@/lib/utils';

/* ============================================================
   FILTER SELECT
   Compact filter dropdown using ctl token class.
   Reusable across all CRM list/table pages.
   ============================================================ */

interface FilterSelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: { value: string; label: string }[];
}

export default function FilterSelect({ options, className, ...props }: FilterSelectProps) {
  return (
    <select
      className={cn(
        'ctl appearance-none px-3.5 py-2 text-[13px] font-medium outline-none transition-colors focus:border-[var(--accent)]',
        className,
      )}
      {...props}
    >
      {options.map(opt => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  );
}
