'use client';

import { Shield, Check, X } from 'lucide-react';

const MODULES = ['Dashboard', 'Leads', 'Accounts', 'Contacts', 'Opportunities', 'Meetings', 'Campaigns', 'Qualification', 'AI Features', 'Reports', 'Admin'];
const ROLES = ['Admin', 'Sales Manager', 'Sales Rep', 'Marketing', 'Support'];

export default function AdminRolesPage() {
  // Mock complex matrix UI
  return (
    <div className="flex h-full flex-col space-y-6 p-6 lg:p-8 max-w-7xl mx-auto">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3.5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-[12px] bg-gradient-to-br from-amber-500 to-orange-600">
            <Shield className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="font-display text-[22px] font-extrabold txt">Roles & Permissions</h1>
            <p className="txt-muted mt-0.5 text-[13px]">Configure access levels across CRM modules.</p>
          </div>
        </div>
        <div className="flex gap-2">
          <button className="flex items-center gap-2 rounded-lg px-4 py-2 text-[13px] font-semibold text-white transition hover:opacity-90" style={{ background: 'var(--accent)' }}>
            Create New Role
          </button>
        </div>
      </div>

      <div className="surface bd rounded-2xl border overflow-x-auto">
        <table className="w-full text-left text-[12.5px]">
          <thead className="bg-[var(--surface-2)] border-b border-[var(--border)]">
            <tr>
              <th className="px-5 py-4 font-bold txt-muted uppercase tracking-wider text-[11px] min-w-[150px]">Module</th>
              {ROLES.map(role => (
                <th key={role} className="px-5 py-4 font-bold txt uppercase tracking-wider text-[11px] text-center min-w-[150px]">{role}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border)]">
            {MODULES.map(mod => (
              <tr key={mod} className="hover:bg-[var(--surface-2)] transition-colors">
                <td className="px-5 py-4 font-semibold txt">{mod}</td>
                {ROLES.map(role => {
                  const isAdmin = role === 'Admin';
                  const isSalesRep = role === 'Sales Rep';
                  
                  // Mock logic for permissions
                  let p = 'V/C/E/D';
                  if (mod === 'Admin' && !isAdmin) p = 'None';
                  if (mod === 'Campaigns' && isSalesRep) p = 'V';
                  
                  return (
                    <td key={role} className="px-5 py-4 text-center">
                      {p === 'None' ? (
                         <div className="inline-flex items-center justify-center h-6 px-2 rounded bg-rose-500/10 text-rose-500 font-medium text-[11px]">No Access</div>
                      ) : (
                         <div className="inline-flex gap-1">
                           <div className="h-6 w-6 rounded bg-[var(--surface)] border border-[var(--border)] flex items-center justify-center txt-muted" title="View"><span className="text-[10px] font-bold">V</span></div>
                           <div className="h-6 w-6 rounded bg-[var(--surface)] border border-[var(--border)] flex items-center justify-center txt-muted" title="Create"><span className="text-[10px] font-bold">C</span></div>
                           <div className="h-6 w-6 rounded bg-[var(--surface)] border border-[var(--border)] flex items-center justify-center txt-muted" title="Edit"><span className="text-[10px] font-bold">E</span></div>
                           {p === 'V' ? (
                             <div className="h-6 w-6 rounded bg-rose-500/10 flex items-center justify-center text-rose-500" title="Delete Denied"><X className="h-3 w-3" /></div>
                           ) : (
                             <div className="h-6 w-6 rounded bg-[var(--surface)] border border-[var(--border)] flex items-center justify-center txt-muted" title="Delete"><span className="text-[10px] font-bold">D</span></div>
                           )}
                         </div>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
