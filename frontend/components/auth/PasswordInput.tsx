'use client';

import { useState } from 'react';
import { Eye, EyeOff } from 'lucide-react';

import { cn } from '@/lib/utils';

/* ============================================================
   PASSWORD INPUT
   A password field with an eye / eye-off toggle inside its right
   edge. The toggle only flips `type` between "password" and
   "text": the value is controlled by the caller and is never
   touched, so revealing or hiding it cannot clear what was typed.

   Every other prop passes straight through to the <input>, so
   callers keep their own id, name, autoComplete, validation and
   styling. `pr-10` is merged into the class list to keep text
   from running under the toggle.

   It renders the input and toggle as siblings, not inside a wrapper
   of its own: the caller supplies the `relative` container. The
   auth pages already have one holding a leading icon, and a second
   positioned box around the input would paint over that icon.
   ============================================================ */

type PasswordInputProps = Omit<React.InputHTMLAttributes<HTMLInputElement>, 'type'>;

export default function PasswordInput({ className, disabled, ...props }: PasswordInputProps) {
  const [visible, setVisible] = useState(false);
  const label = visible ? 'Hide password' : 'Show password';
  const Icon = visible ? EyeOff : Eye;

  return (
    <>
      <input
        {...props}
        type={visible ? 'text' : 'password'}
        disabled={disabled}
        className={cn(className, 'pr-10')}
      />
      <button
        type="button"
        onClick={() => setVisible((current) => !current)}
        disabled={disabled}
        aria-label={label}
        aria-controls={props.id}
        title={label}
        className="txt-faint hover:txt absolute right-2 top-1/2 flex h-7 w-7 -translate-y-1/2 items-center justify-center rounded-md transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent)] disabled:pointer-events-none disabled:opacity-60"
      >
        <Icon className="h-4 w-4" aria-hidden="true" />
      </button>
    </>
  );
}
