/* ============================================================
   S3K CRM — shared mock Task data (India-first).
   Mirrors model Task in 05-CRM-PRISMA-SCHEMA.md (title,
   description, status, priority, dueDate, assignedToId→
   assignedTo, relatedEntityType/relatedEntityId→relatedTo).
   NOTE: there is no dedicated /tasks route in the real frontend
   today (only a dashboard TaskCard) — see REVIEW.md. This module
   is net-new, built from the backend's planned Task model.
   ============================================================ */
var S3K_TASKS = [
  { id: 't1', title: 'Call Rohan Mehta — renewal discussion', description: 'Discuss renewal pricing for Zenith Software before month-end.', status: 'Pending', priority: 'High', dueDate: '2026-10-14', assignedTo: 'Rohan Mehta', relatedTo: 'Zenith Software Solutions' },
  { id: 't2', title: 'Send proposal to Zenith Software', description: 'Finalize and send the Enterprise Expansion proposal.', status: 'In Progress', priority: 'High', dueDate: '2026-10-14', assignedTo: 'Rohan Mehta', relatedTo: 'Zenith Software — Enterprise Expansion' },
  { id: 't3', title: 'Follow up: Himalaya Dairy PO', description: 'Check on purchase order status with procurement.', status: 'Pending', priority: 'Medium', dueDate: '2026-10-14', assignedTo: 'Priya Nair', relatedTo: 'Himalaya Dairy Pvt Ltd' },
  { id: 't4', title: 'Review Q3 pipeline forecast', description: 'Validate numbers with the sales team before the leadership sync.', status: 'Pending', priority: 'Medium', dueDate: '2026-10-14', assignedTo: 'Meera Pillai', relatedTo: '' },
  { id: 't5', title: 'Send NDA to Bharat Textiles', description: 'Legal approved — ready for signature.', status: 'Completed', priority: 'Low', dueDate: '2026-10-10', assignedTo: 'Meera Pillai', relatedTo: 'Bharat Textiles Pvt Ltd' },
  { id: 't6', title: 'Prepare demo script for Confluence Analytics', description: 'Tailor the analytics-vertical demo for the discovery call.', status: 'Overdue', priority: 'High', dueDate: '2026-10-11', assignedTo: 'Rohan Mehta', relatedTo: 'Confluence Analytics Pvt Ltd' }
];
