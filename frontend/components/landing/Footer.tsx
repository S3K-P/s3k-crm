import Link from 'next/link';
import { BRAND } from '@/config/site';
import { Twitter, Linkedin, Github } from 'lucide-react';

const footerLinks = {
  Platform: ['Dashboard', 'Pipeline', 'Analytics', 'AI Copilot', 'Integrations'],
  Solutions: ['Sales Teams', 'Marketing Teams', 'Revenue Operations', 'Enterprise'],
  Resources: ['Documentation', 'API Reference', 'Blog', 'Case Studies', 'Help Center'],
  Company: ['About Us', 'Careers', 'Contact', 'Partners', 'Legal'],
};

export function Footer() {
  return (
    <footer className="bg-[#040810] py-20 border-t border-white/5 relative z-10">
      <div className="max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-12 mb-16">
          <div className="col-span-2 lg:col-span-2">
            <Link href="/" className="flex items-center gap-2 mb-6">
              <div className="w-8 h-8 rounded-lg bg-brand-blue flex items-center justify-center font-bold text-white">
                {BRAND.mark}
              </div>
              <span className="text-xl font-bold text-white tracking-tight">
                {BRAND.name}
              </span>
            </Link>
            <p className="text-gray-400 mb-8 max-w-sm">
              The AI CRM Built for Modern Revenue Teams. Manage leads, accounts, and opportunities from one intelligent platform.
            </p>
            <div className="flex items-center gap-4">
              <Link href="#" className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center text-gray-400 hover:text-white hover:bg-white/10 transition-colors">
                <Twitter className="w-5 h-5" />
              </Link>
              <Link href="#" className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center text-gray-400 hover:text-white hover:bg-white/10 transition-colors">
                <Linkedin className="w-5 h-5" />
              </Link>
              <Link href="#" className="w-10 h-10 rounded-full bg-white/5 flex items-center justify-center text-gray-400 hover:text-white hover:bg-white/10 transition-colors">
                <Github className="w-5 h-5" />
              </Link>
            </div>
          </div>
          
          {Object.entries(footerLinks).map(([category, links]) => (
            <div key={category}>
              <h4 className="text-white font-semibold mb-6">{category}</h4>
              <ul className="space-y-4">
                {links.map((link) => (
                  <li key={link}>
                    <Link href="#" className="text-gray-400 hover:text-white transition-colors text-sm">
                      {link}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        
        <div className="pt-8 border-t border-white/5 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-gray-500 text-sm">
            © {new Date().getFullYear()} {BRAND.footer}
          </p>
          <div className="flex items-center gap-6 text-sm text-gray-500">
            <Link href="#" className="hover:text-white transition-colors">Privacy Policy</Link>
            <Link href="#" className="hover:text-white transition-colors">Terms of Service</Link>
            <Link href="#" className="hover:text-white transition-colors">Cookie Policy</Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
