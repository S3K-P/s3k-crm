import { daysFromToday } from '@/features/ai/shared/format';
import type { NbaRecord } from './types';

/* ============================================================
   NEXT BEST ACTION — FILTER DEFINITIONS
   Filter options and their predicates live beside the data so
   the toolbar stays presentational and the page stays thin.
   ============================================================ */

export interface NbaFilters {
  search: string;
  company: string;
  salesperson: string;
  priority: string;
  status: string;
  confidence: string;
  stage: string;
  followUp: string;
}

export const EMPTY_FILTERS: NbaFilters = {
  search: '',
  company: '',
  salesperson: '',
  priority: '',
  status: '',
  confidence: '',
  stage: '',
  followUp: '',
};

export const PRIORITY_OPTIONS = [
  { value: '', label: 'All Priorities' },
  { value: 'Critical', label: 'Critical' },
  { value: 'High', label: 'High' },
  { value: 'Medium', label: 'Medium' },
  { value: 'Low', label: 'Low' },
];

export const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'New', label: 'New' },
  { value: 'Pending', label: 'Pending' },
  { value: 'In Progress', label: 'In Progress' },
  { value: 'Scheduled', label: 'Scheduled' },
  { value: 'Completed', label: 'Completed' },
  { value: 'Dismissed', label: 'Dismissed' },
];

export const STAGE_OPTIONS = [
  { value: '', label: 'All Stages' },
  { value: 'Qualification', label: 'Qualification' },
  { value: 'Discovery', label: 'Discovery' },
  { value: 'Proposal', label: 'Proposal' },
  { value: 'Negotiation', label: 'Negotiation' },
  { value: 'Contract Review', label: 'Contract Review' },
  { value: 'Closed Won', label: 'Closed Won' },
];

export const CONFIDENCE_OPTIONS = [
  { value: '', label: 'All Confidence' },
  { value: '90', label: '90%+' },
  { value: '75', label: '75–89%' },
  { value: '50', label: '50–74%' },
  { value: '0', label: 'Below 50%' },
];

export const FOLLOW_UP_OPTIONS = [
  { value: '', label: 'Any Follow-up Date' },
  { value: 'overdue', label: 'Overdue' },
  { value: 'today', label: 'Due today' },
  { value: 'week', label: 'Next 7 days' },
  { value: 'month', label: 'Next 30 days' },
];

function matchesConfidence(value: number, bucket: string): boolean {
  switch (bucket) {
    case '90': return value >= 90;
    case '75': return value >= 75 && value < 90;
    case '50': return value >= 50 && value < 75;
    case '0': return value < 50;
    default: return true;
  }
}

function matchesFollowUp(iso: string, bucket: string): boolean {
  const delta = daysFromToday(iso);
  switch (bucket) {
    case 'overdue': return delta < 0;
    case 'today': return delta === 0;
    case 'week': return delta >= 0 && delta <= 7;
    case 'month': return delta >= 0 && delta <= 30;
    default: return true;
  }
}

function matchesSearch(record: NbaRecord, term: string): boolean {
  const haystack = [
    record.leadName,
    record.company,
    record.opportunity,
    record.assignedTo,
    record.recommendation,
    record.leadTitle,
    record.email,
    record.phone,
    record.industry,
  ]
    .join(' ')
    .toLowerCase();

  return haystack.includes(term);
}

/** Applies every active filter. Pure and cheap enough to run on each render. */
export function applyNbaFilters(records: NbaRecord[], filters: NbaFilters): NbaRecord[] {
  const term = filters.search.trim().toLowerCase();

  return records.filter(record => {
    if (term && !matchesSearch(record, term)) return false;
    if (filters.company && record.company !== filters.company) return false;
    if (filters.salesperson && record.assignedTo !== filters.salesperson) return false;
    if (filters.priority && record.priority !== filters.priority) return false;
    if (filters.status && record.status !== filters.status) return false;
    if (filters.stage && record.stage !== filters.stage) return false;
    if (filters.confidence && !matchesConfidence(record.confidence, filters.confidence)) return false;
    if (filters.followUp && !matchesFollowUp(record.nextFollowUp, filters.followUp)) return false;
    return true;
  });
}

export function countActiveFilters(filters: NbaFilters): number {
  return Object.values(filters).filter(value => value.trim().length > 0).length;
}

/** Builds Company / Salesperson dropdown options from the data itself. */
export function buildEntityOptions(records: NbaRecord[]) {
  const companies = [...new Set(records.map(record => record.company))].sort();
  const salespeople = [...new Set(records.map(record => record.assignedTo))].sort();

  return {
    companyOptions: [
      { value: '', label: 'All Companies' },
      ...companies.map(company => ({ value: company, label: company })),
    ],
    salespersonOptions: [
      { value: '', label: 'All Salespeople' },
      ...salespeople.map(person => ({ value: person, label: person })),
    ],
  };
}
