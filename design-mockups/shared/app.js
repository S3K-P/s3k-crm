/* ============================================================
   S3K CRM — shared mockup interactivity helpers.
   Small vanilla JS only, for demo purposes (no external libs).
   ============================================================ */
(function () {
  'use strict';

  var S3K = window.S3K = window.S3K || {};

  /* ---- Theme (light/dark), mirrors ThemeContext's pre-paint pattern ---- */
  function getStoredTheme() {
    try { return localStorage.getItem('s3k-mockup-theme'); } catch (e) { return null; }
  }
  function setStoredTheme(v) {
    try { localStorage.setItem('s3k-mockup-theme', v); } catch (e) { /* noop */ }
  }
  S3K.initTheme = function () {
    var stored = getStoredTheme();
    if (stored === 'dark' || stored === 'light') {
      document.documentElement.setAttribute('data-theme', stored);
    }
    updateThemeToggleIcons();
  };
  S3K.toggleTheme = function () {
    var current = document.documentElement.getAttribute('data-theme');
    var isDark = current === 'dark' || (!current && window.matchMedia('(prefers-color-scheme: dark)').matches);
    var next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    setStoredTheme(next);
    updateThemeToggleIcons();
  };
  function updateThemeToggleIcons() {
    var current = document.documentElement.getAttribute('data-theme');
    var isDark = current === 'dark' || (!current && window.matchMedia('(prefers-color-scheme: dark)').matches);
    document.querySelectorAll('[data-theme-icon="sun"]').forEach(function (el) { el.style.display = isDark ? '' : 'none'; });
    document.querySelectorAll('[data-theme-icon="moon"]').forEach(function (el) { el.style.display = isDark ? 'none' : ''; });
  }

  /* ---- Sidebar collapse (desktop) + mobile drawer ---- */
  S3K.initSidebar = function () {
    var shell = document.querySelector('[data-shell]');
    if (!shell) return;
    var collapseBtn = document.querySelector('[data-action="toggle-sidebar"]');
    var mobileOpenBtn = document.querySelector('[data-action="open-mobile-nav"]');
    var mobileCloseBtn = document.querySelector('[data-action="close-mobile-nav"]');
    var backdrop = document.querySelector('[data-mobile-backdrop]');

    if (collapseBtn) {
      collapseBtn.addEventListener('click', function () {
        shell.classList.toggle('sidebar-collapsed');
      });
    }
    function openMobile() { shell.classList.add('mobile-nav-open'); }
    function closeMobile() { shell.classList.remove('mobile-nav-open'); }
    if (mobileOpenBtn) mobileOpenBtn.addEventListener('click', openMobile);
    if (mobileCloseBtn) mobileCloseBtn.addEventListener('click', closeMobile);
    if (backdrop) backdrop.addEventListener('click', closeMobile);
  };

  /* ---- Tabs ----
     Supports two markups:
     1) A single [data-tabs] wrapper containing both [data-tab] buttons
        and [data-tab-panel] panels.
     2) Two sibling [data-tabs] elements under a common parent — one
        holding the buttons, the other the panels (the pattern used by
        every detail-page tab strip in this project). In that case each
        button's closest [data-tabs] ancestor's PARENT is used as the
        scope, so buttons and panels outside that one wrapper still find
        each other.
  */
  S3K.initTabs = function () {
    document.querySelectorAll('[data-tab]').forEach(function (btn) {
      if (btn._tabWired) return;
      btn._tabWired = true;
      btn.addEventListener('click', function () {
        var target = btn.getAttribute('data-tab');
        var ownWrap = btn.closest('[data-tabs]');
        var scope = ownWrap && ownWrap.querySelector('[data-tab-panel]') ? ownWrap : (ownWrap ? ownWrap.parentElement : document);
        scope.querySelectorAll('[data-tab]').forEach(function (b) { b.classList.toggle('is-active', b === btn); });
        scope.querySelectorAll('[data-tab-panel]').forEach(function (panel) {
          panel.classList.toggle('is-active', panel.getAttribute('data-tab-panel') === target);
        });
      });
    });
  };

  /* ---- Generic open/close for modals, menus, drawers via data-attributes ----
     data-open="#id"  -> adds is-open to #id
     data-close="#id" -> removes is-open from #id (or closest [data-closable] if no selector)
  */
  S3K.initOverlays = function () {
    document.addEventListener('click', function (e) {
      var openTrigger = e.target.closest('[data-open]');
      if (openTrigger) {
        var sel = openTrigger.getAttribute('data-open');
        var el = document.querySelector(sel);
        if (el) {
          el.classList.add('is-open');
          document.dispatchEvent(new CustomEvent('s3k:opened', { detail: { el: el } }));
        }
      }
      var closeTrigger = e.target.closest('[data-close]');
      if (closeTrigger) {
        var csel = closeTrigger.getAttribute('data-close');
        if (csel) {
          var cel = document.querySelector(csel);
          if (cel) cel.classList.remove('is-open');
        } else {
          var host = closeTrigger.closest('.is-open');
          if (host) host.classList.remove('is-open');
        }
      }
      // Close dropdown menus when clicking outside
      if (!e.target.closest('[data-menu-trigger]') && !e.target.closest('.menu')) {
        document.querySelectorAll('.menu.is-open').forEach(function (m) { m.classList.remove('is-open'); });
      }
    });

    // Menu triggers toggle their adjacent .menu
    document.addEventListener('click', function (e) {
      var trigger = e.target.closest('[data-menu-trigger]');
      if (!trigger) return;
      var sel = trigger.getAttribute('data-menu-trigger');
      var menu = sel ? document.querySelector(sel) : trigger.parentElement.querySelector('.menu');
      if (!menu) return;
      var willOpen = !menu.classList.contains('is-open');
      document.querySelectorAll('.menu.is-open').forEach(function (m) { m.classList.remove('is-open'); });
      if (willOpen) menu.classList.add('is-open');
    });

    // Escape closes topmost modal
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        var openModals = document.querySelectorAll('.modal-backdrop.is-open');
        if (openModals.length) openModals[openModals.length - 1].classList.remove('is-open');
      }
    });

    // Clicking a modal backdrop (not its modal card) closes it
    document.querySelectorAll('.modal-backdrop').forEach(function (bd) {
      bd.addEventListener('click', function (e) {
        if (e.target === bd) bd.classList.remove('is-open');
      });
    });
  };

  /* ---- Toggle switches: [role=switch].toggle ---- */
  S3K.initToggles = function () {
    document.querySelectorAll('.toggle').forEach(function (t) {
      t.addEventListener('click', function () {
        var on = t.getAttribute('aria-checked') === 'true';
        t.setAttribute('aria-checked', String(!on));
        var evt = t.getAttribute('data-on-toggle');
        if (evt && window.S3K.toggleHandlers && window.S3K.toggleHandlers[evt]) {
          window.S3K.toggleHandlers[evt](!on);
        }
      });
    });
  };

  /* ---- Toast ---- */
  S3K.toast = function (message, variant) {
    variant = variant || 'success';
    var stack = document.querySelector('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      document.body.appendChild(stack);
    }
    var icons = {
      success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--success)"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
      info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--info)"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
    };
    var el = document.createElement('div');
    el.className = 'toast';
    el.innerHTML = (icons[variant] || icons.success) + '<span class="txt" style="font-size:13px;font-weight:500;">' + message + '</span>';
    stack.appendChild(el);
    setTimeout(function () {
      el.style.transition = 'opacity .2s ease';
      el.style.opacity = '0';
      setTimeout(function () { el.remove(); }, 200);
    }, 3200);
  };

  /* ---- Boot ---- */
  document.addEventListener('DOMContentLoaded', function () {
    S3K.initTheme();
    S3K.initSidebar();
    S3K.initTabs();
    S3K.initOverlays();
    S3K.initToggles();

    document.querySelectorAll('[data-action="toggle-theme"]').forEach(function (btn) {
      btn.addEventListener('click', S3K.toggleTheme);
    });

    // Ctrl/Cmd+K focuses the first search trigger (opens search modal if present)
    document.addEventListener('keydown', function (e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        var trigger = document.querySelector('[data-open="#search-modal"]');
        if (trigger) { e.preventDefault(); trigger.click(); }
      }
    });
  });
})();
