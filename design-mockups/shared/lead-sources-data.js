/* ============================================================
   S3K CRM — shared mock Lead Source data.
   Mirrors model LeadSource in 05-CRM-PRISMA-SCHEMA.md
   (name, category, description, status). leadsGenerated/
   leadsConverted mirror the existing frontend mock
   (frontend/app/(crm)/lead-sources/page.tsx) as computed display
   fields, not raw schema columns.
   ============================================================ */
var S3K_LEAD_SOURCES = [
  { id: 'ls1', name: 'Company Website', category: 'Digital', description: 'Inbound form submissions from the public website.', leadsGenerated: 312, leadsConverted: 48, status: 'Active', createdBy: 'Rohan Mehta', lastUpdated: '2 days ago' },
  { id: 'ls2', name: 'LinkedIn', category: 'Social Media', description: 'Organic and paid LinkedIn campaigns.', leadsGenerated: 198, leadsConverted: 31, status: 'Active', createdBy: 'Priya Nair', lastUpdated: '1 week ago' },
  { id: 'ls3', name: 'Channel Partner', category: 'Partnership', description: 'Leads referred by reseller and alliance partners.', leadsGenerated: 86, leadsConverted: 22, status: 'Active', createdBy: 'Meera Pillai', lastUpdated: '3 days ago' },
  { id: 'ls4', name: 'Employee Referral', category: 'Internal', description: 'Leads referred by current employees.', leadsGenerated: 44, leadsConverted: 19, status: 'Active', createdBy: 'Rohan Mehta', lastUpdated: '5 days ago' },
  { id: 'ls5', name: 'Webinar', category: 'Marketing', description: 'Attendees from S3K-hosted product webinars.', leadsGenerated: 127, leadsConverted: 15, status: 'Active', createdBy: 'Priya Nair', lastUpdated: '1 day ago' },
  { id: 'ls6', name: 'Cold Outreach', category: 'Outbound', description: 'SDR-initiated cold calling and email sequences.', leadsGenerated: 265, leadsConverted: 12, status: 'Active', createdBy: 'Meera Pillai', lastUpdated: '4 days ago' },
  { id: 'ls7', name: 'Trade Show', category: 'Events', description: 'In-person leads captured at industry exhibitions.', leadsGenerated: 73, leadsConverted: 14, status: 'Inactive', createdBy: 'Rohan Mehta', lastUpdated: '2 months ago' }
];
