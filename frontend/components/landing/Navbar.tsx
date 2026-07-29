'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { BRAND } from '@/config/site';

export function Navbar() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setScrolled(window.scrollY > 20);
    };
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled ? 'bg-navy-900/80 backdrop-blur-md border-b border-white/10' : 'bg-transparent'
      }`}
    >
      <div className="max-w-7xl mx-auto px-6 h-20 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <div className="font-display flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-violet-600 to-indigo-500 text-[11px] font-extrabold tracking-tight text-white shadow-md">
            {BRAND.mark}
          </div>
          <span className="text-xl font-bold text-white tracking-tight">
            {BRAND.name}
          </span>
        </Link>

        <div className="hidden md:flex items-center gap-8 text-sm font-medium text-gray-300">
          <Link href="#features" className="hover:text-white transition-colors">Features</Link>
          <Link href="#modules" className="hover:text-white transition-colors">Modules</Link>
          <Link href="#ai" className="hover:text-white transition-colors">AI</Link>
          <Link href="#pricing" className="hover:text-white transition-colors">Pricing</Link>
          <Link href="#contact" className="hover:text-white transition-colors">Contact</Link>
        </div>

        <Link
          href={BRAND.homeHref}
          className="bg-brand-blue hover:bg-brand-indigo transition-colors text-white px-5 py-2.5 rounded-xl font-medium text-sm shadow-[0_0_15px_rgba(79,126,255,0.4)]"
        >
          Launch CRM
        </Link>
      </div>
    </nav>
  );
}
