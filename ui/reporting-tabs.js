(() => {
  const $ = (id) => document.getElementById(id);
  const num = (v) => Number.isFinite(Number(v)) ? Number(v) : 0;
  const fmt = (v) => num(v).toLocaleString();
  const pct = (v) => `${num(v).toFixed(1)}%`;
  const formatIssue = (value) => String(value || '').replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

  function injectStyles() {
    if ($('reportingTabsStyles')) return;
    const style = document.createElement('style');
    style.id = 'reportingTabsStyles';
    style.textContent = `
      .reporting-inner-tabs{display:flex;gap:8px;margin:0 0 18px;padding:6px;background:#eef3f8;border:1px solid var(--line);border-radius:8px;width:max-content;max-width:100%}
      .reporting-inner-tab{border:0;background:transparent;color:var(--muted);padding:9px 14px;border-radius:6px;font-size:13px;font-weight:750;cursor:pointer}
      .reporting-inner-tab.active{background:#fff;color:var(--navy,var(--ink));box-shadow:0 1px 4px rgba(15,23,42,.10)}
      .reporting-tab-panel.hidden{display:none!important}
      .dq-intro{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin:4px 0 16px;padding:16px;border:1px solid var(--line);border-radius:8px;background:#fff}
      .dq-intro h2{margin:0 0 5px;font-size:20px;color:var(--navy,var(--ink))}
      .dq-intro p{margin:0;color:var(--muted);max-width:760px}
      .dq-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:14px 0 20px}
      .dq-card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px;min-height:92px}
      .dq-card strong{display:block;font-size:25px;line-height:1.1;color:var(--navy,var(--ink));font-weight:800}
      .dq-card span{display:block;margin-top:6px;color:var(--muted);font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.02em}
      .dq-card small{display:block;margin-top:4px;color:var(--muted);font-size:11px}
      .dq-section{margin:22px 0}.dq-section h3{margin:0 0 10px;font-size:18px;color:var(--navy,var(--ink))}
      .dq-table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:8px;overflow:hidden}
      .dq-table th,.dq-table td{padding:12px 14px;border-bottom:1px solid var(--line);font-size:14px;line-height:1.35;text-align:left}
      .dq-table th{background:#eef4fc;color:var(--navy,var(--ink));font-size:13px;font-weight:750}
      .dq-status{display:inline-flex;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:750}
      .dq-status.good{background:#dcfce7;color:#15803d}.dq-status.warn{background:#fef3c7;color:#a16207}.dq-status.bad{background:#fee2e2;color:#b91c1c}.dq-status.neutral{background:#f1f5f9;color:#64748b}
      .dq-improvements{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
      .dq-improvement{background:#fff;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;padding:12px 14px}
      .dq-improvement strong{display:block;color:var(--navy,var(--ink));margin-bottom:3px}.dq-improvement span{font-size:12px;color:var(--muted)}
      .dq-filters{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:12px;align-items:end;margin:0 0 14px;padding:16px;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 1px 3px rgba(15,23,42,.05)}
      .dq-filter-field{display:grid;gap:5px;min-width:0}.dq-filter-field label{font-size:11px;font-weight:700;color:var(--muted)}
      .dq-filters select,.dq-filters button{width:100%;min-height:38px;padding:8px 11px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);font-size:12px;box-sizing:border-box}.dq-filters select:focus{outline:2px solid #bfdbfe;outline-offset:1px}.dq-filters button{grid-column:1/-1;justify-self:center;width:min(220px,100%);background:var(--accent);color:#fff;font-weight:700;cursor:pointer;border-color:var(--accent)}
      .dq-loading-panel{min-height:360px;display:flex;align-items:center;justify-content:center}
      .dq-loading-panel.hidden,.dq-body.hidden{display:none!important}
      .dq-loading-box{display:flex;align-items:center;gap:12px;padding:16px 20px;background:#fff;border:1px solid var(--line);border-radius:8px;color:var(--ink);font-weight:750;box-shadow:0 8px 24px rgba(15,23,42,.08)}
      @media(max-width:900px){.dq-filters{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:520px){.dq-filters{grid-template-columns:1fr}}
      @media(max-width:1000px){.dq-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.dq-improvements{grid-template-columns:1fr}}
    `;
    document.head.appendChild(style);
  }

  function statusClass(value, goodThreshold, warnThreshold, inverse = false) {
    const n = num(value);
    if (inverse) return n <= goodThreshold ? 'good' : n <= warnThreshold ? 'warn' : 'bad';
    return n >= goodThreshold ? 'good' : n >= warnThreshold ? 'warn' : 'bad';
  }

  function metricCard(value, label, note = '') {
    return `<div class="dq-card"><strong>${value}</strong><span>${label}</span>${note ? `<small>${note}</small>` : ''}</div>`;
  }

  function buildQualityPanel() {
    if ($('reportQualityPanel')) return $('reportQualityPanel');
    const panel = document.createElement('div');
    panel.id = 'reportQualityPanel';
    panel.className = 'reporting-tab-panel hidden';
    panel.innerHTML = `
      <div class="dq-intro">
        <div><h2>Data Quality &amp; Improvements</h2><p>Focus on invalid listings, unresolved issues, and measurable improvement from automatic and manual fixes.</p></div>
        <button id="refreshDataQualityBtn" type="button">Refresh Quality Metrics</button>
      </div>
      <div class="dq-filters"><div class="dq-filter-field"><label for="dqBrandFilter">Brand</label><select id="dqBrandFilter"><option value="">All impacted brands</option></select></div><div class="dq-filter-field"><label for="dqStateFilter">State</label><select id="dqStateFilter"><option value="">All impacted states</option></select></div><div class="dq-filter-field"><label for="dqReasonFilter">Issue type</label><select id="dqReasonFilter"><option value="">All issue types</option></select></div><div class="dq-filter-field"><label for="dqStatusFilter">Review status</label><select id="dqStatusFilter"><option value="all">All statuses</option><option value="needs_review">Needs review</option><option value="ai_fixed">AI fixed</option></select></div><button id="applyQualityFiltersBtn" type="button">Apply filters</button></div>
      <div id="dqStatus" class="report-status">Open this tab to load quality metrics.</div>
      <div id="dqLoadingPanel" class="dq-loading-panel hidden"><div class="dq-loading-box"><span class="spinner"></span><span>Loading quality metrics</span></div></div>
      <div id="dqBody" class="dq-body hidden">
        <div id="dqMetricGrid" class="dq-grid"></div>
        <div class="dq-section"><h3>Quality Signals</h3><div id="dqSignals"></div></div>
        <div class="dq-section"><h3>Improvement Opportunities</h3><div id="dqImprovements" class="dq-improvements"></div></div>
        <div class="dq-section"><h3>Quality by Brand</h3><div id="dqBrandTable"></div></div>
        <div class="dq-section"><h3>Most Impacted States and Cities</h3><div id="dqGeoTables" class="dq-improvements"></div></div>
        <div class="dq-section"><h3>Reconciliation</h3><div id="dqReconciliation"></div></div>
      </div>
    `;
    return panel;
  }

  async function loadQuality(forceRefresh = false) {
    const status = $('dqStatus');
    if (!status) return;
    const refreshButton = $('refreshDataQualityBtn');
    const loadingPanel = $('dqLoadingPanel');
    const body = $('dqBody');
    const originalRefreshLabel = refreshButton?.innerHTML || 'Refresh Quality Metrics';
    if (loadingPanel) loadingPanel.classList.remove('hidden');
    if (body) body.classList.add('hidden');
    if (forceRefresh) {
      if (refreshButton) { refreshButton.disabled = true; refreshButton.innerHTML = '<span class="spinner"></span> Refreshing quality metrics'; }
      status.className = 'report-status hidden';
      status.textContent = '';
    } else {
      status.className = 'report-status hidden';
      status.textContent = '';
    }
      try {
        let qs = '';
      try {
        if (typeof window.reportingQueryString === 'function') {
          const brandOnly = new URLSearchParams(window.reportingQueryString());
          ['min_population', 'min_income', 'max_median_age'].forEach((key) => brandOnly.delete(key));
          qs = brandOnly.toString();
        }
      } catch (_) {}
      const qualityParams = new URLSearchParams(qs);
      if (forceRefresh) qualityParams.set('refresh', '1');
      [['brand', 'dqBrandFilter'], ['state', 'dqStateFilter'], ['reason', 'dqReasonFilter'], ['status', 'dqStatusFilter']].forEach(([key, id]) => { const node = $(id); if (node?.value) qualityParams.set(key, node.value); });
      const res = await fetch(`/api/reporting/quality${qualityParams.toString() ? `?${qualityParams}` : ''}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Unable to load quality metrics.');
      const q = data.metrics || {};
      const raw = num(q.invalid_listings);
      const needsReview = num(q.needs_manual_review);
      const aiFixed = num(q.ai_fixed);
      const manualFixed = num(q.manual_fixed);
      const unresolvedRate = num(q.unresolved_rate_pct);
      const reasons = Array.isArray(data.reasons) ? data.reasons : [];
      const states = Array.isArray(data.states) ? data.states : [];
      const cities = Array.isArray(data.cities) ? data.cities : [];
      [['dqBrandFilter', data.filters?.brands || [], 'All impacted brands'], ['dqStateFilter', data.filters?.states || [], 'All impacted states'], ['dqReasonFilter', data.filters?.reasons || [], 'All issue types']].forEach(([id, values, label]) => {
        const node = $(id); if (!node) return; const previous = node.value;
        node.innerHTML = `<option value="">${label}</option>${values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(formatIssue(value))}</option>`).join('')}`;
        if (values.includes(previous)) node.value = previous;
      });

      $('dqMetricGrid').innerHTML = [
        metricCard(fmt(raw), 'Invalid listings', 'Active validation and review population'),
        metricCard(fmt(needsReview), 'Needs manual review'),
        metricCard(fmt(aiFixed), 'Listings fixed automatically'),
        metricCard(fmt(manualFixed), 'Listings fixed manually'),
        metricCard(pct(unresolvedRate), 'Unresolved rate'),
        metricCard(fmt(reasons.length), 'Active issue types'),
        metricCard(fmt(states.length), 'Impacted states'),
        metricCard(fmt(cities.length), 'Impacted cities')
      ].join('');

      const hasData = raw > 0 || needsReview > 0 || aiFixed > 0 || manualFixed > 0 || reasons.length > 0;

      const signals = [
        ['Manual review queue', fmt(needsReview), hasData ? (needsReview ? 'bad' : 'good') : 'neutral'],
        ['Unresolved rate', hasData ? pct(unresolvedRate) : '—', hasData ? statusClass(unresolvedRate, 5, 20, true) : 'neutral'],
        ['Automatic fixes', fmt(aiFixed), hasData ? (aiFixed ? 'good' : 'warn') : 'neutral'],
        ['Manual fixes', fmt(manualFixed), hasData ? (manualFixed ? 'good' : 'warn') : 'neutral'],
        ['Issue categories', fmt(reasons.length), hasData ? (reasons.length ? 'warn' : 'good') : 'neutral']
      ];
      $('dqSignals').innerHTML = `<table class="dq-table"><thead><tr><th>Signal</th><th>Current</th><th>Status</th></tr></thead><tbody>${signals.map(([name,val,cls]) => `<tr><td>${name}</td><td>${val}</td><td><span class="dq-status ${cls}">${cls === 'good' ? 'Healthy' : cls === 'warn' ? 'Review' : cls === 'bad' ? 'Needs attention' : 'No data'}</span></td></tr>`).join('')}</tbody></table>`;

      const buckets = reasons.filter((bucket) => num(bucket.count) > 0).map((bucket) => ({...bucket, type: bucket.reason}));
      if (buckets.length) {
        $('dqSignals').insertAdjacentHTML('beforeend', `<table class="dq-table" style="margin-top:12px;"><thead><tr><th>Validation issue</th><th>Records</th><th>Resolution</th></tr></thead><tbody>${buckets.map((bucket) => `<tr><td>${escapeHtml(formatIssue(bucket.type || 'Validation issue'))}</td><td>${fmt(bucket.count)}</td><td>${bucket.resolved === true ? 'Resolved' : 'Needs review'}</td></tr>`).join('')}</tbody></table>`);
      }

      const brandRows = Array.isArray(data.brands) ? data.brands : [];
      $('dqBrandTable').innerHTML = `<table class="dq-table"><thead><tr><th>Brand</th><th>Invalid</th><th>Needs review</th><th>AI fixed</th></tr></thead><tbody>${brandRows.length ? brandRows.map((brand) => `<tr><td>${escapeHtml(formatBrandName(brand.brand))}</td><td>${fmt(brand.invalid)}</td><td>${fmt(brand.needs_review)}</td><td>${fmt(brand.ai_enriched)}</td></tr>`).join('') : '<tr><td colspan="4">No invalid brand records are available for this filter.</td></tr>'}</tbody></table>`;
      $('dqGeoTables').innerHTML = `<div><table class="dq-table"><thead><tr><th>State</th><th>Invalid listings</th></tr></thead><tbody>${states.slice(0, 10).map((row) => `<tr><td>${escapeHtml(row.state)}</td><td>${fmt(row.count)}</td></tr>`).join('') || '<tr><td colspan="2">No impacted states.</td></tr>'}</tbody></table></div><div><table class="dq-table"><thead><tr><th>City</th><th>Invalid listings</th></tr></thead><tbody>${cities.slice(0, 10).map((row) => `<tr><td>${escapeHtml(row.city)}</td><td>${fmt(row.count)}</td></tr>`).join('') || '<tr><td colspan="2">No impacted cities.</td></tr>'}</tbody></table></div>`;

      const improvements = [];
      if (needsReview) improvements.push(['Reduce manual review', `${fmt(needsReview)} invalid listings remain unresolved and require attention.`]);
      if (reasons[0]) improvements.push(['Address the leading issue', `${fmt(reasons[0].count)} listings are affected by ${String(reasons[0].reason).replace(/_/g, ' ')}.`]);
      if (aiFixed) improvements.push(['Automatic improvements completed', `${fmt(aiFixed)} listings have passed through the automatic repair path.`]);
      if (!improvements.length) {
        if (hasData) {
          improvements.push(['Maintain current quality level', 'No major threshold breach is visible in the current reporting summary. Continue monitoring freshness and source coverage.']);
        } else {
          improvements.push(['No data available', 'No validation or review records are currently recorded. Signals will populate once records are processed.']);
        }
      }
      $('dqImprovements').innerHTML = improvements.map(([title,text]) => `<div class="dq-improvement"><strong>${title}</strong><span>${text}</span></div>`).join('');

      $('dqReconciliation').innerHTML = `<table class="dq-table"><thead><tr><th>Measure</th><th>Value</th><th>Explanation</th></tr></thead><tbody>
        <tr><td>Invalid listings</td><td>${fmt(raw)}</td><td>Active records that failed validation or remain in review.</td></tr>
        <tr><td>Review status</td><td>${fmt(needsReview)} unresolved</td><td>Only records still requiring user attention are counted here.</td></tr>
        <tr><td>Change history</td><td>Not tracked yet</td><td>Run-over-run comparison requires snapshot history.</td></tr>
      </tbody></table>`;

      if (loadingPanel) loadingPanel.classList.add('hidden');
      if (body) body.classList.remove('hidden');
      status.className = 'report-status hidden';
      status.textContent = '';
    } catch (err) {
      if (loadingPanel) loadingPanel.classList.add('hidden');
      if (body) body.classList.add('hidden');
      status.className = 'report-status error';
      status.textContent = err.message || 'Unable to load data quality metrics.';
    } finally {
      if (forceRefresh && refreshButton) { refreshButton.disabled = false; refreshButton.innerHTML = originalRefreshLabel; }
      if (forceRefresh && status.className !== 'report-status error') { status.className = 'report-status hidden'; status.textContent = ''; }
      const reportingView = $('reportingView');
      if (reportingView) {
        const shell = reportingView.querySelector('.report-shell');
        if (shell) {
          shell.querySelectorAll('.report-location-panel').forEach((n) => n.classList.add('hidden'));
          const quality = $('reportQualityPanel');
          if (quality) quality.classList.remove('hidden');
          const tabs = $('reportingInnerTabs');
          if (tabs) tabs.querySelectorAll('[data-report-tab]').forEach((b) => b.classList.toggle('active', b.dataset.reportTab === 'quality'));
        }
      }
    }
  }

  function init() {
    injectStyles();
    const reportingView = $('reportingView');
    if (!reportingView) return false;
    const shell = reportingView.querySelector('.report-shell');
    if (!shell || $('reportingInnerTabs')) return true;
    const hero = shell.querySelector('.report-hero');
    const tabs = document.createElement('div');
    tabs.id = 'reportingInnerTabs';
    tabs.className = 'reporting-inner-tabs';
    tabs.innerHTML = `
      <button type="button" class="reporting-inner-tab active" data-report-tab="location">Location Intelligence &amp; Whitespace</button>
      <button type="button" class="reporting-inner-tab" data-report-tab="quality">Data Quality &amp; Improvements</button>
    `;
    if (hero && hero.nextSibling) shell.insertBefore(tabs, hero.nextSibling); else shell.prepend(tabs);

    const quality = buildQualityPanel();
    shell.appendChild(quality);
    [...shell.children].forEach((child) => {
      if (child !== hero && child !== tabs && child !== quality) child.classList.add('report-location-panel');
    });

    function switchTab(name) {
      tabs.querySelectorAll('[data-report-tab]').forEach((b) => b.classList.toggle('active', b.dataset.reportTab === name));
      shell.querySelectorAll('.report-location-panel').forEach((n) => n.classList.toggle('hidden', name !== 'location'));
      quality.classList.toggle('hidden', name !== 'quality');
      if (name === 'quality') loadQuality();
      if (name === 'location' && typeof window.reportingMap?.invalidateSize === 'function') setTimeout(() => window.reportingMap.invalidateSize(), 100);
    }

    tabs.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-report-tab]');
      if (btn) switchTab(btn.dataset.reportTab);
    });
    $('refreshDataQualityBtn')?.addEventListener('click', () => loadQuality(true));
    $('applyQualityFiltersBtn')?.addEventListener('click', loadQuality);
    switchTab('location');
    return true;
  }

  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    if (init() || attempts > 80) clearInterval(timer);
  }, 250);
})();
