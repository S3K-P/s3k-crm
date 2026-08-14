'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useRouter } from 'next/navigation';

import {
  api,
  apiRequest,
  setAccessToken,
  setOrganizationId,
  setSessionExpiredHandler,
} from '@/lib/api-client';
import { AUTH_ENABLED, LOGIN_PATH, POST_LOGIN_PATH } from '@/lib/api-config';
import type {
  CurrentUser,
  LoginCredentials,
  Membership,
  PermissionAction,
  TokenResponse,
} from '@/features/auth/types';
import { permission } from '@/features/auth/types';

/* ============================================================
   AUTH CONTEXT
   Session state for the whole app: who is signed in, which
   organization they are acting in, and what they may do.

   The access token is deliberately absent from this state — it
   lives only inside the API client, so no component can read it
   and it can never end up in a serialized React tree.
   ============================================================ */

interface AuthContextValue {
  /** `null` once loading finishes and nobody is signed in. */
  currentUser: CurrentUser | null;
  /** True while the initial session probe is in flight. */
  loading: boolean;
  isAuthenticated: boolean;
  /** Organizations the user belongs to. */
  memberships: Membership[];
  activeOrganizationId: string | null;
  login: (credentials: LoginCredentials) => Promise<void>;
  logout: () => Promise<void>;
  switchOrganization: (organizationId: string) => Promise<void>;
  /** Effective permissions in the active organization. */
  permissions: ReadonlySet<string>;
  /**
   * Whether the user holds `module.action`.
   *
   * **UX only.** The backend re-checks every request; hiding a button here
   * does not protect anything, and showing one does not grant anything.
   */
  can: (module: string, action: PermissionAction) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Remembers the last organization chosen, so a reload keeps the context. */
const ORGANIZATION_STORAGE_KEY = 's3k-active-organization';

function readStoredOrganization(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(ORGANIZATION_STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeOrganization(organizationId: string | null): void {
  try {
    if (organizationId) {
      window.localStorage.setItem(ORGANIZATION_STORAGE_KEY, organizationId);
    } else {
      window.localStorage.removeItem(ORGANIZATION_STORAGE_KEY);
    }
  } catch {
    // A blocked storage API must not break sign-in.
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  // With no backend configured there is no session to probe for, so the app
  // starts ready rather than stuck on a loading state.
  const [loading, setLoading] = useState(AUTH_ENABLED);

  const clearSession = useCallback(() => {
    setAccessToken(null);
    setOrganizationId(null);
    storeOrganization(null);
    setCurrentUser(null);
  }, []);

  const loadCurrentUser = useCallback(async (): Promise<CurrentUser | null> => {
    const me = await api.get<CurrentUser>('/auth/me');
    setCurrentUser(me);
    const active = me.active_organization_id;
    setOrganizationId(active);
    storeOrganization(active);
    return me;
  }, []);

  /* --- Restore a session on first mount ---------------------------------
     The refresh cookie is httpOnly, so the only way to know whether a
     session exists is to try to use it. A failure here is the normal
     "not signed in" case, not an error. */
  useEffect(() => {
    if (!AUTH_ENABLED) return;

    let cancelled = false;

    const restore = async () => {
      try {
        const refreshed = await apiRequest<TokenResponse>('/auth/refresh', {
          method: 'POST',
          body: {},
          skipRefresh: true,
        });
        if (cancelled) return;
        setAccessToken(refreshed.access_token);
        setOrganizationId(readStoredOrganization() ?? refreshed.organization_id);
        await loadCurrentUser();
      } catch {
        if (!cancelled) clearSession();
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void restore();
    return () => {
      cancelled = true;
    };
  }, [loadCurrentUser, clearSession]);

  /* --- End the session when a refresh finally fails ---------------------- */
  useEffect(() => {
    setSessionExpiredHandler(() => {
      clearSession();
      if (AUTH_ENABLED) router.replace(LOGIN_PATH);
    });
    return () => setSessionExpiredHandler(null);
  }, [clearSession, router]);

  const login = useCallback(
    async (credentials: LoginCredentials) => {
      const tokens = await apiRequest<TokenResponse>('/auth/login', {
        method: 'POST',
        body: credentials,
        skipRefresh: true,
      });
      setAccessToken(tokens.access_token);
      setOrganizationId(tokens.organization_id);
      storeOrganization(tokens.organization_id);
      await loadCurrentUser();
    },
    [loadCurrentUser],
  );

  const logout = useCallback(async () => {
    try {
      await api.post('/auth/logout');
    } catch {
      // Sign-out is best-effort: the local session is cleared regardless.
    }
    clearSession();
    router.replace(LOGIN_PATH);
  }, [clearSession, router]);

  const switchOrganization = useCallback(
    async (organizationId: string) => {
      // Permissions are per-organization, so the profile must be re-read
      // rather than reused across the switch.
      setOrganizationId(organizationId);
      storeOrganization(organizationId);
      const me = await api.get<CurrentUser>('/auth/me');
      setCurrentUser(me);
    },
    [],
  );

  const permissions = useMemo(
    () => new Set(currentUser?.permissions ?? []),
    [currentUser],
  );

  const can = useCallback(
    (module: string, action: PermissionAction) => {
      // With no backend there is nothing to authorize against; the existing
      // demonstration pages must stay fully usable.
      if (!AUTH_ENABLED) return true;
      return permissions.has(permission(module, action));
    },
    [permissions],
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      currentUser,
      loading,
      isAuthenticated: currentUser !== null,
      memberships: currentUser?.memberships ?? [],
      activeOrganizationId: currentUser?.active_organization_id ?? null,
      login,
      logout,
      switchOrganization,
      permissions,
      can,
    }),
    [currentUser, loading, login, logout, switchOrganization, permissions, can],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error('useAuth must be used inside an <AuthProvider>.');
  }
  return context;
}

/** Convenience hook for permission-aware UI. */
export function usePermissions() {
  const { can, permissions } = useAuth();
  return { can, permissions };
}

export { POST_LOGIN_PATH };
