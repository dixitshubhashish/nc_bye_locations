(() => {
  const $ = (id) => document.getElementById(id);
  const num = (v) => Number.isFinite(Number(v)) ? Number(v) : 0;
  const fmt = (v) => num(v).toLocaleString();
  const pct = (v) => `${num(v).toFixed(1)}%`;

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
      .dq-table th,.dq-table td{padding:9px 10px;border-bottom:1px solid var(--line);font-size:12px;text-align:left}
      .dq-table th{background:#eef4fc;color:var(--navy,var(--ink));font-weight:750}
      .dq-status{display:inline-flex;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:750}
      .dq-status.good{background:#dcfce7;color:#15803d}.dq-status.warn{background:#fef3c7;color:#a16207}.dq-status.bad{background:#fee2e2;color:#b91c1c}
      .dq-improvements{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
      .dq-improvement{background:#fff;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;padding:12px 14px}
      .dq-improvement strong{display:block;color:var(--navy,var(--ink));margin-bottom:3px}.dq-improvement span{font-size:12px;color:var(--muted)}
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
        <div><h2>Data Quality &amp; Improvements</h2><p>Operational quality view for the same records used by Location Intelligence. This summarizes completeness, duplicates, freshness, confidence, and the highest-value remediation opportunities without replacing the existing Error Listings or Template Library workflows.</p></div>
        <button id="refreshDataQualityBtn" type="button">Refresh Quality Metrics</button>
      </div>
      <div id="dqStatus" class="report-status">Open this tab to load quality metrics.</div>
      <div id="dqMetricGrid" class="dq-grid"></div>
      <div class="dq-section"><h3>Quality Signals</h3><div id="dqSignals"></div></div>
      <div class="dq-section"><h3>Improvement Opportunities</h3><div id="dqImprovements" class="dq-improvements"></div></div>
      <div class="dq-section"><h3>Reconciliation</h3><div id="dqReconciliation"></div></div>
    `;
    return panel;
  }

  async function loadQuality() {
    const status = $('dqStatus');
    if (!status) return;
    status.className = 'report-status loading';
    status.innerHTML = '<span class="spinner"></span> Loading data quality metrics...';
    try {
      let qs = '';
      try { if (typeof window.reportingQueryString === 'function') qs = window.reportingQueryString(); } catch (_) {}
      const res = await fetch(`/api/reporting${qs ? `?${qs}` : ''}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Unable to load quality metrics.');
      const q = data.data_quality_summary || {};
      const totals = data.totals || {};
      const raw = num(q.total_raw_locations || totals.total_locations);
      const validRate = num(q.valid_rate_pct);
      const dupRate = num(q.duplicate_rate_pct);
      const zipComp = num(q.zip_completeness_pct);
      const coordComp = num(q.coordinate_completeness_pct);
      const freshness = num(q.freshness_days);
      const confidence = String(q.overall_confidence || 'N/A').toUpperCase();
      const validEstimated = raw && validRate ? Math.round(raw * validRate / 100) : 0;
      const dupEstimated = raw && dupRate ? Math.round(raw * dupRate / 100) : 0;

      $('dqMetricGrid').innerHTML = [
        metricCard(fmt(raw), 'Records in analytical scope', 'Same reporting filter context'),
        metricCard(validRate ? pct(validRate) : 'N/A', 'Valid rate'),
        metricCard(dupRate ? pct(dupRate) : 'N/A', 'Duplicate rate'),
        metricCard(zipComp ? pct(zipComp) : 'N/A', 'ZIP completeness'),
        metricCard(coordComp ? pct(coordComp) : 'N/A', 'Coordinate completeness'),
        metricCard(freshness || freshness === 0 ? `${freshness} days` : 'N/A', 'Source freshness'),
        metricCard(confidence, 'Overall confidence'),
        metricCard(fmt(validEstimated), 'Estimated usable records', validRate ? 'Derived from backend valid rate' : 'Not available')
      ].join('');

      const signals = [
        ['Valid records', validRate ? pct(validRate) : 'N/A', statusClass(validRate, 98, 95)],
        ['Duplicate rate', dupRate ? pct(dupRate) : 'N/A', statusClass(dupRate, 1, 3, true)],
        ['ZIP completeness', zipComp ? pct(zipComp) : 'N/A', statusClass(zipComp, 98, 95)],
        ['Coordinate completeness', coordComp ? pct(coordComp) : 'N/A', statusClass(coordComp, 98, 92)],
        ['Freshness', freshness || freshness === 0 ? `${freshness} days` : 'N/A', statusClass(freshness, 7, 30, true)],
        ['Confidence', confidence, confidence === 'HIGH' ? 'good' : confidence === 'MEDIUM' ? 'warn' : 'bad']
      ];
      $('dqSignals').innerHTML = `<table class="dq-table"><thead><tr><th>Signal</th><th>Current</th><th>Status</th></tr></thead><tbody>${signals.map(([name,val,cls]) => `<tr><td>${name}</td><td>${val}</td><td><span class="dq-status ${cls}">${cls === 'good' ? 'Healthy' : cls === 'warn' ? 'Review' : 'Needs attention'}</span></td></tr>`).join('')}</tbody></table>`;

      const improvements = [];
      if (zipComp && zipComp < 99.5) improvements.push(['Improve ZIP completeness', `${Math.max(0, Math.round(raw * (100 - zipComp) / 100)).toLocaleString()} records may need ZIP enrichment or validation.`]);
      if (coordComp && coordComp < 99) improvements.push(['Improve coordinate coverage', `${Math.max(0, Math.round(raw * (100 - coordComp) / 100)).toLocaleString()} records may benefit from source coordinates, ZIP centroid, or city/state fallback.`]);
      if (dupRate > 1) improvements.push(['Review duplicate candidates', `Approximately ${dupEstimated.toLocaleString()} records may require canonical-location review.`]);
      if (freshness > 14) improvements.push(['Refresh stale sources', `Current freshness is ${freshness} days. Prioritize source refresh before relying on market-gap conclusions.`]);
      if (validRate && validRate < 99) improvements.push(['Reduce validation failures', `Approximately ${Math.max(0, raw - validEstimated).toLocaleString()} records are outside the valid analytical set.`]);
      if (!improvements.length) improvements.push(['Maintain current quality level', 'No major threshold breach is visible in the current reporting summary. Continue monitoring freshness and source coverage.']);
      $('dqImprovements').innerHTML = improvements.map(([title,text]) => `<div class="dq-improvement"><strong>${title}</strong><span>${text}</span></div>`).join('');

      $('dqReconciliation').innerHTML = `<table class="dq-table"><thead><tr><th>Measure</th><th>Value</th><th>Explanation</th></tr></thead><tbody>
        <tr><td>Records in scope</td><td>${fmt(raw)}</td><td>Current reporting scope after selected geography/brand filters.</td></tr>
        <tr><td>Estimated valid</td><td>${fmt(validEstimated)}</td><td>Calculated from backend-reported valid rate when available.</td></tr>
        <tr><td>Estimated duplicate observations</td><td>${fmt(dupEstimated)}</td><td>Calculated from backend-reported duplicate rate when available.</td></tr>
        <tr><td>Location Intelligence source</td><td>Shared</td><td>Both reporting tabs consume the same reporting API and filters.</td></tr>
      </tbody></table>`;

      status.className = 'report-status';
      status.textContent = `Quality metrics loaded${data.reporting_cache ? ` • cache: ${data.reporting_cache}` : ''}.`;
    } catch (err) {
      status.className = 'report-status error';
      status.textContent = err.message || 'Unable to load data quality metrics.';
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
    $('refreshDataQualityBtn')?.addEventListener('click', loadQuality);
    switchTab('location');
    return true;
  }

  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    if (init() || attempts > 80) clearInterval(timer);
  }, 250);
})();
