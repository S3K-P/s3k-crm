import Link from 'next/link';
import { Mail, Globe } from 'lucide-react';
import BrandLogo from '@/components/brand/BrandLogo';
import { BRAND } from '@/config/site';

/* ============================================================
   CRM FOOTER
   Small persistent strip at the bottom of the app shell:
   brand mark (left), copyright (center), contact (right).
   ============================================================ */

const CONTACT_EMAIL = 'discover@s3ktech.ai';
const WEBSITE_URL = 'https://www.s3ktech.ai/';
const WEBSITE_LABEL = 's3ktech.ai';

export default function CrmFooter() {
  return (
    <footer className="bd surface flex shrink-0 flex-wrap items-center justify-between gap-2 border-t px-5 py-2.5">
      <BrandLogo variant="wordmark" className="h-6" label={BRAND.name} />

      <p className="txt-faint order-3 w-full text-center text-[11px] sm:order-none sm:w-auto">
        © {new Date().getFullYear()} {BRAND.footer}
      </p>

      <div className="txt-faint flex items-center gap-4 text-[11px]">
        <a
          href={`mailto:${CONTACT_EMAIL}`}
          className="flex items-center gap-1.5 transition hover:opacity-80"
        >
          <Mail className="h-3 w-3" aria-hidden="true" />
          {CONTACT_EMAIL}
        </a>
        <Link
          href={WEBSITE_URL}
          target="_blank"
          rel="noreferrer"
          className="flex items-center gap-1.5 transition hover:opacity-80"
        >
          <Globe className="h-3 w-3" aria-hidden="true" />
          {WEBSITE_LABEL}
        </Link>
      </div>
    </footer>
  );
}
