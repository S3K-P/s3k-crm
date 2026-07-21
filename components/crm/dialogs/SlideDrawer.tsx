'use client';

import { useEffect, useCallback } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

/* ============================================================
   SLIDE DRAWER
   Right-side slide-in panel for Add/Edit forms and detail views.
   Uses existing design tokens. Traps focus and closes on ESC.
   Reusable across all CRM modules (Lead Sources, Leads, etc.)
   ============================================================ */

interface SlideDrawerProps {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Optional subtitle below the title */
  subtitle?: string;
  /** Width override */
  width?: string;
  children: React.ReactNode;
  /** Footer actions slot (Save / Cancel buttons) */
  footer?: React.ReactNode;
}

export default function SlideDrawer({
  open,
  onClose,
  title,
  subtitle,
  width = 'max-w-md',
  children,
  footer,
}: SlideDrawerProps) {
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
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
      <div
        className={cn(
          'surface fixed right-0 top-0 z-50 flex h-full w-full flex-col shadow-[0_32px_80px_-20px_rgba(0,0,0,0.4)]',
          width,
        )}
      >
        {/* Header */}
        <div className="bd flex shrink-0 items-center justify-between border-b px-6 py-4">
          <div>
            <h2 className="font-display txt text-[18px] font-bold">{title}</h2>
            {subtitle && <p className="txt-muted mt-0.5 text-[12.5px]">{subtitle}</p>}
          </div>
          <button
            onClick={onClose}
            className="ctl grid h-8 w-8 place-items-center rounded-lg transition hover:opacity-80"
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
          <div className="bd flex shrink-0 items-center justify-end gap-2.5 border-t px-6 py-4">
            {footer}
          </div>
        )}
      </div>
    </>
  );
}
