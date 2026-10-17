'use client';

import { useEffect, useCallback } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ============================================================
   MODAL
   Centered create/edit dialog, replacing the right-side
   SlideDrawer pattern for CRM module forms. Traps Escape to
   close, locks body scroll while open, sticky footer for
   Save actions.
   ============================================================ */

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  /** Tailwind max-width class, e.g. "max-w-2xl" */
  maxWidth?: string;
  children: React.ReactNode;
  footer?: React.ReactNode;
}

export default function Modal({
  open,
  onClose,
  title,
  subtitle,
  maxWidth = 'max-w-2xl',
  children,
  footer,
}: ModalProps) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
  }, [onClose]);

  useEffect(() => {
    if (open) {
      document.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [open, handleKeyDown]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/45 px-4 py-[4vh] backdrop-blur-[2px]"
      onClick={onClose}
    >
      <div
        className={cn(
          'surface bd flex w-full max-h-[92vh] flex-col rounded-2xl border shadow-[0_32px_80px_-20px_rgba(0,0,0,0.4)]',
          maxWidth,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="bd flex shrink-0 items-center justify-between border-b px-6 py-4">
          <div>
            <h2 className="font-display txt text-[16px] font-bold">{title}</h2>
            {subtitle && <p className="txt-muted mt-0.5 text-[12px]">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="ctl grid h-8 w-8 shrink-0 place-items-center rounded-lg transition hover:opacity-80"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="bd surface sticky bottom-0 flex shrink-0 items-center justify-end gap-2.5 rounded-b-2xl border-t px-6 py-4">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
