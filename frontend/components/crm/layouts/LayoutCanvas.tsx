'use client';

import { useState } from 'react';
import {
  DndContext,
  DragOverlay,
  PointerSensor,
  closestCenter,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { ChevronDown, ChevronUp, GripVertical, Lock, Settings2, Trash2 } from 'lucide-react';

import { notifyError, notifySuccess } from '@/components/crm/feedback/notify';
import {
  removeField,
  removeSection,
  reorderFields,
  updateSection,
  type LayoutField,
  type LayoutSection,
  type RecordLayoutDetail,
} from '@/features/crm/layouts';
import { cn } from '@/lib/utils';

/* ============================================================
   LAYOUT CANVAS

   The drag-and-drop half of the form builder. Every drop is
   optimistic — the field moves in the browser immediately — and
   is followed by the one API call
   (`POST /layouts/{id}/fields/reorder`) that makes the new
   arrangement the one a page refresh shows too. A failed request
   reloads the layout from the server rather than trusting local
   state, the same "optimistic, then reconcile" pattern the
   custom-fields admin screen already uses for its own reorder.

   Sections are reordered with buttons, not drag — the same
   keyboard-accessible fallback the custom-fields screen already
   established, kept deliberately simple here because fields (not
   sections) are what an administrator actually rearranges often.
   ============================================================ */

interface LayoutCanvasProps {
  layout: RecordLayoutDetail;
  onReload: () => void;
  onSelectField: (field: LayoutField) => void;
  selectedFieldId: string | null;
  mayEdit: boolean;
}

export default function LayoutCanvas({
  layout,
  onReload,
  onSelectField,
  selectedFieldId,
  mayEdit,
}: LayoutCanvasProps) {
  const [sections, setSections] = useState<LayoutSection[]>(layout.sections);
  // Re-derive local (draggable) state when the `layout` prop identity
  // changes — after a reload, publish, or a parent-triggered refetch — via
  // the render-time adjustment React recommends in place of an effect that
  // would call `setState` synchronously on every prop change:
  // https://react.dev/learn/you-might-not-need-an-effect#adjusting-state-when-a-prop-changes
  const [syncedLayout, setSyncedLayout] = useState(layout);
  if (layout !== syncedLayout) {
    setSyncedLayout(layout);
    setSections(layout.sections);
  }
  const [activeField, setActiveField] = useState<LayoutField | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 4 } }));

  function fieldLocation(fieldId: string): { sectionIndex: number; fieldIndex: number } | null {
    for (let s = 0; s < sections.length; s++) {
      const f = sections[s].fields.findIndex((field) => field.id === fieldId);
      if (f !== -1) return { sectionIndex: s, fieldIndex: f };
    }
    return null;
  }

  function handleDragStart(event: DragStartEvent) {
    const location = fieldLocation(String(event.active.id));
    if (location) setActiveField(sections[location.sectionIndex].fields[location.fieldIndex]);
  }

  async function handleDragEnd(event: DragEndEvent) {
    setActiveField(null);
    const { active, over } = event;
    if (!over || !mayEdit) return;

    const from = fieldLocation(String(active.id));
    if (!from) return;

    const overId = String(over.id);
    const toSectionId = overId.startsWith('section:')
      ? overId.slice('section:'.length)
      : sections[fieldLocation(overId)?.sectionIndex ?? from.sectionIndex]?.id;
    const toSectionIndex = sections.findIndex((s) => s.id === toSectionId);
    if (toSectionIndex === -1) return;

    const next = sections.map((section) => ({ ...section, fields: [...section.fields] }));
    const [moved] = next[from.sectionIndex].fields.splice(from.fieldIndex, 1);

    const overLocation = fieldLocation(overId);
    let insertAt = next[toSectionIndex].fields.length;
    if (overLocation && overLocation.sectionIndex === toSectionIndex) {
      insertAt = overLocation.fieldIndex;
    } else if (
      from.sectionIndex === toSectionIndex &&
      overLocation &&
      overLocation.fieldIndex > from.fieldIndex
    ) {
      insertAt = overLocation.fieldIndex;
    }
    next[toSectionIndex].fields.splice(insertAt, 0, moved);

    if (
      from.sectionIndex === toSectionIndex &&
      from.fieldIndex === insertAt
    ) {
      return; // dropped back where it started — nothing changed
    }

    setSections(next);

    const entries = next.flatMap((section) =>
      section.fields.map((field, index) => ({
        field_id: field.id,
        section_id: section.id,
        position: index,
      })),
    );
    try {
      await reorderFields(layout.id, entries);
    } catch (caught) {
      notifyError(caught, 'Could not save the new arrangement.');
      onReload();
    }
  }

  async function moveSectionVertically(index: number, delta: number) {
    const target = index + delta;
    if (target < 0 || target >= sections.length) return;
    const reordered = arrayMove(sections, index, target);
    setSections(reordered);
    try {
      await Promise.all(
        reordered.map((section, position) => updateSection(layout.id, section.id, { position })),
      );
    } catch (caught) {
      notifyError(caught, 'Could not reorder sections.');
      onReload();
    }
  }

  async function handleRemoveField(field: LayoutField) {
    setSections((prev) =>
      prev.map((section) => ({
        ...section,
        fields: section.fields.filter((f) => f.id !== field.id),
      })),
    );
    try {
      await removeField(layout.id, field.id);
      notifySuccess('Field removed from the layout.');
    } catch (caught) {
      notifyError(caught, 'Could not remove the field.');
      onReload();
    }
  }

  async function handleRemoveSection(section: LayoutSection) {
    setSections((prev) => prev.filter((s) => s.id !== section.id));
    try {
      await removeSection(layout.id, section.id);
      notifySuccess(`"${section.name}" removed.`);
    } catch (caught) {
      notifyError(caught, 'Could not remove the section.');
      onReload();
    }
  }

  async function renameSection(section: LayoutSection, name: string) {
    if (!name.trim() || name === section.name) return;
    setSections((prev) => prev.map((s) => (s.id === section.id ? { ...s, name } : s)));
    try {
      await updateSection(layout.id, section.id, { name });
    } catch (caught) {
      notifyError(caught, 'Could not rename the section.');
      onReload();
    }
  }

  async function setSectionColumns(section: LayoutSection, columns: number) {
    setSections((prev) => prev.map((s) => (s.id === section.id ? { ...s, columns } : s)));
    try {
      await updateSection(layout.id, section.id, { columns });
    } catch (caught) {
      notifyError(caught, 'Could not change the column count.');
      onReload();
    }
  }

  if (sections.length === 0) {
    return (
      <div className="bd surface flex flex-1 items-center justify-center rounded-xl border border-dashed p-10 text-center">
        <p className="txt-muted text-[13px]">
          Add a section to start placing fields on this layout.
        </p>
      </div>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={closestCenter}
      onDragStart={handleDragStart}
      onDragEnd={handleDragEnd}
    >
      <div className="flex-1 space-y-4 overflow-y-auto pr-1">
        {sections.map((section, index) => (
          <SectionCard
            key={section.id}
            section={section}
            index={index}
            total={sections.length}
            mayEdit={mayEdit}
            selectedFieldId={selectedFieldId}
            onSelectField={onSelectField}
            onRemoveField={handleRemoveField}
            onRemoveSection={handleRemoveSection}
            onRename={renameSection}
            onSetColumns={setSectionColumns}
            onMove={moveSectionVertically}
          />
        ))}
      </div>
      <DragOverlay>
        {activeField && (
          <div className="surface bd flex items-center gap-2 rounded-lg border px-3 py-2 shadow-lg">
            <GripVertical className="txt-faint h-3.5 w-3.5" />
            <span className="txt text-[12.5px] font-medium">
              {activeField.label_override ?? activeField.field_key}
            </span>
          </div>
        )}
      </DragOverlay>
    </DndContext>
  );
}

function SectionCard({
  section,
  index,
  total,
  mayEdit,
  selectedFieldId,
  onSelectField,
  onRemoveField,
  onRemoveSection,
  onRename,
  onSetColumns,
  onMove,
}: {
  section: LayoutSection;
  index: number;
  total: number;
  mayEdit: boolean;
  selectedFieldId: string | null;
  onSelectField: (field: LayoutField) => void;
  onRemoveField: (field: LayoutField) => void;
  onRemoveSection: (section: LayoutSection) => void;
  onRename: (section: LayoutSection, name: string) => void;
  onSetColumns: (section: LayoutSection, columns: number) => void;
  onMove: (index: number, delta: number) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: `section:${section.id}` });

  return (
    <div className="surface bd rounded-xl border p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <input
          defaultValue={section.name}
          disabled={!mayEdit}
          onBlur={(event) => onRename(section, event.target.value)}
          className="txt bg-transparent text-[13.5px] font-semibold outline-none focus:underline disabled:cursor-default"
          aria-label="Section name"
        />
        <div className="flex items-center gap-1">
          <select
            value={section.columns}
            disabled={!mayEdit}
            onChange={(event) => onSetColumns(section, Number(event.target.value))}
            className="ctl px-2 py-1 text-[11.5px]"
            aria-label="Section columns"
          >
            <option value={1}>1 column</option>
            <option value={2}>2 columns</option>
          </select>
          <button
            type="button"
            disabled={!mayEdit || index === 0}
            onClick={() => onMove(index, -1)}
            className="txt-muted rounded p-1 hover:bg-[var(--surface-2)] disabled:opacity-30"
            aria-label="Move section up"
          >
            <ChevronUp className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            disabled={!mayEdit || index === total - 1}
            onClick={() => onMove(index, 1)}
            className="txt-muted rounded p-1 hover:bg-[var(--surface-2)] disabled:opacity-30"
            aria-label="Move section down"
          >
            <ChevronDown className="h-3.5 w-3.5" />
          </button>
          {mayEdit && (
            <button
              type="button"
              onClick={() => onRemoveSection(section)}
              className="rounded p-1 text-red-500 hover:bg-red-500/10"
              aria-label="Remove section"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      <SortableContext
        items={section.fields.map((f) => f.id)}
        strategy={verticalListSortingStrategy}
      >
        <div
          ref={setNodeRef}
          className={cn(
            'grid min-h-[44px] gap-2 rounded-lg p-1',
            section.columns === 2 ? 'grid-cols-2' : 'grid-cols-1',
            isOver && 'bg-[var(--accent)]/5 ring-1 ring-[var(--accent)]/30',
          )}
        >
          {section.fields.length === 0 && (
            <p className="txt-faint col-span-full py-3 text-center text-[11.5px]">
              Drop fields here
            </p>
          )}
          {section.fields.map((field) => (
            <FieldChip
              key={field.id}
              field={field}
              mayEdit={mayEdit}
              selected={field.id === selectedFieldId}
              onSelect={() => onSelectField(field)}
              onRemove={() => onRemoveField(field)}
            />
          ))}
        </div>
      </SortableContext>
    </div>
  );
}

function FieldChip({
  field,
  mayEdit,
  selected,
  onSelect,
  onRemove,
}: {
  field: LayoutField;
  mayEdit: boolean;
  selected: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: field.id,
    disabled: !mayEdit,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    gridColumn: field.column_span === 2 ? 'span 2 / span 2' : undefined,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        'bd flex items-center gap-1.5 rounded-lg border bg-[var(--surface)] px-2 py-2 text-[12.5px]',
        selected && 'border-[var(--accent)] ring-1 ring-[var(--accent)]',
        isDragging && 'opacity-40',
      )}
    >
      {mayEdit && (
        <button
          type="button"
          className="txt-faint cursor-grab touch-none active:cursor-grabbing"
          aria-label={`Drag to reposition ${field.field_key}`}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="h-3.5 w-3.5" />
        </button>
      )}
      <button type="button" onClick={onSelect} className="txt flex-1 truncate text-left font-medium">
        {field.label_override ?? field.field_key.replace('custom:', '')}
      </button>
      {field.is_read_only && <Lock className="txt-faint h-3 w-3 shrink-0" />}
      {mayEdit && (
        <>
          <button
            type="button"
            onClick={onSelect}
            className="txt-faint rounded p-0.5 hover:bg-[var(--surface-2)]"
            aria-label="Configure field"
          >
            <Settings2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onRemove}
            className="rounded p-0.5 text-red-500/70 hover:bg-red-500/10 hover:text-red-500"
            aria-label="Remove field"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </>
      )}
    </div>
  );
}
