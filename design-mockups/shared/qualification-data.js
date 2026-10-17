/* ============================================================
   S3K CRM — shared mock Qualification queue data (India-first).
   Mirrors model QualificationRecord in 05-CRM-PRISMA-SCHEMA.md
   (leadId→lead, framework BANT/MEDDICC/CHAMP, status UNQUALIFIED/
   IN_REVIEW/QUALIFIED/DISQUALIFIED, budget/authority/need/
   timeline, aiScore, recommendation, ownerId→owner, priority).
   This is a triage queue, not a CRUD list — there is no "create
   new qualification record" flow in the real app or the schema;
   records are generated against an existing Lead.
   ============================================================ */
var S3K_QUALIFICATION_QUEUE = [
  { id: 'q1', leadName: 'Ishaan Malhotra', company: 'Ashoka Build Infra Ltd', source: 'Channel Partner', status: 'Qualified', budget: 'Confirmed', authority: 'Confirmed', need: 'Confirmed', timeline: 'Confirmed', aiScore: 88, recommendation: 'Fast-track to Opportunity — all BANT criteria met.', owner: 'Rohan Mehta', createdDate: '2026-10-05', priority: 'High' },
  { id: 'q2', leadName: 'Varun Nair', company: 'Blue Ocean Seafoods Pvt Ltd', source: 'Webinar', status: 'In Review', budget: 'Pending', authority: 'Confirmed', need: 'Confirmed', timeline: 'Unknown', aiScore: 64, recommendation: 'Confirm budget range before moving to Proposal.', owner: 'Priya Nair', createdDate: '2026-09-20', priority: 'High' },
  { id: 'q3', leadName: 'Pooja Bhatt', company: 'Saffron Hospitality Group', source: 'Trade Show', status: 'In Review', budget: 'Unknown', authority: 'Pending', need: 'Confirmed', timeline: 'Pending', aiScore: 41, recommendation: 'Identify the economic buyer before continuing.', owner: 'Meera Pillai', createdDate: '2026-09-28', priority: 'Medium' },
  { id: 'q4', leadName: 'Neha Kapoor', company: 'Confluence Analytics Pvt Ltd', source: 'Company Website', status: 'Unqualified', budget: 'Unknown', authority: 'Unknown', need: 'Confirmed', timeline: 'Unknown', aiScore: 35, recommendation: 'Early stage — needs a discovery call first.', owner: 'Rohan Mehta', createdDate: '2026-10-12', priority: 'Medium' },
  { id: 'q5', leadName: 'Simran Kaur', company: 'Pinnacle Fintech', source: 'Cold Outreach', status: 'Disqualified', budget: 'No Budget', authority: 'Unknown', need: 'None', timeline: 'Unknown', aiScore: 12, recommendation: 'No budget this cycle — revisit in Q1.', owner: 'Rohan Mehta', createdDate: '2026-09-15', priority: 'Low' }
];
