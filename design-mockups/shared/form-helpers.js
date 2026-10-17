/* ============================================================
   S3K CRM — generic, data-driven create/edit-modal helpers.
   Reused by every module's "New X" / "Edit X" modal so each
   module page only has to declare markup + a small data array,
   not reimplement lookup/validation/duplicate-check logic.
   ============================================================ */
(function () {
  'use strict';
  var S3K = window.S3K = window.S3K || {};

  /* ---- Collapsible sections: <div class="form-section-head" data-toggle-section> ---- */
  S3K.initFormSections = function (scope) {
    (scope || document).querySelectorAll('[data-toggle-section]').forEach(function (head) {
      if (head._wired) return;
      head._wired = true;
      head.addEventListener('click', function () { head.closest('.form-section').classList.toggle('is-collapsed'); });
    });
  };

  /* ---- Generic lookup/combobox ----
     <div class="lookup-wrap">
       <input data-lookup data-lookup-var="S3K_ACCOUNT_NAMES" data-lookup-create="true">
       <div class="lookup-dropdown" data-lookup-dropdown></div>
     </div>
     data-lookup-var names a global array of either strings, or {label, sub} objects.
  */
  function lookupOptions(input) {
    var varName = input.getAttribute('data-lookup-var');
    var raw = varName ? window[varName] : [];
    return (raw || []).map(function (o) { return typeof o === 'string' ? { label: o, sub: '' } : o; });
  }
  document.addEventListener('input', function (e) {
    if (!e.target.matches('[data-lookup]')) return;
    var input = e.target;
    var wrap = input.closest('.lookup-wrap');
    var dd = wrap.querySelector('[data-lookup-dropdown]');
    var q = input.value.trim().toLowerCase();
    var all = lookupOptions(input);
    var matches = all.filter(function (o) { return o.label.toLowerCase().indexOf(q) > -1; });
    var html = matches.slice(0, 8).map(function (o) {
      var initials = o.label.split(' ').map(function (w) { return w[0]; }).slice(0, 2).join('').toUpperCase();
      return '<div class="lookup-item" data-pick="' + o.label.replace(/"/g, '&quot;') + '"><div class="avatar avatar-xs" style="background:var(--surface-3);color:var(--muted);border-radius:6px;">' + initials + '</div><div><div style="font-size:12.5px;font-weight:600;">' + o.label + '</div>' + (o.sub ? '<div style="font-size:11px;color:var(--faint);">' + o.sub + '</div>' : '') + '</div></div>';
    }).join('');
    if (q && input.getAttribute('data-lookup-create') === 'true') {
      html += '<div class="lookup-item" data-create-entity style="color:var(--accent);"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:14px;height:14px;"><path d="M5 12h14M12 5v14"/></svg><span style="font-size:12.5px;font-weight:600;">Create new "' + input.value + '"</span></div>';
    }
    dd.innerHTML = html || '<div style="padding:10px;font-size:12px;color:var(--faint);">No matches</div>';
    dd.classList.add('is-open');
  });
  document.addEventListener('focusin', function (e) { if (e.target.matches('[data-lookup]')) e.target.dispatchEvent(new Event('input')); });
  document.addEventListener('click', function (e) {
    var pick = e.target.closest('[data-pick]');
    var create = e.target.closest('[data-create-entity]');
    if (pick) {
      var wrap = pick.closest('.lookup-wrap');
      wrap.querySelector('[data-lookup]').value = pick.getAttribute('data-pick');
      wrap.querySelector('[data-lookup-dropdown]').classList.remove('is-open');
    } else if (create) {
      var wrap2 = create.closest('.lookup-wrap');
      var val = wrap2.querySelector('[data-lookup]').value;
      wrap2.querySelector('[data-lookup-dropdown]').classList.remove('is-open');
      S3K.toast('"' + val + '" created');
    } else if (!e.target.closest('.lookup-wrap')) {
      document.querySelectorAll('.lookup-dropdown.is-open').forEach(function (d) { d.classList.remove('is-open'); });
    }
  });

  /* ---- Duplicate detection ----
     <input data-dup-trigger data-dup-var="S3K_ACCOUNTS" data-dup-field="name">
     data-dup-var names a global array of records; data-dup-field is the record
     property to compare (case-insensitive exact match) against the input's value.
  */
  document.addEventListener('blur', function (e) {
    if (!e.target.matches('[data-dup-trigger]')) return;
    var input = e.target;
    var root = input.closest('.contact-form-root, [data-form-root]') || document;
    var banner = root.querySelector('[data-dup-banner]');
    if (!banner) return;
    var varName = input.getAttribute('data-dup-var');
    var field = input.getAttribute('data-dup-field');
    var records = window[varName] || [];
    var val = input.value.trim().toLowerCase();
    var match = val && records.some(function (r) { return (r[field] || '').toString().toLowerCase() === val; });
    banner.classList.toggle('is-visible', !!match);
  }, true);
  document.addEventListener('click', function (e) {
    if (e.target.closest('[data-dup-dismiss]')) {
      var root = e.target.closest('.contact-form-root, [data-form-root]');
      var banner = root && root.querySelector('[data-dup-banner]');
      if (banner) banner.classList.remove('is-visible');
    }
  });

  /* ---- Validation + Save ----
     requiredFields: [{ selector: '[data-field="name"]', label: 'Name is required' }]
     Returns true if valid (and shows toast + resets/closes), false if invalid (shows error summary).
  */
  S3K.trySaveForm = function (root, requiredFields, opts) {
    opts = opts || {};
    var errors = [];
    root.querySelectorAll('[data-field]').forEach(function (f) { f.classList.remove('has-error'); });
    requiredFields.forEach(function (rf) {
      var field = root.querySelector(rf.selector);
      if (!field) return;
      var val = (field.value || '').trim();
      var bad = !val || (rf.pattern && !rf.pattern.test(val));
      if (bad) errors.push({ field: field, label: rf.label });
    });
    var summary = root.querySelector('[data-error-summary]');
    var list = root.querySelector('[data-error-list]');
    if (errors.length) {
      if (summary && list) {
        list.innerHTML = errors.map(function (e) { return '<li><a data-jump>' + e.label + '</a></li>'; }).join('');
        Array.from(list.querySelectorAll('[data-jump]')).forEach(function (a, i) {
          a.addEventListener('click', function () { errors[i].field.focus(); errors[i].field.scrollIntoView({ behavior: 'smooth', block: 'center' }); });
        });
        errors.forEach(function (e) { e.field.classList.add('has-error'); });
        summary.classList.add('is-visible');
        summary.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
      return false;
    }
    if (summary) summary.classList.remove('is-visible');
    S3K.toast(opts.successMessage || 'Saved successfully');
    if (opts.onSuccess) opts.onSuccess();
    return true;
  };
})();
