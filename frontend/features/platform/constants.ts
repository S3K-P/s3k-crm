/**
 * Product codes, mirroring `app.platform.products.models`.
 *
 * These are the backend's stable machine identifiers. They appear here because
 * the frontend has to name the app it is currently inside — the launcher marks
 * it "Current" — and a literal string sprinkled through components is the kind
 * of thing that survives a rename on only one side.
 */

/** The CRM's code in the catalogue. The one product that ships today. */
export const CRM_PRODUCT_CODE = 's3k-crm';
