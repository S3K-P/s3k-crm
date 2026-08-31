/**
 * Platform contracts: the S3K app catalogue, organizations and invitations.
 *
 * Hand-written to mirror the backend's Pydantic models, like
 * `features/auth/types.ts`, and replaced wholesale when doc 11's generated
 * client arrives.
 */

/**
 * What the client should do with an app.
 *
 * **Decided by the server, never re-derived here.** The backend resolves
 * availability, licence, expiry and the administrator switch together in
 * `ProductService.describe_apps`; a second copy of that rule in the browser
 * would eventually disagree with the one the API enforces, and the UI would
 * either hide something the user owns or offer something they cannot open.
 */
export type AppState = 'OPEN' | 'DISABLED' | 'NOT_LICENSED' | 'COMING_SOON';

export type AppAvailability = 'AVAILABLE' | 'COMING_SOON';

/** One app from `GET /products/apps`. */
export interface PlatformApp {
  code: string;
  name: string;
  summary: string;
  description: string;
  /** A lucide icon name, resolved against an allow-list — see `AppIcon`. */
  icon: string;
  /** Non-null only when `state` is `OPEN`. */
  route: string | null;
  availability: AppAvailability;
  sort_order: number;
  state: AppState;
  /** A usable licence exists, whatever the administrator switch says. */
  entitled: boolean;
  /** The administrator switch. `false` when there is no entitlement at all. */
  enabled: boolean;
}

export interface OrganizationSummary {
  id: string;
  name: string;
  slug: string;
  status: string;
}

/** `POST /organizations` */
export interface CreateOrganizationPayload {
  name: string;
  industry?: string | null;
  company_size?: string | null;
  country?: string | null;
  app_codes: string[];
}

export interface OrganizationCreated {
  organization: OrganizationSummary;
  /** What was actually granted — never an echo of what was asked for. */
  granted_app_codes: string[];
}

/** `POST /auth/signup` */
export interface SignupPayload {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
}

export type InvitationStatus = 'PENDING' | 'ACCEPTED' | 'REVOKED';

export interface Invitation {
  id: string;
  email: string;
  role_id: string | null;
  status: InvitationStatus;
  expires_at: string;
  created_at: string;
  accepted_at: string | null;
}

/**
 * `POST /organizations/current/invitations`.
 *
 * `token` is returned exactly once and is not recoverable afterwards — there
 * is no email backend in this deployment, so the administrator passes the link
 * on themselves.
 */
export interface InvitationCreated {
  invitation: Invitation;
  token: string;
}

/** `GET /invitations/preview` — what the accept screen may show pre-sign-in. */
export interface InvitationPreview {
  organization_name: string;
  email: string;
  expires_at: string;
}

/** Apps a user can actually open right now, in catalogue order. */
export function openableApps(apps: readonly PlatformApp[]): PlatformApp[] {
  return apps.filter((app) => app.state === 'OPEN');
}

/** Everything not currently openable — the "Explore" half of the launcher. */
export function exploreApps(apps: readonly PlatformApp[]): PlatformApp[] {
  return apps.filter((app) => app.state !== 'OPEN');
}

/**
 * A human label for a state.
 *
 * Kept beside the type so every surface — launcher, workspace, explore page,
 * admin table — says the same word for the same condition.
 */
export const APP_STATE_LABEL: Record<AppState, string> = {
  OPEN: 'Active',
  DISABLED: 'Turned off',
  NOT_LICENSED: 'Not activated',
  COMING_SOON: 'Coming soon',
};
