'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { BRAND } from '@/config/site';
import BrandLogo from '@/components/brand/BrandLogo';

export function LandingNavbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 10);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? 'bg-white/90 backdrop-blur-md border-b border-gray-200 shadow-sm' : 'bg-white'
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
        {/* Left: Brand */}
        <Link href="/" className="flex items-center gap-2">
          <BrandLogo priority />
          <div className="flex flex-col">
            <span className="text-lg font-bold text-gray-900 leading-none tracking-tight">
              {BRAND.name}
            </span>
            <span className="text-[10px] uppercase font-semibold text-brand-violet mt-0.5 tracking-wider">
              Enterprise CRM
            </span>
          </div>
        </Link>

        {/* Center: Navigation */}
        <div className="hidden md:flex items-center gap-8 text-sm font-medium text-gray-600">
          <Link href="#features" className="hover:text-brand-violet transition-colors">Features</Link>
          <Link href="#how-it-works" className="hover:text-brand-violet transition-colors">How It Works</Link>
          <Link href="#solutions" className="hover:text-brand-violet transition-colors">Solutions</Link>
          <Link href="/dashboard" className="hover:text-brand-violet transition-colors">Dashboard</Link>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="hidden md:block text-sm font-medium text-gray-600 hover:text-brand-violet transition-colors">
            Sign In
          </Link>
          <Link
            href="/dashboard"
            className="bg-brand-violet hover:bg-brand-purple transition-colors text-white px-5 py-2.5 rounded-xl font-medium text-sm shadow-sm"
          >
            Launch CRM
          </Link>
        </div>
      </div>
    </nav>
  );
}
