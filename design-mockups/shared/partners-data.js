/* ============================================================
   S3K CRM — shared mock Partner data (India-first).
   NOTE: the only existing Partner prototype lives OUTSIDE
   frontend/app/(crm) at repo-root app/(crm)/partners — a stale,
   unreachable parallel location (see 00_discovery.md addendum).
   Field shape below is adapted from that prototype's
   features/crm/partners/types.ts, reformatted to the currency-
   string convention the rest of frontend/app/(crm) uses, since
   that prototype used raw numbers inconsistently with every
   other module.
   ============================================================ */
var S3K_PARTNERS = [
  { id: 'p1', name: 'Nimbus Channel Partners', type: 'Channel Partner', status: 'Active', territory: 'West India', assignedManager: 'Priya Nair', linkedAccount: '', totalLeadsGenerated: 64, activeLeads: 12, qualifiedLeads: 28, convertedOpportunities: 9, wonDeals: 7, lostDeals: 2, totalPipelineValue: '₹1.4 Cr', revenueGenerated: '₹2.1 Cr', conversionRate: 14.1, averageDealSize: '₹30 L', lastLeadGeneratedAt: '2 days ago', lastActivityAt: '1 day ago' },
  { id: 'p2', name: 'Suryoday Alliance Group', type: 'Alliance Partner', status: 'Active', territory: 'South India', assignedManager: 'Rohan Mehta', linkedAccount: '', totalLeadsGenerated: 41, activeLeads: 8, qualifiedLeads: 19, convertedOpportunities: 6, wonDeals: 5, lostDeals: 1, totalPipelineValue: '₹85 L', revenueGenerated: '₹1.3 Cr', conversionRate: 14.6, averageDealSize: '₹26 L', lastLeadGeneratedAt: '5 hrs ago', lastActivityAt: '5 hrs ago' },
  { id: 'p3', name: 'Konkan Logistics', type: 'Referral Partner', status: 'Onboarding', territory: 'Kerala', assignedManager: 'Rohan Mehta', linkedAccount: 'Konkan Logistics', totalLeadsGenerated: 6, activeLeads: 4, qualifiedLeads: 2, convertedOpportunities: 0, wonDeals: 0, lostDeals: 0, totalPipelineValue: '₹18 L', revenueGenerated: '₹0', conversionRate: 0, averageDealSize: '₹0', lastLeadGeneratedAt: '1 week ago', lastActivityAt: '3 days ago' },
  { id: 'p4', name: 'Vajra Strategic Technologies', type: 'Strategic Partner', status: 'Active', territory: 'North India', assignedManager: 'Meera Pillai', linkedAccount: '', totalLeadsGenerated: 88, activeLeads: 15, qualifiedLeads: 35, convertedOpportunities: 12, wonDeals: 10, lostDeals: 2, totalPipelineValue: '₹2.2 Cr', revenueGenerated: '₹3.4 Cr', conversionRate: 13.6, averageDealSize: '₹34 L', lastLeadGeneratedAt: '12 hrs ago', lastActivityAt: '12 hrs ago' },
  { id: 'p5', name: 'Coastal Referral Network', type: 'Referral Partner', status: 'Pending', territory: 'East India', assignedManager: 'Priya Nair', linkedAccount: '', totalLeadsGenerated: 0, activeLeads: 0, qualifiedLeads: 0, convertedOpportunities: 0, wonDeals: 0, lostDeals: 0, totalPipelineValue: '₹0', revenueGenerated: '₹0', conversionRate: 0, averageDealSize: '₹0', lastLeadGeneratedAt: '—', lastActivityAt: '3 weeks ago' },
  { id: 'p6', name: 'Himalaya Dairy Pvt Ltd', type: 'Channel Partner', status: 'Inactive', territory: 'Maharashtra', assignedManager: 'Priya Nair', linkedAccount: 'Himalaya Dairy Pvt Ltd', totalLeadsGenerated: 11, activeLeads: 0, qualifiedLeads: 3, convertedOpportunities: 1, wonDeals: 1, lostDeals: 1, totalPipelineValue: '₹0', revenueGenerated: '₹22 L', conversionRate: 9.1, averageDealSize: '₹22 L', lastLeadGeneratedAt: '4 months ago', lastActivityAt: '3 months ago' }
];

var S3K_PARTNER_LEADS = [
  { id: 'pl1', partnerId: 'p1', leadName: 'Devika Shah', company: 'Trident Marine Exports', source: 'Nimbus Channel Partners', currentStage: 'Qualified', owner: 'Priya Nair', createdAt: '2026-10-09', status: 'Open' },
  { id: 'pl2', partnerId: 'p1', leadName: 'Farhan Shaikh', company: 'Orion Steel Works', source: 'Nimbus Channel Partners', currentStage: 'Proposal Sent', owner: 'Priya Nair', createdAt: '2026-10-02', status: 'Open' }
];
