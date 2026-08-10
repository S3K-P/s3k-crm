import Link from 'next/link';
import { BRAND } from '@/config/site';
import BrandLogo from '@/components/brand/BrandLogo';

export function LandingFooter() {
  return (
    <footer className="bg-white py-16 border-t border-gray-100">
      <div className="max-w-7xl mx-auto px-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-8 mb-12">
          <div className="max-w-xs">
            <Link href="/" className="flex items-center gap-2 mb-4">
              <BrandLogo className="h-8 rounded-lg" />
              <span className="text-lg font-bold text-gray-900 tracking-tight">
                {BRAND.name}
              </span>
            </Link>
            <p className="text-sm text-gray-500 leading-relaxed">
              S3K CRM helps growing businesses organize customer relationships, manage opportunities, and improve sales visibility.
            </p>
          </div>
          
          <div className="flex flex-wrap gap-8 text-sm font-medium text-gray-600">
            <Link href="#features" className="hover:text-brand-violet transition-colors">Features</Link>
            <Link href="#how-it-works" className="hover:text-brand-violet transition-colors">How It Works</Link>
            <Link href="#solutions" className="hover:text-brand-violet transition-colors">Solutions</Link>
            <Link href="/dashboard" className="hover:text-brand-violet transition-colors text-brand-violet">Dashboard</Link>
          </div>
        </div>
        
        <div className="pt-8 border-t border-gray-100 flex flex-col sm:flex-row items-center justify-between gap-4">
          <p className="text-xs text-gray-400">
            © {new Date().getFullYear()} {BRAND.footer}
          </p>
          <div className="flex items-center gap-6 text-xs font-medium text-gray-400">
            <Link href="#" className="hover:text-gray-900 transition-colors">Privacy Policy</Link>
            <Link href="#" className="hover:text-gray-900 transition-colors">Terms of Service</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
