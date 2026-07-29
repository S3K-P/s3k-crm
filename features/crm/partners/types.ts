export type PartnerStatus = 'Active' | 'Pending' | 'Onboarding' | 'Inactive';
export type PartnerType = 'Channel Partner' | 'Alliance Partner' | 'Referral Partner' | 'Strategic Partner';

export interface Partner {
  id: string;
  name: string;
  type: PartnerType;
  status: PartnerStatus;
  
  // Basic Info
  company: string;
  website: string;
  territory: string;
  assignedManagerId: string;
  createdAt: string;
  
  // Links
  linkedAccountId: string;
  primaryContactId: string;

  // Funnel Metrics
  totalLeadsGenerated: number;
  activeLeads: number;
  qualifiedLeads: number;
  convertedOpportunities: number;
  wonDeals: number;
  lostDeals: number;
  totalPipelineValue: number;
  revenueGenerated: number;
  conversionRate: number; // Percentage 0-100
  averageDealSize: number;
  
  lastLeadGeneratedAt: string;
  lastActivityAt: string;
}

export interface PartnerLead {
  id: string;
  partnerId: string;
  leadName: string;
  company: string;
  source: string;
  currentStage: string;
  ownerId: string;
  createdAt: string;
  status: string;
  opportunityId?: string;
}
