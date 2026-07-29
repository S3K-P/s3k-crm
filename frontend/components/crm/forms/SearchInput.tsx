import { cn } from '@/lib/utils';
import { Search } from 'lucide-react';

/* ============================================================
   SEARCH INPUT
   Inline search input with icon, using ctl token class.
   Reusable across all CRM list/table pages.
   ============================================================ */

interface SearchInputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'> {
  containerClassName?: string;
}

export default function SearchInput({ containerClassName, className, ...props }: SearchInputProps) {
  return (
    <div className={cn('relative', containerClassName)}>
      <Search className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2" />
      <input
        type="text"
        className={cn(
          'ctl w-full py-2 pl-9 pr-3.5 text-[13px] outline-none transition-colors focus:border-[var(--accent)]',
          className,
        )}
        {...props}
      />
    </div>
  );
}
