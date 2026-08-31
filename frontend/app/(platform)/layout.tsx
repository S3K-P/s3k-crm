import RequireAuth from '@/components/auth/RequireAuth';
import RequireOrganization from '@/components/platform/RequireOrganization';
import PlatformHeader from '@/components/platform/PlatformHeader';

/* ============================================================
   PLATFORM ROUTE GROUP LAYOUT

   The S3K shell that sits *above* any individual app: the
   workspace and the app catalogue live here. Deliberately no
   sidebar — this layer is about choosing an app, and the app
   supplies its own navigation once you are inside it.

   Two guards, in order. `RequireAuth` decides whether anybody is
   signed in; `RequireOrganization` decides whether they belong
   to a tenant yet. Neither is the security boundary — the
   backend authorizes every request — they only decide what the
   browser renders.
   ============================================================ */

export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  return (
    <RequireAuth>
      <RequireOrganization>
        <div className="flex min-h-screen flex-col" style={{ background: 'var(--bg)' }}>
          <PlatformHeader />
          <main className="flex-1">{children}</main>
        </div>
      </RequireOrganization>
    </RequireAuth>
  );
}
