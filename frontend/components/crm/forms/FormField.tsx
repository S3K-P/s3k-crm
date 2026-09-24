'use client';

import { createContext, useContext, useId } from 'react';

import PasswordInput from '@/components/auth/PasswordInput';
import { cn } from '@/lib/utils';

/* ============================================================
   FORM FIELD
   Reusable labelled form field wrapper with input/select/textarea.
   Uses existing ctl class for inputs.
   Reusable across all CRM form drawers and pages.

   **The label wraps its control**, rather than sitting beside it
   with an optional `htmlFor` nobody passed. As siblings the two
   were never associated, so every input in all eighteen forms
   using this component had no accessible name: a screen reader
   read "edit text", and clicking the word "Email" did not focus
   the field. An end-to-end test looking for a field by its label
   is what surfaced it.

   Wrapping gives implicit association, which needs no id and so
   cannot be forgotten at a call site. `htmlFor` is still honoured
   for the case where a control has to live outside the label.

   The one cost of wrapping: a label's accessible name is built
   from *all* of its content, so a second control inside it (the
   show/hide button in FormPasswordInput) leaks its own name into
   the field's — "Current password Show password". The label text
   therefore carries an id, published through context, which such
   an input can name itself by with aria-labelledby.
   ============================================================ */

const FormFieldLabelContext = createContext<string | undefined>(undefined);

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
  const labelId = useId();
  return (
    <div className={cn('space-y-1.5', className)}>
      <label htmlFor={htmlFor} className="block space-y-1.5">
        <span id={labelId} className="txt block text-[13px] font-semibold">
          {label}
          {required && <span className="ml-0.5 text-red-500">*</span>}
        </span>
        <FormFieldLabelContext.Provider value={labelId}>{children}</FormFieldLabelContext.Provider>
      </label>
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

/** FormInput for secrets: same styling, plus a show/hide toggle. */
export function FormPasswordInput({ hasError, className, ...props }: Omit<InputProps, 'type'>) {
  const labelId = useContext(FormFieldLabelContext);
  return (
    <span className="relative block">
      <PasswordInput
        aria-labelledby={labelId}
        className={cn(
          'ctl w-full px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-[var(--accent)]',
          hasError && 'border-red-500 focus:border-red-500',
          className,
        )}
        {...props}
      />
    </span>
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
