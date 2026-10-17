/* ============================================================
   S3K CRM — shared app shell renderer (sidebar + topbar + breadcrumb).
   Mirrors frontend/config/crm-navigation.ts exactly so every mockup
   shows the SAME real navigation (no invented Salesforce modules).
   Builds the shell once from data, so all mockup pages stay in sync.
   ============================================================ */
(function () {
  'use strict';
  var S3K = window.S3K = window.S3K || {};

  var ICON = {
    dashboard: '<path d="M3 3h7v9H3z"/><path d="M14 3h7v5h-7z"/><path d="M14 12h7v9h-7z"/><path d="M3 16h7v5H3z"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20z"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
    handshake: '<path d="m11 17 2 2a1 1 0 1 0 3-3"/><path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"/><path d="m21 3 1 11h-2"/><path d="M3 4h8"/><path d="m7 18-1.5-1.5"/><path d="M3 15h2.5l2 2"/>',
    megaphone: '<path d="m3 11 18-5v12L3 14v-3z"/><path d="M11.6 16.8a3 3 0 1 1-5.8-1.6"/>',
    calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    building: '<rect x="4" y="2" width="16" height="20" rx="1"/><path d="M9 22v-4h6v4M9 6h.01M9 10h.01M9 14h.01M15 6h.01M15 10h.01M15 14h.01"/>',
    contact: '<path d="M16 2v3M8 2v3"/><rect x="3" y="5" width="18" height="16" rx="2"/><circle cx="12" cy="12" r="3"/><path d="M7 18a5 5 0 0 1 10 0"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    'check-circle': '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    'clipboard-check': '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/><path d="m9 16 2 2 4-4"/>',
    brain: '<path d="M12 5a3 3 0 1 0-5.99.08A2.5 2.5 0 0 0 4 7.5 2.5 2.5 0 0 0 5.5 12a2.5 2.5 0 0 0-1 4.73A2.5 2.5 0 0 0 7 20.5a3 3 0 0 0 5-2.5"/><path d="M12 5a3 3 0 1 1 5.99.08A2.5 2.5 0 0 1 20 7.5 2.5 2.5 0 0 1 18.5 12a2.5 2.5 0 0 1 1 4.73A2.5 2.5 0 0 1 17 20.5a3 3 0 0 1-5-2.5V5z"/>',
    zap: '<path d="M13 2 3 14h8l-1 8 10-12h-8l1-8z"/>',
    shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    sparkles: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M18.4 5.6l-2.8 2.8M8.4 15.6l-2.8 2.8"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    plus: '<path d="M5 12h14M12 5v14"/>',
    'chevron-down': '<path d="m6 9 6 6 6-6"/>',
    'chevron-left': '<path d="m15 18-6-6 6-6"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
    'panel-left-close': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 10l-2 2 2 2"/>',
    'panel-left': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>'
  };
  function icon(name, cls) {
    return '<svg class="' + (cls || '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + (ICON[name] || '') + '</svg>';
  }
  S3K.icon = icon;

  var NAV = [
    { title: 'Overview', items: [
      { id: 'dashboard', label: 'Dashboard', href: '01_dashboard.html', icon: 'dashboard' }
    ]},
    { title: 'Pipeline', items: [
      { id: 'lead-sources', label: 'Lead Sources', href: '11_lead_sources.html', icon: 'globe' },
      { id: 'leads', label: 'Leads', href: '09_leads.html', icon: 'users' },
      { id: 'campaigns', label: 'Campaigns', href: '12_campaigns.html', icon: 'megaphone' },
      { id: 'meetings', label: 'Meetings', href: '14_meetings.html', icon: 'calendar' },
      { id: 'tasks', label: 'Tasks', href: '16_tasks.html', icon: 'clipboard-check' }
    ]},
    { title: 'Relationships', items: [
      { id: 'accounts', label: 'Accounts', href: '05_accounts.html', icon: 'building' },
      { id: 'contacts', label: 'Contacts', href: '02_contacts_list.html', icon: 'contact' },
      { id: 'opportunities', label: 'Opportunities', href: '07_opportunities.html', icon: 'target' },
      { id: 'qualification', label: 'Qualification', href: '17_qualification.html', icon: 'check-circle' }
    ]},
    { title: 'AI', items: [
      { id: 'ai-insights', label: 'AI Insights', href: '#', icon: 'brain' },
      { id: 'ai-nba', label: 'Next Best Action', href: '#', icon: 'zap' }
    ]},
    { title: 'System', items: [
      { id: 'admin', label: 'Admin', href: '#', icon: 'shield' },
      { id: 'ai-settings', label: 'AI Settings', href: '#', icon: 'sparkles' }
    ]}
  ];

  var SEARCH_ITEMS = [].concat.apply([], NAV.map(function (s) { return s.items; }));

  S3K.mountShell = function (opts) {
    opts = opts || {};
    var shell = document.getElementById('app-shell');
    if (!shell) return;
    var active = opts.active || '';
    var breadcrumb = opts.breadcrumb || [];

    // Mobile backdrop
    var backdrop = document.createElement('div');
    backdrop.className = 'mobile-backdrop';
    backdrop.setAttribute('data-mobile-backdrop', '');
    shell.insertBefore(backdrop, shell.firstChild);

    // Sidebar
    var sectionsHtml = NAV.map(function (section) {
      var itemsHtml = section.items.map(function (item) {
        var isActive = item.id === active;
        return '<a class="nav-item' + (isActive ? ' is-active' : '') + '" href="' + item.href + '"' + (item.href === '#' ? ' title="Not built yet — real nav does not route here" aria-disabled="true"' : '') + '>' +
          icon(item.icon) + '<span class="nav-item-label">' + item.label + '</span></a>';
      }).join('');
      return '<div class="sidebar-section"><div class="sidebar-section-title">' + section.title + '</div>' + itemsHtml + '</div>';
    }).join('');

    var sidebar = document.createElement('aside');
    sidebar.className = 'app-sidebar';
    sidebar.innerHTML =
      '<div class="sidebar-brand">' +
        '<div class="sidebar-mark">S3K</div>' +
        '<div class="sidebar-brand-text"><div class="sidebar-brand-name">S3K CRM</div><div class="sidebar-brand-tag">AI-First Enterprise CRM</div></div>' +
        '<button class="icon-btn" style="margin-left:auto;background:transparent;border-color:#2a2347;color:#b3a8d1;display:none;" data-action="close-mobile-nav" aria-label="Close menu">' + icon('x') + '</button>' +
      '</div>' +
      '<nav class="sidebar-nav">' + sectionsHtml + '</nav>' +
      '<div class="sidebar-footer"><button class="sidebar-collapse-btn" data-action="toggle-sidebar">' + icon('panel-left-close') + '<span class="collapse-label">Collapse</span></button></div>';
    shell.insertBefore(sidebar, shell.children[1]);

    // Mobile close button only shown < 860px — simplest: always present, hidden by CSS unless mobile nav open
    var closeBtn = sidebar.querySelector('[data-action="close-mobile-nav"]');
    var mq = window.matchMedia('(max-width: 860px)');
    function syncCloseBtn() { closeBtn.style.display = mq.matches ? 'inline-flex' : 'none'; }
    syncCloseBtn();
    mq.addEventListener ? mq.addEventListener('change', syncCloseBtn) : mq.addListener(syncCloseBtn);

    // Topbar + breadcrumb, prepended into .app-main-col (before the existing <main id="page-content">)
    var mainCol = shell.querySelector('.app-main-col');
    var pageContent = document.getElementById('page-content');

    var topbar = document.createElement('header');
    topbar.className = 'app-topbar';
    topbar.innerHTML =
      '<button class="icon-btn topbar-mobile-btn" data-action="open-mobile-nav" aria-label="Open menu">' + icon('menu') + '</button>' +
      '<button class="search-trigger" data-open="#search-modal" aria-label="Search">' + icon('search') + '<span>Search CRM…</span><span class="kbd">⌘K</span></button>' +
      (opts.quickCreate !== false ? '<div style="position:relative;">' +
        '<button class="btn btn-primary btn-sm quick-create-btn" data-menu-trigger="#quick-create-menu">' + icon('plus') + 'New</button>' +
        '<div class="menu" id="quick-create-menu" style="right:0;left:auto;top:calc(100% + 6px);">' +
          '<button class="menu-item">' + icon('contact') + 'New Contact</button>' +
          '<button class="menu-item">' + icon('building') + 'New Account</button>' +
          '<button class="menu-item">' + icon('target') + 'New Opportunity</button>' +
          '<button class="menu-item">' + icon('users') + 'New Lead</button>' +
        '</div></div>' : '') +
      '<div class="topbar-right">' +
        '<button class="icon-btn" data-action="toggle-theme" aria-label="Toggle dark mode">' + icon('sun', '').replace('<svg ', '<svg data-theme-icon="sun" ') + icon('moon', '').replace('<svg ', '<svg data-theme-icon="moon" ') + '</button>' +
        '<button class="icon-btn" aria-label="Notifications">' + icon('bell') + '<span class="dot"></span></button>' +
        '<div class="avatar avatar-sm" title="Rohan Mehta — Sales Manager">RM</div>' +
      '</div>';
    mainCol.insertBefore(topbar, pageContent);

    if (breadcrumb.length) {
      var bc = document.createElement('div');
      bc.className = 'app-breadcrumb';
      bc.innerHTML = breadcrumb.map(function (b, i) {
        var isLast = i === breadcrumb.length - 1;
        return (i > 0 ? '<span aria-hidden="true" style="opacity:.6;">&rsaquo;</span>' : '') + '<span' + (isLast ? ' class="current"' : '') + '>' + b + '</span>';
      }).join('');
      mainCol.insertBefore(bc, pageContent);
    }

    // Search modal + toast stack appended to body once
    if (!document.getElementById('search-modal')) {
      var sm = document.createElement('div');
      sm.className = 'modal-backdrop';
      sm.id = 'search-modal';
      sm.style.alignItems = 'flex-start';
      sm.innerHTML =
        '<div class="search-modal">' +
          '<div class="search-modal-input-row">' + icon('search') + '<input type="text" placeholder="Search CRM pages…" autofocus>' +
          '<span class="kbd" style="border:1px solid var(--border);border-radius:4px;padding:1px 6px;font-size:10px;font-weight:700;color:var(--faint);">ESC</span></div>' +
          '<div class="search-modal-results">' + SEARCH_ITEMS.map(function (it) {
            return '<a class="search-result-item" href="' + it.href + '" style="text-decoration:none;color:var(--text);">' + icon(it.icon) + '<span style="font-size:13px;font-weight:500;">' + it.label + '</span></a>';
          }).join('') + '</div>' +
        '</div>';
      document.body.appendChild(sm);
    }
    if (!document.querySelector('.toast-stack')) {
      var ts = document.createElement('div');
      ts.className = 'toast-stack';
      document.body.appendChild(ts);
    }
  };
})();
