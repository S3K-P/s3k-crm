import { Metadata } from 'next';
import { LandingNavbar } from '@/components/landing/landing-navbar';
import { HeroSection } from '@/components/landing/hero-section';
import { TrustMetrics } from '@/components/landing/trust-metrics';
import { CrmWorkflowSection } from '@/components/landing/crm-workflow-section';
import { CrmFeaturesSection } from '@/components/landing/crm-features-section';
import { CrmUseCasesSection } from '@/components/landing/crm-use-cases-section';
import { VisibilitySection } from '@/components/landing/visibility-section';
import { FinalCtaSection } from '@/components/landing/final-cta-section';
import { LandingFooter } from '@/components/landing/landing-footer';

export const metadata: Metadata = {
  title: 'S3K CRM | Accounts, Opportunities and Sales Pipeline Management',
  description: 'Manage accounts, contacts, opportunities, activities, and sales pipeline visibility with S3K CRM.',
  openGraph: {
    title: 'S3K CRM | Accounts, Opportunities and Sales Pipeline Management',
    description: 'Manage accounts, contacts, opportunities, activities, and sales pipeline visibility with S3K CRM.',
    type: 'website',
  }
};

export default function Home() {
  return (
    <main className="min-h-screen bg-white font-sans selection:bg-brand-violet/20 selection:text-brand-violet">
      <LandingNavbar />
      <HeroSection />
      <TrustMetrics />
      <CrmWorkflowSection />
      <CrmFeaturesSection />
      <CrmUseCasesSection />
      <VisibilitySection />
      <FinalCtaSection />
      <LandingFooter />
    </main>
  );
}
