import { BRAND } from '@/config/site';

export default function Footer() {
  return (
    <footer className="surface bd border-t py-3.5">
      <div className="px-6">
        <p className="txt-faint text-center text-xs">
          {BRAND.footer}
        </p>
      </div>
    </footer>
  );
}
