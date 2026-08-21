'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react';
import { AlertTriangle, Info, ShieldAlert } from 'lucide-react';

import FormField, { FormInput, FormTextarea } from '@/components/crm/forms/FormField';
import { cn } from '@/lib/utils';

/* ============================================================
   CONFIRM DIALOG

   The CRM's single "are you sure?" surface, built from the same
   tokens as SlideDrawer (`surface`, `bd`, `ctl`, `txt`) so it
   belongs to the existing design system rather than introducing
   a second dialog language.

   It replaces two things that were wrong before:

   - destructive row actions (archive a lead, a deal, an
     account) that fired on a single click with no confirmation
     and no feedback;
   - `window.prompt('Why was this deal lost?')`, a browser
     dialog that ignores the theme, cannot be styled, and is
     blocked outright in some embedded browsers.

   Usage is promise-based so a call site reads top to bottom:

       const ok = await confirm({ title: '…', tone: 'danger' });
       if (!ok) return;

   When `prompt` is supplied the resolved object carries the
   entered text in `value`, which is how a loss reason or a
   disqualification reason is collected without a second screen.
   ============================================================ */

export type ConfirmTone = 'danger' | 'warning' | 'accent';

export interface ConfirmPromptSpec {
  label: string;
  placeholder?: string;
  hint?: string;
  /** Confirm stays disabled until the field is non-empty. */
  required?: boolean;
  /** Defaults to a textarea; set false for a single-line input. */
  multiline?: boolean;
  defaultValue?: string;
}

export interface ConfirmOptions {
  title: string;
  description?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  tone?: ConfirmTone;
  /** Collect a short reason as part of confirming. */
  prompt?: ConfirmPromptSpec;
  /**
   * Guard for the most consequential actions: confirm stays disabled until
   * the user types this exact string.
   */
  requireTyping?: string;
}

export interface ConfirmResult {
  /** Text entered in `prompt`, or `''` when the dialog had no prompt. */
  value: string;
}

/** Resolves to `null` when the user cancels, dismisses or presses Escape. */
export type ConfirmFn = (options: ConfirmOptions) => Promise<ConfirmResult | null>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

export function useConfirm(): ConfirmFn {
  const confirm = useContext(ConfirmContext);
  if (confirm === null) {
    throw new Error('useConfirm must be used inside <ConfirmProvider>.');
  }
  return confirm;
}

const TONE_STYLES: Record<
  ConfirmTone,
  { icon: typeof AlertTriangle; iconClass: string; button: string }
> = {
  danger: {
    icon: AlertTriangle,
    iconClass: 'bg-gradient-to-br from-rose-500 to-red-600',
    button: 'bg-red-500 hover:bg-red-600',
  },
  warning: {
    icon: ShieldAlert,
    iconClass: 'bg-gradient-to-br from-amber-500 to-orange-500',
    button: 'bg-amber-500 hover:bg-amber-600',
  },
  accent: {
    icon: Info,
    iconClass: 'bg-gradient-to-br from-violet-500 to-indigo-600',
    button: '',
  },
};

interface PendingRequest {
  options: ConfirmOptions;
  resolve: (result: ConfirmResult | null) => void;
}

export function ConfirmProvider({ children }: { children: React.ReactNode }) {
  const [request, setRequest] = useState<PendingRequest | null>(null);
  const [value, setValue] = useState('');
  const [typed, setTyped] = useState('');
  const [settling, setSettling] = useState(false);

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);
  /** The element to hand focus back to when the dialog closes. */
  const restoreFocusRef = useRef<HTMLElement | null>(null);

  const confirm = useCallback<ConfirmFn>(
    (options) =>
      new Promise<ConfirmResult | null>((resolve) => {
        restoreFocusRef.current =
          document.activeElement instanceof HTMLElement ? document.activeElement : null;
        setValue(options.prompt?.defaultValue ?? '');
        setTyped('');
        setSettling(false);
        setRequest({ options, resolve });
      }),
    [],
  );

  /* One place that ends the interaction, so the promise settles exactly once
     and focus always goes back where it came from. */
  const settle = useCallback((result: ConfirmResult | null) => {
    setRequest((current) => {
      current?.resolve(result);
      return null;
    });
    restoreFocusRef.current?.focus?.();
    restoreFocusRef.current = null;
  }, []);

  const options = request?.options ?? null;
  const promptSpec = options?.prompt ?? null;

  const blocked =
    (promptSpec?.required === true && value.trim().length === 0) ||
    (options?.requireTyping !== undefined && typed.trim() !== options.requireTyping);

  const onConfirm = useCallback(() => {
    // A double click must not resolve twice, and so must not fire the
    // caller's mutation twice either.
    if (blocked || settling) return;
    setSettling(true);
    settle({ value: value.trim() });
  }, [blocked, settling, settle, value]);

  /* ---- Escape cancels; Tab stays inside the dialog ---- */
  useEffect(() => {
    if (request === null) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        settle(null);
        return;
      }
      if (event.key === 'Tab' && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), input, textarea, [href], select',
        );
        if (focusable.length === 0) return;
        const first = focusable[0]!;
        const last = focusable[focusable.length - 1]!;
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };

    document.addEventListener('keydown', onKeyDown);
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [request, settle]);

  /* Land focus on the confirm button when the dialog has no field to fill in.
     With a field, its own `autoFocus` wins — never leave focus on the
     backdrop, which strands the keyboard outside the dialog. */
  useEffect(() => {
    if (request === null || request.options.prompt) return;
    confirmButtonRef.current?.focus();
  }, [request]);

  const tone = options?.tone ?? 'accent';
  const toneStyle = TONE_STYLES[tone];
  const ToneIcon = toneStyle.icon;

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}

      {request !== null && options !== null && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center p-4"
          role="presentation"
        >
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => settle(null)}
            aria-hidden="true"
          />

          <div
            ref={dialogRef}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
            aria-describedby={options.description ? 'confirm-dialog-description' : undefined}
            className="surface bd relative w-full max-w-md rounded-2xl border p-6 shadow-[0_32px_80px_-20px_rgba(0,0,0,0.45)]"
          >
            <div className="flex items-start gap-3.5">
              <div
                className={cn(
                  'flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px]',
                  toneStyle.iconClass,
                )}
              >
                <ToneIcon className="h-5 w-5 text-white" aria-hidden="true" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 id="confirm-dialog-title" className="font-display txt text-[16px] font-bold">
                  {options.title}
                </h2>
                {options.description && (
                  <div
                    id="confirm-dialog-description"
                    className="txt-muted mt-1.5 text-[12.5px] leading-relaxed"
                  >
                    {options.description}
                  </div>
                )}
              </div>
            </div>

            {(promptSpec !== null || options.requireTyping !== undefined) && (
              <div className="mt-4 space-y-4">
                {promptSpec !== null && (
                  <FormField
                    label={promptSpec.label}
                    required={promptSpec.required}
                    hint={promptSpec.hint}
                  >
                    {promptSpec.multiline === false ? (
                      <FormInput
                        autoFocus
                        value={value}
                        placeholder={promptSpec.placeholder}
                        onChange={(event) => setValue(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') {
                            event.preventDefault();
                            onConfirm();
                          }
                        }}
                      />
                    ) : (
                      <FormTextarea
                        autoFocus
                        value={value}
                        rows={3}
                        placeholder={promptSpec.placeholder}
                        onChange={(event) => setValue(event.target.value)}
                      />
                    )}
                  </FormField>
                )}

                {options.requireTyping !== undefined && (
                  <FormField label={`Type "${options.requireTyping}" to continue`} required>
                    <FormInput
                      value={typed}
                      onChange={(event) => setTyped(event.target.value)}
                      placeholder={options.requireTyping}
                      autoComplete="off"
                    />
                  </FormField>
                )}
              </div>
            )}

            <div className="mt-6 flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={() => settle(null)}
                className="ctl bd rounded-lg border px-4 py-2 text-[13px] font-semibold transition hover:opacity-80"
              >
                {options.cancelLabel ?? 'Cancel'}
              </button>
              <button
                ref={confirmButtonRef}
                type="button"
                onClick={onConfirm}
                disabled={blocked || settling}
                className={cn(
                  'rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50',
                  toneStyle.button,
                )}
                style={tone === 'accent' ? { background: 'var(--accent)' } : undefined}
              >
                {options.confirmLabel ?? 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
