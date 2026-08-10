'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

/* ============================================================
   COPY BUTTON
   Copy-to-clipboard action for generated AI content.
   Icon-only by default, with an accessible label and the same
   native-title tooltip convention used by the CRM sidebar.
   ============================================================ */

interface CopyButtonProps {
  /** Text placed on the clipboard. */
  value: string;
  /** What was copied, e.g. "Email draft" — used in the label and toast. */
  label: string;
  /** Render the label next to the icon instead of icon-only. */
  showLabel?: boolean;
  className?: string;
}

export default function CopyButton({ value, label, showLabel = false, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const timeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => {
    if (timeout.current) clearTimeout(timeout.current);
  }, []);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      toast.success(`${label} copied to clipboard`);
      if (timeout.current) clearTimeout(timeout.current);
      timeout.current = setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Could not copy — your browser blocked clipboard access');
    }
  }, [value, label]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      title={`Copy ${label.toLowerCase()}`}
      aria-label={`Copy ${label.toLowerCase()}`}
      className={cn(
        'ctl txt-muted inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[12px] font-semibold transition hover:opacity-80',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]',
        className,
      )}
    >
      {copied
        ? <Check className="h-3.5 w-3.5 text-emerald-500" aria-hidden="true" />
        : <Copy className="h-3.5 w-3.5" aria-hidden="true" />}
      {showLabel && <span>{copied ? 'Copied' : 'Copy'}</span>}
    </button>
  );
}
