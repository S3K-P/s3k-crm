import { cn } from '@/lib/utils';

/* ============================================================
   FORM FIELD
   Reusable labelled form field wrapper with input/select/textarea.
   Uses existing ctl class for inputs.
   Reusable across all CRM form drawers and pages.
   ============================================================ */

interface FormFieldProps {
  label: string;
  htmlFor?: string;
  required?: boolean;
  hint?: string;
  error?: string;
  children: React.ReactNode;
  className?: string;
}

export default function FormField({
  label,
  htmlFor,
  required,
  hint,
  error,
  children,
  className,
}: FormFieldProps) {
  return (
    <div className={cn('space-y-1.5', className)}>
      <label
        htmlFor={htmlFor}
        className="txt text-[13px] font-semibold"
      >
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </label>
      {children}
      {hint && !error && (
        <p className="txt-faint text-[11px]">{hint}</p>
      )}
      {error && (
        <p className="text-[11px] text-red-500">{error}</p>
      )}
    </div>
  );
}

/* ============================================================
   PRE-BUILT INPUT COMPONENTS
   Convenience wrappers using ctl class for consistent styling.
   ============================================================ */

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  hasError?: boolean;
}

export function FormInput({ hasError, className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'ctl w-full px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-[var(--accent)]',
        hasError && 'border-red-500 focus:border-red-500',
        className,
      )}
      {...props}
    />
  );
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  options: { value: string; label: string }[];
  placeholder?: string;
  hasError?: boolean;
}

export function FormSelect({ options, placeholder, hasError, className, ...props }: SelectProps) {
  return (
    <select
      className={cn(
        'ctl w-full appearance-none px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-[var(--accent)]',
        hasError && 'border-red-500 focus:border-red-500',
        className,
      )}
      {...props}
    >
      {placeholder && <option value="">{placeholder}</option>}
      {options.map(opt => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  );
}

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  hasError?: boolean;
}

export function FormTextarea({ hasError, className, ...props }: TextareaProps) {
  return (
    <textarea
      className={cn(
        'ctl w-full resize-none px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-[var(--accent)]',
        hasError && 'border-red-500 focus:border-red-500',
        className,
      )}
      rows={3}
      {...props}
    />
  );
}
