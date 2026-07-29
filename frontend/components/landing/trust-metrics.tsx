'use client';

export function TrustMetrics() {
  const metrics = [
    { value: '360°', label: 'Customer View', sub: 'Complete relationship context' },
    { value: '4', label: 'Core CRM Modules', sub: 'Accounts, Contacts, Deals, Activity' },
    { value: '100%', label: 'Pipeline Visibility', sub: 'No blind spots in your forecast' },
    { value: '0', label: 'Missed Follow-ups', sub: 'Actionable next steps tracked' },
  ];

  return (
    <section className="bg-white pt-16 pb-12 relative z-20 -mt-8 rounded-t-[40px] shadow-[0_-20px_40px_rgba(0,0,0,0.1)]">
      <div className="max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-8 divide-x divide-gray-100">
          {metrics.map((metric, i) => (
            <div key={i} className="text-center px-4">
              <div className="text-4xl md:text-5xl font-bold text-navy-900 mb-2 tracking-tight">
                {metric.value}
              </div>
              <div className="text-sm font-semibold text-gray-900 mb-1">
                {metric.label}
              </div>
              <div className="text-xs text-gray-500 hidden sm:block">
                {metric.sub}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
