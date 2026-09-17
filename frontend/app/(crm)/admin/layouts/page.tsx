'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Eye, LayoutTemplate, Loader2, Plus, Radio, Trash2 } from 'lucide-react';

import { useConfirm } from '@/components/crm/dialogs/ConfirmDialog';
import SlideDrawer from '@/components/crm/dialogs/SlideDrawer';
import { notifyError, notifyErrorMessage, notifySuccess } from '@/components/crm/feedback/notify';
import FormField, { FormInput, FormSelect } from '@/components/crm/forms/FormField';
import { FormError } from '@/components/crm/shared/ListStates';
import { usePermissions } from '@/context/AuthContext';
import { describeApiError, useMutation } from '@/features/shared/hooks/useCollection';
import FieldConfigDrawer from '@/components/crm/layouts/FieldConfigDrawer';
import LayoutCanvas from '@/components/crm/layouts/LayoutCanvas';
import LayoutPreview from '@/components/crm/layouts/LayoutPreview';
import {
  LAYOUT_ENTITY_TYPES,
  LAYOUT_TYPES,
  LAYOUT_TYPE_LABELS,
  addField,
  addSection,
  archiveLayout,
  createLayout,
  getLayout,
  listAvailableFields,
  listLayouts,
  publishLayout,
  unpublishLayout,
  type AvailableFieldInfo,
  type LayoutEntityType,
  type LayoutField,
  type LayoutType,
  type RecordLayout,
  type RecordLayoutDetail,
} from '@/features/crm/layouts';

/* ============================================================
   ADMIN — FORM / LAYOUT BUILDER (Checkpoint 4)

   One entity type's layout at a time: sections, drag-and-drop
   field placement, per-field configuration and conditional
   rules — see LayoutCanvas and FieldConfigDrawer. Every action
   here is a real API call against `crm.record_layouts` and its
   child tables; nothing is held only in browser state.

   Draft vs published is the one thing worth restating on this
   screen specifically: editing a layout never changes what any
   rep's form renders until "Publish" is pressed. A tenant may
   keep drafting for days without anything going live.
   ============================================================ */

const ENTITY_LABELS: Record<LayoutEntityType, string> = {
  ACCOUNT: 'Accounts',
  CONTACT: 'Contacts',
  LEAD: 'Leads',
  OPPORTUNITY: 'Opportunities',
};

function AdminLayoutsPageContent() {
  const { can } = usePermissions();
  const mayView = can('record_layouts', 'VIEW');
  const mayEdit = can('record_layouts', 'EDIT');
  const mayCreate = can('record_layouts', 'CREATE');
  const mayDelete = can('record_layouts', 'DELETE');

  // A module's own "Edit Page Layout" action deep-links here with the entity
  // (and optionally the screen) preselected, rather than landing an admin on
  // Leads every time and making them re-pick it.
  const params = useSearchParams();
  const requestedEntity = params.get('entity');
  const requestedLayoutType = params.get('layout_type');
  const initialEntity: LayoutEntityType = (LAYOUT_ENTITY_TYPES as string[]).includes(
    requestedEntity ?? '',
  )
    ? (requestedEntity as LayoutEntityType)
    : 'LEAD';
  const initialLayoutType: LayoutType = (LAYOUT_TYPES as string[]).includes(
    requestedLayoutType ?? '',
  )
    ? (requestedLayoutType as LayoutType)
    : 'DETAIL';

  const [entityType, setEntityType] = useState<LayoutEntityType>(initialEntity);
  const [layoutType, setLayoutType] = useState<LayoutType>(initialLayoutType);
  const [layoutId, setLayoutId] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [selectedField, setSelectedField] = useState<LayoutField | null>(null);
  const confirm = useConfirm();
  const { pending: publishing, run: runPublish } = useMutation();

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  // Stamped-result loads throughout this page, the same shape
  // `CustomFieldInputs.useEntitySchema` uses: a request's outcome is tagged
  // with the identity it answered and compared at read time, so a late
  // response for an entity type or layout the user has since navigated away
  // from can never repaint the screen with the wrong data — and nothing
  // calls `setState` synchronously inside an effect body to make that true.
  const [layoutsResult, setLayoutsResult] = useState<{
    entityType: LayoutEntityType;
    layoutType: LayoutType;
    layouts: RecordLayout[] | null;
    error: string | null;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const list = await listLayouts(entityType, layoutType);
        if (!cancelled) setLayoutsResult({ entityType, layoutType, layouts: list, error: null });
      } catch (caught) {
        if (!cancelled) {
          setLayoutsResult({
            entityType,
            layoutType,
            layouts: null,
            error: describeApiError(caught, 'Could not load layouts.'),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [entityType, layoutType, attempt]);

  const layouts =
    layoutsResult?.entityType === entityType && layoutsResult.layoutType === layoutType
      ? layoutsResult.layouts
      : null;
  const listError =
    layoutsResult?.entityType === entityType && layoutsResult.layoutType === layoutType
      ? layoutsResult.error
      : null;

  // The selected layout follows the loaded list: default to the published
  // one (or the first) whenever the list changes identity, adjusted at
  // render time rather than in an effect — see `LayoutCanvas` for the same
  // pattern with a fuller explanation.
  const [syncedLayouts, setSyncedLayouts] = useState(layouts);
  if (layouts !== syncedLayouts) {
    setSyncedLayouts(layouts);
    const published = layouts?.find((l) => l.status === 'PUBLISHED') ?? layouts?.[0] ?? null;
    setLayoutId(published?.id ?? null);
  }

  const [detailResult, setDetailResult] = useState<{
    layoutId: string;
    detail: RecordLayoutDetail | null;
    available: AvailableFieldInfo[];
    error: string | null;
  } | null>(null);

  useEffect(() => {
    if (!layoutId) return;
    let cancelled = false;
    void (async () => {
      try {
        const [layout, fields] = await Promise.all([
          getLayout(layoutId),
          listAvailableFields(layoutId),
        ]);
        if (!cancelled) {
          setDetailResult({ layoutId, detail: layout, available: fields, error: null });
        }
      } catch (caught) {
        if (!cancelled) {
          setDetailResult({
            layoutId,
            detail: null,
            available: [],
            error: describeApiError(caught, 'Could not load this layout.'),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [layoutId, attempt]);

  const detail =
    layoutId && detailResult?.layoutId === layoutId ? detailResult.detail : null;
  const available =
    layoutId && detailResult?.layoutId === layoutId ? detailResult.available : [];
  const detailError = layoutId && detailResult?.layoutId === layoutId ? detailResult.error : null;
  const error = listError ?? detailError;

  async function handlePublish() {
    if (!detail) return;
    const result = await confirm({
      title: `Publish "${detail.name}"?`,
      description:
        detail.status === 'PUBLISHED'
          ? 'This layout is already live; this republishes it with any unsaved arrangement.'
          : 'Every rep creating or editing a Lead, Account, Contact or Opportunity of this type will render this layout from now on.',
      tone: 'accent',
      confirmLabel: 'Publish',
    });
    if (!result) return;
    const published = await runPublish(() => publishLayout(detail.id));
    if (published) {
      notifySuccess(`"${detail.name}" is now published.`);
      reload();
    }
  }

  async function handleUnpublish() {
    if (!detail) return;
    const result = await confirm({
      title: 'Unpublish this layout?',
      description: 'Forms fall back to their built-in default. Conditional rules stop applying.',
      tone: 'warning',
      confirmLabel: 'Unpublish',
    });
    if (!result) return;
    try {
      await unpublishLayout(detail.id);
      notifySuccess('Layout unpublished.');
      reload();
    } catch (caught) {
      notifyError(caught, 'Could not unpublish.');
    }
  }

  async function handleArchive() {
    if (!detail) return;
    if (detail.status === 'PUBLISHED') {
      notifyErrorMessage('Publish another layout for this record type first.');
      return;
    }
    const result = await confirm({
      title: `Delete "${detail.name}"?`,
      tone: 'danger',
      confirmLabel: 'Delete',
    });
    if (!result) return;
    try {
      await archiveLayout(detail.id);
      notifySuccess('Layout deleted.');
      setLayoutId(null);
      reload();
    } catch (caught) {
      notifyError(caught, 'Could not delete this layout.');
    }
  }

  async function handleAddField(field: AvailableFieldInfo) {
    if (!detail) return;
    let sectionId = detail.sections[0]?.id;
    if (!sectionId) {
      try {
        const section = await addSection(detail.id, { name: 'Details', columns: 1 });
        sectionId = section.id;
      } catch (caught) {
        notifyError(caught, 'Could not create a section.');
        return;
      }
    }
    try {
      await addField(detail.id, { section_id: sectionId, field_key: field.field_key });
      reload();
    } catch (caught) {
      notifyError(caught, 'Could not add the field.');
    }
  }

  if (!mayView) {
    return (
      <div className="p-6 lg:p-8">
        <h1 className="font-display txt text-[22px] font-extrabold">Form Layouts</h1>
        <p className="txt-muted mt-1 text-[13px]">
          You do not have permission to view this organization&apos;s layouts.
        </p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col space-y-5 p-6 lg:p-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-violet-500 to-purple-600">
            <LayoutTemplate className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display txt text-[22px] font-extrabold">Form Layouts</h1>
            <p className="txt-muted mt-0.5 text-[13px]">
              Sections, fields and conditional rules for each record type&apos;s form.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <FormSelect
            options={LAYOUT_ENTITY_TYPES.map((t) => ({ value: t, label: ENTITY_LABELS[t] }))}
            value={entityType}
            onChange={(e) => setEntityType(e.target.value as LayoutEntityType)}
            className="w-auto py-2 text-[13px]"
          />
          <FormSelect
            options={LAYOUT_TYPES.map((t) => ({ value: t, label: LAYOUT_TYPE_LABELS[t] }))}
            value={layoutType}
            onChange={(e) => setLayoutType(e.target.value as LayoutType)}
            className="w-auto py-2 text-[13px]"
          />
          {layouts && layouts.length > 0 && (
            <FormSelect
              options={layouts.map((l) => ({
                value: l.id,
                label: `${l.name}${l.status === 'PUBLISHED' ? ' (published)' : ' (draft)'}`,
              }))}
              value={layoutId ?? ''}
              onChange={(e) => setLayoutId(e.target.value)}
              className="w-auto py-2 text-[13px]"
            />
          )}
          {mayCreate && (
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="btn-ghost flex items-center gap-1.5 px-3 py-2 text-[13px]"
            >
              <Plus className="h-4 w-4" /> New layout
            </button>
          )}
        </div>
      </div>

      <FormError message={error} />

      {layouts !== null && layouts.length === 0 && (
        <div className="bd surface flex flex-1 flex-col items-center justify-center rounded-xl border border-dashed p-10 text-center">
          <p className="txt text-[14px] font-semibold">No layout yet for {ENTITY_LABELS[entityType]}</p>
          <p className="txt-muted mt-1 max-w-sm text-[13px]">
            {ENTITY_LABELS[entityType]} render their built-in default form until a layout is
            created and published here.
          </p>
          {mayCreate && (
            <button
              type="button"
              onClick={() => setCreateOpen(true)}
              className="btn-primary mt-4 px-4 py-2 text-[13px]"
            >
              Create the first layout
            </button>
          )}
        </div>
      )}

      {detail && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--border)] pb-3">
            <div className="flex items-center gap-2">
              <span
                className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                  detail.status === 'PUBLISHED'
                    ? 'bg-emerald-500/15 text-emerald-500'
                    : 'bg-[var(--surface-2)] txt-muted'
                }`}
              >
                <Radio className="h-3 w-3" />
                {detail.status === 'PUBLISHED' ? 'Published' : 'Draft'}
              </span>
              {detail.description && <span className="txt-muted text-[12px]">{detail.description}</span>}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setPreviewOpen(true)}
                className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-[12.5px]"
              >
                <Eye className="h-3.5 w-3.5" /> Preview
              </button>
              {mayDelete && detail.status !== 'PUBLISHED' && (
                <button
                  type="button"
                  onClick={handleArchive}
                  className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[12.5px] text-red-500 hover:bg-red-500/10"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Delete
                </button>
              )}
              {mayEdit && detail.status === 'PUBLISHED' && (
                <button
                  type="button"
                  onClick={handleUnpublish}
                  className="btn-ghost px-3 py-1.5 text-[12.5px]"
                >
                  Unpublish
                </button>
              )}
              {mayEdit && (
                <button
                  type="button"
                  onClick={handlePublish}
                  disabled={publishing}
                  className="btn-primary px-3 py-1.5 text-[12.5px] disabled:opacity-60"
                >
                  {publishing ? 'Publishing…' : 'Publish'}
                </button>
              )}
            </div>
          </div>

          <div className="flex flex-1 gap-5 overflow-hidden">
            <aside className="bd surface w-64 shrink-0 overflow-y-auto rounded-xl border p-3">
              <h2 className="txt-muted mb-2 text-[11px] font-bold uppercase tracking-wider">
                Available fields
              </h2>
              <div className="space-y-1">
                {available
                  .filter((f) => !f.placed)
                  .map((field) => (
                    <button
                      key={field.field_key}
                      type="button"
                      disabled={!mayEdit}
                      onClick={() => handleAddField(field)}
                      className="flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-[12.5px] hover:bg-[var(--surface-2)] disabled:opacity-50"
                    >
                      <span className="txt truncate">{field.label}</span>
                      <Plus className="txt-faint h-3.5 w-3.5 shrink-0" />
                    </button>
                  ))}
                {available.every((f) => f.placed) && (
                  <p className="txt-faint px-2.5 py-1.5 text-[12px]">Every field is placed.</p>
                )}
              </div>
            </aside>

            <LayoutCanvas
              layout={detail}
              onReload={reload}
              onSelectField={setSelectedField}
              selectedFieldId={selectedField?.id ?? null}
              mayEdit={mayEdit}
            />
          </div>
        </>
      )}

      {createOpen && (
        <CreateLayoutDrawer
          entityType={entityType}
          layoutType={layoutType}
          onClose={() => setCreateOpen(false)}
          onCreated={(layout) => {
            setCreateOpen(false);
            setLayoutId(layout.id);
            reload();
          }}
        />
      )}

      {selectedField && detail && (
        <FieldConfigDrawer
          layoutId={detail.id}
          field={selectedField}
          rules={detail.rules.filter((r) => r.target_field_key === selectedField.field_key)}
          availableFields={available}
          mayEdit={mayEdit}
          onClose={() => setSelectedField(null)}
          onSaved={() => {
            setSelectedField(null);
            reload();
          }}
        />
      )}

      {previewOpen && detail && (
        <LayoutPreview layout={detail} onClose={() => setPreviewOpen(false)} />
      )}
    </div>
  );
}

/** Suspense is required: `useSearchParams` above reads the deep link a
 * module's own "Edit Page Layout" action carries the preselected entity
 * (and screen) in, and Next refuses to prerender a route that reads the
 * query string without one. */
export default function AdminLayoutsPage() {
  return (
    <Suspense
      fallback={
        <div className="txt-muted flex items-center gap-2 p-8 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" /> Loading layouts…
        </div>
      }
    >
      <AdminLayoutsPageContent />
    </Suspense>
  );
}

function CreateLayoutDrawer({
  entityType,
  layoutType,
  onClose,
  onCreated,
}: {
  entityType: LayoutEntityType;
  layoutType: LayoutType;
  onClose: () => void;
  onCreated: (layout: RecordLayout) => void;
}) {
  const { pending, error, clearError, run } = useMutation();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  async function handleCreate() {
    clearError();
    const layout = await run(() =>
      createLayout({
        entity_type: entityType,
        layout_type: layoutType,
        name,
        description: description || undefined,
      }),
    );
    if (layout) onCreated(layout);
  }

  return (
    <SlideDrawer
      open
      onClose={onClose}
      title="New layout"
      footer={
        <div className="flex justify-end gap-2">
          <button type="button" onClick={onClose} className="btn-ghost px-4 py-2 text-[13px]">
            Cancel
          </button>
          <button
            type="button"
            onClick={handleCreate}
            disabled={pending || !name.trim()}
            className="btn-primary px-4 py-2 text-[13px] disabled:opacity-60"
          >
            {pending ? 'Creating…' : 'Create'}
          </button>
        </div>
      }
    >
      <div className="space-y-4">
        <FormError message={error} />
        <FormField label="Name" required>
          <FormInput value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </FormField>
        <FormField label="Description">
          <FormInput value={description} onChange={(e) => setDescription(e.target.value)} />
        </FormField>
      </div>
    </SlideDrawer>
  );
}
