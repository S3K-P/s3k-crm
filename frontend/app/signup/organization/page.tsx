'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AlertCircle, ArrowLeft, Building2, Check, Loader2 } from 'lucide-react';

import OnboardingShell from '@/components/platform/OnboardingShell';
import { AppIcon } from '@/features/platform/AppIcon';
import RequireAuth from '@/components/auth/RequireAuth';
import { useAuth } from '@/context/AuthContext';
import { api, ApiError } from '@/lib/api-client';
import type { OrganizationCreated } from '@/features/platform/types';

/* ============================================================
   SIGN UP — STEPS 2 & 3: ORGANIZATION, THEN APPS

   Two screens, one request. The tenant, its administrator, its
   entitlements and each app's first-run setup are created in a
   single transaction on the server, so there is no state where
   an organization exists without an owner or without the apps
   the customer chose.

   The app list comes from `/products/catalogue`, so it can only
   ever offer products that actually exist. Anything not
   `AVAILABLE` is shown but not selectable: S3K has not built it,
   and letting somebody tick it would be promising a product on
   the first screen of the relationship.
   ============================================================ */

interface CatalogueEntry {
  code: string;
  name: string;
  summary: string;
  icon: string;
  availability: 'AVAILABLE' | 'COMING_SOON';
  self_serve: boolean;
  sort_order: number;
}

const INDUSTRIES = [
  'Technology',
  'Professional services',
  'Manufacturing',
  'Retail & e-commerce',
  'Healthcare',
  'Financial services',
  'Education',
  'Other',
];

const COMPANY_SIZES = ['1-10', '11-50', '51-200', '201-1000', '1000+'];

export default function OnboardingOrganizationPage() {
  return (
    <RequireAuth>
      <OrganizationWizard />
    </RequireAuth>
  );
}

function OrganizationWizard() {
  const router = useRouter();
  const { memberships, loading, refreshProfile } = useAuth();

  const [stage, setStage] = useState<'details' | 'apps'>('details');
  const [name, setName] = useState('');
  const [industry, setIndustry] = useState('');
  const [companySize, setCompanySize] = useState('');
  const [country, setCountry] = useState('');

  const [catalogue, setCatalogue] = useState<CatalogueEntry[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [catalogueLoading, setCatalogueLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // Somebody who already belongs somewhere does not need this wizard. This is
  // the guard that stops an invited user who wandered here from founding a
  // second organization they did not mean to create.
  useEffect(() => {
    if (!loading && memberships.length > 0) router.replace('/workspace');
  }, [loading, memberships, router]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const entries = await api.get<CatalogueEntry[]>('/products/catalogue');
        if (cancelled) return;
        setCatalogue(entries);
        // Pre-select everything self-service can actually grant, so the common
        // case is one click. Today that is the CRM.
        setSelected(
          entries
            .filter((entry) => entry.self_serve && entry.availability === 'AVAILABLE')
            .map((entry) => entry.code),
        );
      } catch {
        if (!cancelled) setError('Unable to load the S3K app catalogue.');
      } finally {
        if (!cancelled) setCatalogueLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const toggle = (code: string) =>
    setSelected((current) =>
      current.includes(code)
        ? current.filter((item) => item !== code)
        : [...current, code],
    );

  const submit = async () => {
    if (submitting) return;
    setError(null);
    setSubmitting(true);
    try {
      const created = await api.post<OrganizationCreated>('/organizations', {
        name: name.trim(),
        industry: industry || null,
        company_size: companySize || null,
        country: country.trim() || null,
        app_codes: selected,
      });
      // The session already exists; re-reading the profile is what makes the
      // new organization and its permissions current. No second sign-in.
      await refreshProfile();
      router.replace(created.granted_app_codes.length > 0 ? '/workspace' : '/apps');
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Unable to create your organization right now. Please try again.',
      );
      setStage('details');
    } finally {
      setSubmitting(false);
    }
  };

  if (stage === 'details') {
    return (
      <OnboardingShell
        step={2}
        title="Welcome to S3K"
        subtitle="Let's set up your organization."
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setStage('apps');
          }}
          className="mt-5 space-y-4"
          noValidate
        >
          <div className="space-y-1.5">
            <label htmlFor="org_name" className="txt text-[13px] font-semibold">
              Organization name
            </label>
            <div className="relative">
              <Building2
                className="txt-faint pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
                aria-hidden="true"
              />
              <input
                id="org_name"
                required
                value={name}
                onChange={(event) => setName(event.target.value)}
                className="ctl w-full py-2.5 pl-9 pr-3.5 text-sm outline-none transition-colors focus:border-[var(--accent)]"
                placeholder="Acme Ltd"
              />
            </div>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <label htmlFor="industry" className="txt text-[13px] font-semibold">
                Industry
              </label>
              <select
                id="industry"
                value={industry}
                onChange={(event) => setIndustry(event.target.value)}
                className="ctl w-full px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-[var(--accent)]"
              >
                <option value="">Select…</option>
                {INDUSTRIES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="company_size" className="txt text-[13px] font-semibold">
                Company size
              </label>
              <select
                id="company_size"
                value={companySize}
                onChange={(event) => setCompanySize(event.target.value)}
                className="ctl w-full px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-[var(--accent)]"
              >
                <option value="">Select…</option>
                {COMPANY_SIZES.map((item) => (
                  <option key={item} value={item}>
                    {item} people
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="country" className="txt text-[13px] font-semibold">
              Country
            </label>
            <input
              id="country"
              value={country}
              onChange={(event) => setCountry(event.target.value)}
              className="ctl w-full px-3.5 py-2.5 text-sm outline-none transition-colors focus:border-[var(--accent)]"
              placeholder="United Kingdom"
            />
          </div>

          {error && <ErrorLine message={error} />}

          <button
            type="submit"
            disabled={!name.trim()}
            className="w-full rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            style={{ background: 'var(--accent)' }}
          >
            Continue
          </button>
        </form>
      </OnboardingShell>
    );
  }

  return (
    <OnboardingShell
      step={3}
      wide
      title="Choose the apps you want to use"
      subtitle="You can change this later in Settings."
    >
      {catalogueLoading ? (
        <p className="txt-muted mt-5 flex items-center gap-2 text-[13px]">
          <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
          Loading apps…
        </p>
      ) : (
        <>
          <fieldset className="mt-5 space-y-2.5">
            <legend className="sr-only">S3K applications</legend>
            {catalogue.map((entry) => {
              const selectable = entry.availability === 'AVAILABLE' && entry.self_serve;
              const checked = selected.includes(entry.code);
              return (
                <label
                  key={entry.code}
                  className={`seg flex items-center gap-3 p-3.5 transition-all ${
                    checked ? 'seg-on' : ''
                  } ${
                    selectable
                      ? 'cursor-pointer hover:border-[var(--accent)]'
                      : 'cursor-not-allowed opacity-60'
                  }`}
                >
                  <input
                    type="checkbox"
                    className="sr-only"
                    checked={checked}
                    disabled={!selectable}
                    onChange={() => selectable && toggle(entry.code)}
                  />
                  <span
                    className="grid h-9 w-9 shrink-0 place-items-center rounded-lg"
                    style={{
                      background: checked ? 'var(--accent)' : 'var(--surface-2)',
                    }}
                  >
                    <AppIcon
                      name={entry.icon}
                      className={`h-4 w-4 ${checked ? 'text-white' : 'txt-faint'}`}
                    />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="txt block text-[13.5px] font-semibold">
                      {entry.name}
                    </span>
                    <span className="txt-muted block text-[12px]">{entry.summary}</span>
                  </span>
                  {!selectable && (
                    <span className="txt-faint shrink-0 text-[10.5px] font-bold uppercase tracking-wider">
                      Coming soon
                    </span>
                  )}
                  {checked && (
                    <Check
                      className="h-4 w-4 shrink-0"
                      style={{ color: 'var(--accent)' }}
                      aria-hidden="true"
                    />
                  )}
                </label>
              );
            })}
          </fieldset>

          {error && (
            <div className="mt-4">
              <ErrorLine message={error} />
            </div>
          )}

          <div className="mt-6 flex items-center gap-3">
            <button
              type="button"
              onClick={() => setStage('details')}
              disabled={submitting}
              className="bd txt flex items-center gap-1.5 rounded-lg border px-3.5 py-2.5 text-[13px] font-semibold transition hover:opacity-80 disabled:opacity-50"
            >
              <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
              Back
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={submitting}
              className="flex flex-1 items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-[13.5px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              style={{ background: 'var(--accent)' }}
            >
              {submitting && (
                <Loader2 className="h-4 w-4 motion-safe:animate-spin" aria-hidden="true" />
              )}
              {submitting ? 'Setting up your workspace…' : 'Continue'}
            </button>
          </div>
        </>
      )}
    </OnboardingShell>
  );
}

function ErrorLine({ message }: { message: string }) {
  return (
    <p role="alert" className="flex items-start gap-2 text-[12.5px] font-medium text-red-500">
      <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}
