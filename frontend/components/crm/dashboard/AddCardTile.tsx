'use client';

import { useState } from 'react';
import { Plus } from 'lucide-react';

import { CARD_CATALOG } from '@/components/crm/dashboard/cardCatalog';
import type { HomeCardConfig } from '@/features/crm/dashboard';

interface AddCardTileProps {
  hiddenCards: HomeCardConfig[];
  onAdd: (cardType: HomeCardConfig['card_type']) => void;
}

/** The dashed "Add Card" tile, shown only while customizing. Opens a picker
 * of the cards the user has hidden. */
export default function AddCardTile({ hiddenCards, onAdd }: AddCardTileProps) {
  const [open, setOpen] = useState(false);

  if (hiddenCards.length === 0) {
    return (
      <div
        className="flex min-h-[160px] flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-6 text-center text-[12.5px] font-semibold"
        style={{ borderColor: 'var(--border)', color: 'var(--faint)' }}
      >
        Every card is already on your dashboard.
      </div>
    );
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex min-h-[160px] w-full flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed p-6 text-[12.5px] font-semibold transition hover:border-[var(--accent)] hover:text-[var(--accent)]"
        style={{ borderColor: 'var(--border)', color: 'var(--faint)' }}
      >
        <Plus className="h-6 w-6" />
        Add Card
      </button>

      {open && (
        <div
          className="surface bd absolute bottom-full left-0 z-50 mb-2 w-full min-w-[220px] rounded-xl border p-1.5 shadow-lg"
          role="menu"
        >
          {hiddenCards.map((card) => {
            const meta = CARD_CATALOG[card.card_type];
            const Icon = meta.icon;
            return (
              <button
                key={card.card_type}
                type="button"
                role="menuitem"
                onClick={() => {
                  onAdd(card.card_type);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[12.5px] font-medium transition hover:bg-[var(--surface-2)]"
              >
                <Icon className="h-4 w-4" style={{ color: 'var(--muted)' }} />
                {meta.title}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
