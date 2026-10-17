'use client';

import type { HTMLAttributes, ReactNode } from 'react';
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core';
import { SortableContext, rectSortingStrategy, sortableKeyboardCoordinates, useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

import AddCardTile from '@/components/crm/dashboard/AddCardTile';
import { cn } from '@/lib/utils';
import type { HomeCardConfig, HomeCardType } from '@/features/crm/dashboard';

/* ============================================================
   DASHBOARD CARD GRID
   The customizable grid: drag-to-reorder via dnd-kit when
   `isCustomizing` is on, plain CSS grid otherwise. Each visible
   card is rendered through `renderCard`, which gets the drag
   handle props to wire into that card's own grip icon.
   ============================================================ */

//: Cards that span the full row (currently just the wide Activity
//: Timeline). A CSS `col-span` only has effect on a direct grid child, so
//: this has to be applied to the sortable wrapper itself, not to the card
//: component nested inside it.
const WIDE_CARD_TYPES: ReadonlySet<HomeCardType> = new Set(['ACTIVITY_TIMELINE']);

interface SortableSlotProps {
  id: string;
  disabled: boolean;
  wide: boolean;
  children: (dragHandleProps: HTMLAttributes<HTMLButtonElement>) => ReactNode;
}

function SortableSlot({ id, disabled, wide, children }: SortableSlotProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
    disabled,
  });

  return (
    <div
      ref={setNodeRef}
      className={cn(wide && 'md:col-span-2 xl:col-span-3')}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        zIndex: isDragging ? 10 : undefined,
      }}
    >
      {children({ ...attributes, ...listeners } as HTMLAttributes<HTMLButtonElement>)}
    </div>
  );
}

interface DashboardCardGridProps {
  visibleCards: HomeCardConfig[];
  hiddenCards: HomeCardConfig[];
  isCustomizing: boolean;
  onReorder: (fromIndex: number, toIndex: number) => void;
  onShow: (cardType: HomeCardType) => void;
  renderCard: (cardType: HomeCardType, dragHandleProps: HTMLAttributes<HTMLButtonElement>) => ReactNode;
}

export default function DashboardCardGrid({
  visibleCards,
  hiddenCards,
  isCustomizing,
  onReorder,
  onShow,
  renderCard,
}: DashboardCardGridProps) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const fromIndex = visibleCards.findIndex((card) => card.card_type === active.id);
    const toIndex = visibleCards.findIndex((card) => card.card_type === over.id);
    if (fromIndex === -1 || toIndex === -1) return;
    onReorder(fromIndex, toIndex);
  }

  return (
    <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
      <SortableContext items={visibleCards.map((card) => card.card_type)} strategy={rectSortingStrategy}>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visibleCards.map((card) => (
            <SortableSlot
              key={card.card_type}
              id={card.card_type}
              disabled={!isCustomizing}
              wide={WIDE_CARD_TYPES.has(card.card_type)}
            >
              {(dragHandleProps) =>
                renderCard(card.card_type, isCustomizing ? dragHandleProps : ({} as HTMLAttributes<HTMLButtonElement>))
              }
            </SortableSlot>
          ))}
          {isCustomizing && <AddCardTile hiddenCards={hiddenCards} onAdd={onShow} />}
        </div>
      </SortableContext>
    </DndContext>
  );
}

export type { DashboardCardGridProps };
