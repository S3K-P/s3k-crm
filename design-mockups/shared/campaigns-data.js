/* ============================================================
   S3K CRM — shared mock Campaign data (India-first).
   Mirrors model Campaign in 05-CRM-PRISMA-SCHEMA.md (name, type,
   status, ownerId→owner, startDate, endDate, budget,
   expectedRevenue, targetAudience, leadSourceId→leadSource,
   products, notes, leadsGenerated, opportunitiesGenerated,
   conversionRate, roi — the last four are the schema's own
   "computed/cached metrics" fields, shown read-only).
   ============================================================ */
var S3K_CAMPAIGNS = [
  { id: 'c1', name: 'Diwali Enterprise Offer 2026', type: 'Email', status: 'Active', owner: 'Priya Nair', startDate: '2026-10-01', endDate: '2026-11-10', budget: '₹8,00,000', expectedRevenue: '₹60,00,000', targetAudience: 'Existing mid-market accounts', leadSource: 'Email Campaign', products: 'CRM Enterprise Bundle', notes: 'Festive-season upgrade push for accounts past 1-year mark.', leadsGenerated: 86, opportunitiesGenerated: 14, conversionRate: 16.3, roi: '340%', progress: 55 },
  { id: 'c2', name: 'Bengaluru Tech Summit Booth', type: 'Event', status: 'Planning', owner: 'Rohan Mehta', startDate: '2026-11-18', endDate: '2026-11-20', budget: '₹12,00,000', expectedRevenue: '₹90,00,000', targetAudience: 'Enterprise IT decision makers', leadSource: 'Trade Show', products: 'Full Platform Demo', notes: 'Booth + 2 speaking slots confirmed.', leadsGenerated: 0, opportunitiesGenerated: 0, conversionRate: 0, roi: '0%', progress: 10 },
  { id: 'c3', name: 'SaaS for Manufacturing Webinar', type: 'Webinar', status: 'Completed', owner: 'Meera Pillai', startDate: '2026-08-05', endDate: '2026-08-05', budget: '₹1,50,000', expectedRevenue: '₹25,00,000', targetAudience: 'Manufacturing sector leads', leadSource: 'Webinar', products: 'Field Service Module', notes: '212 registrants, 127 attended live.', leadsGenerated: 127, opportunitiesGenerated: 9, conversionRate: 7.1, roi: '890%', progress: 100 },
  { id: 'c4', name: 'LinkedIn ABM — Logistics Vertical', type: 'Social Media', status: 'Active', owner: 'Rohan Mehta', startDate: '2026-09-15', endDate: '2026-12-15', budget: '₹5,50,000', expectedRevenue: '₹40,00,000', targetAudience: 'Logistics & supply-chain accounts', leadSource: 'LinkedIn', products: 'Fleet Management Suite', notes: 'Account-based targeting against 40 named accounts.', leadsGenerated: 52, opportunitiesGenerated: 6, conversionRate: 11.5, roi: '210%', progress: 60 },
  { id: 'c5', name: 'Google Ads — Festive CRM Search', type: 'Advertisement', status: 'Paused', owner: 'Priya Nair', startDate: '2026-10-01', endDate: '2026-10-31', budget: '₹3,00,000', expectedRevenue: '₹18,00,000', targetAudience: 'Inbound search traffic', leadSource: 'Google Ads', products: 'CRM Mid-Market Bundle', notes: 'Paused after budget cap reached early.', leadsGenerated: 94, opportunitiesGenerated: 7, conversionRate: 7.4, roi: '150%', progress: 40 },
  { id: 'c6', name: 'Q4 Customer Referral Drive', type: 'Email', status: 'Cancelled', owner: 'Meera Pillai', startDate: '2026-10-05', endDate: '2026-10-20', budget: '₹1,00,000', expectedRevenue: '₹10,00,000', targetAudience: 'Existing champions', leadSource: 'Employee Referral', products: 'All products', notes: 'Cancelled — folded into the Diwali campaign instead.', leadsGenerated: 3, opportunitiesGenerated: 0, conversionRate: 0, roi: '0%', progress: 15 }
];
