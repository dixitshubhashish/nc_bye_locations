(() => {
  const $ = (id) => document.getElementById(id);
  const num = (v) => Number.isFinite(Number(v)) ? Number(v) : 0;
  const fmt = (v) => num(v).toLocaleString();
  const pct = (v) => `${num(v).toFixed(1)}%`;
  const formatIssue = (value) => String(value || '').replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());

  // ---- d3 charting -------------------------------------------------------
  // Vendored d3 (ui/vendor/d3). Every chart here is built with it; the
  // hand-rolled SVG string versions these replaced could not support real
  // hover/tooltip interaction, axes, or responsive rescaling.
  const hasD3 = () => typeof window.d3 !== 'undefined';

  // One tooltip element per chart container, positioned against the cursor.
  function chartTooltip(container) {
    let tip = container.querySelector('.dq-chart-tooltip');
    if (!tip) {
      tip = document.createElement('div');
      tip.className = 'dq-chart-tooltip';
      container.appendChild(tip);
    }
    return {
      show(html, event) {
        tip.innerHTML = html;
        tip.style.display = 'block';
        const bounds = container.getBoundingClientRect();
        const left = Math.max(4, Math.min(event.clientX - bounds.left + 12, container.clientWidth - tip.offsetWidth - 4));
        const top = Math.max(4, event.clientY - bounds.top - tip.offsetHeight - 10);
        tip.style.left = `${left}px`;
        tip.style.top = `${top}px`;
      },
      hide() { tip.style.display = 'none'; },
    };
  }

  /**
   * Multi-series time chart: real d3 scales/axes, a point per bucket, hover
   * tooltips, and a crosshair. Used by both Trends Over Time and Historical
   * Quality so the two can't drift apart.
   * series: [{ label, color, points: [{date, count}] }]
   */
  function renderTimeSeriesChart(container, series, options = {}) {
    if (!container) return;
    container.innerHTML = '';
    const active = (series || []).filter((s) => Array.isArray(s.points) && s.points.length);
    if (!active.length) {
      container.innerHTML = `<div class="report-status">${escapeHtml(options.emptyMessage || 'No data for this period yet.')}</div>`;
      return;
    }
    if (!hasD3()) {
      container.innerHTML = '<div class="report-status">Charting library failed to load. Refresh the page to try again.</div>';
      return;
    }
    const d3 = window.d3;
    const height = options.height || 320;
    const margin = { top: 16, right: 20, bottom: 34, left: 56 };
    const width = Math.max(320, container.clientWidth || 900);
    const innerW = Math.max(40, width - margin.left - margin.right);
    const innerH = Math.max(40, height - margin.top - margin.bottom);

    const parsed = active.map((s) => ({
      ...s,
      points: s.points
        .map((p) => ({ date: new Date(p.date), value: num(p.count) }))
        .filter((p) => !Number.isNaN(p.date.getTime()))
        .sort((a, b) => a.date - b.date),
    })).filter((s) => s.points.length);
    if (!parsed.length) {
      container.innerHTML = `<div class="report-status">${escapeHtml(options.emptyMessage || 'No data for this period yet.')}</div>`;
      return;
    }

    const allPoints = parsed.flatMap((s) => s.points);
    const xExtent = d3.extent(allPoints, (p) => p.date);
    // A single bucket has no extent to scale across - pad it by a day so the
    // point renders mid-chart instead of collapsing onto the axis edge.
    if (xExtent[0].getTime() === xExtent[1].getTime()) {
      xExtent[0] = d3.timeDay.offset(xExtent[0], -1);
      xExtent[1] = d3.timeDay.offset(xExtent[1], 1);
    }
    const x = d3.scaleTime().domain(xExtent).range([0, innerW]);
    const y = d3.scaleLinear().domain([0, d3.max(allPoints, (p) => p.value) || 1]).nice().range([innerH, 0]);

    const svg = d3.select(container).append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('width', '100%')
      .attr('height', height)
      .attr('role', 'img')
      .attr('aria-label', options.ariaLabel || 'Time series chart');
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    g.append('g')
      .attr('class', 'dq-grid-lines')
      .call(d3.axisLeft(y).ticks(5).tickSize(-innerW).tickFormat(''))
      .call((sel) => sel.select('.domain').remove())
      .selectAll('line').attr('stroke', '#eef2f7');
    g.append('g')
      .attr('transform', `translate(0,${innerH})`)
      .call(d3.axisBottom(x).ticks(Math.min(7, allPoints.length)).tickFormat(d3.timeFormat('%b %d')))
      .selectAll('text').attr('fill', '#64748b').attr('font-size', 11);
    g.append('g')
      .call(d3.axisLeft(y).ticks(5).tickFormat((v) => fmt(v)))
      .selectAll('text').attr('fill', '#64748b').attr('font-size', 11);
    g.selectAll('.domain').attr('stroke', '#cbd5e1');

    const line = d3.line().x((p) => x(p.date)).y((p) => y(p.value)).curve(d3.curveMonotoneX);
    const tip = chartTooltip(container);

    parsed.forEach((s) => {
      const color = s.color || '#1677ee';
      if (s.points.length > 1) {
        g.append('path').datum(s.points)
          .attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2.5).attr('d', line);
      }
      g.selectAll(null).data(s.points).enter().append('circle')
        .attr('class', 'dq-chart-point')
        .attr('cx', (p) => x(p.date))
        .attr('cy', (p) => y(p.value))
        .attr('r', 4)
        .attr('fill', color)
        .attr('stroke', '#fff')
        .attr('stroke-width', 1.5)
        .style('cursor', 'pointer')
        .on('mouseenter', function (event, p) {
          d3.select(this).attr('r', 6);
          tip.show(`<strong>${escapeHtml(s.label)}</strong><br>${escapeHtml(d3.timeFormat('%b %d, %Y')(p.date))}<br>${fmt(p.value)}`, event);
        })
        .on('mousemove', (event, p) => {
          tip.show(`<strong>${escapeHtml(s.label)}</strong><br>${escapeHtml(d3.timeFormat('%b %d, %Y')(p.date))}<br>${fmt(p.value)}`, event);
        })
        .on('mouseleave', function () {
          d3.select(this).attr('r', 4);
          tip.hide();
        });
    });
  }

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
      .reporting-tab-panel{display:block;width:100%;max-width:none;box-sizing:border-box}.dq-body,.dq-section{width:100%;max-width:none;box-sizing:border-box}.dq-grid{display:grid;grid-template-columns:repeat(4,minmax(190px,1fr));gap:14px;margin:14px 0 20px;width:100%;max-width:none}
      .dq-card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px;min-height:92px}
      .dq-card strong{display:block;font-size:25px;line-height:1.1;color:var(--navy,var(--ink));font-weight:800}
      .dq-card span{display:block;margin-top:6px;color:var(--muted);font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.02em}
      .dq-card small{display:block;margin-top:4px;color:var(--muted);font-size:11px}
      .dq-section{margin:22px 0}.dq-section h3{margin:0 0 10px;font-size:18px;color:var(--navy,var(--ink))}
      /* Shared d3 chart tooltip (all charts use chartTooltip()). */
      .dq-chart-tooltip{position:absolute;display:none;z-index:20;pointer-events:none;background:#0f172a;color:#fff;padding:7px 10px;border-radius:6px;font-size:12px;line-height:1.45;box-shadow:0 6px 18px rgba(15,23,42,.28);white-space:nowrap}
      /* Number cards expose a download of the data behind the figure. */
      .dq-card{position:relative}
      .dq-card .dq-metric-download{position:absolute;top:6px;right:6px;display:none;align-items:center;gap:4px;padding:3px 7px;border:1px solid var(--line);border-radius:5px;background:#fff;color:var(--muted);font-size:10px;font-weight:700;cursor:pointer;line-height:1}
      .dq-card:hover .dq-metric-download{display:inline-flex}
      .dq-card .dq-metric-download:hover{color:var(--accent);border-color:var(--accent)}
      /* Same hover-to-download affordance on the location tab's number
         cards, which previously had no export at all. */
      .report-metric{position:relative}
      .report-metric .report-metric-download{position:absolute;top:4px;right:4px;display:none;align-items:center;gap:4px;padding:2px 6px;border:1px solid var(--line);border-radius:5px;background:#fff;color:var(--muted);font-size:10px;font-weight:700;cursor:pointer;line-height:1}
      .report-metric:hover .report-metric-download{display:inline-flex}
      .report-metric .report-metric-download:hover{color:var(--accent);border-color:var(--accent)}
      .dq-table{width:100%;border-collapse:collapse;background:#fff;border:1px solid var(--line);border-radius:8px}
      .dq-table th,.dq-table td{padding:12px 14px;border-bottom:1px solid var(--line);font-size:14px;line-height:1.35;text-align:left}
      .dq-table th{background:#eef4fc;color:var(--navy,var(--ink));font-size:13px;font-weight:750}
      .dq-status{display:inline-flex;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:750}
      .dq-status.good{background:#dcfce7;color:#15803d}.dq-status.warn{background:#fef3c7;color:#a16207}.dq-status.bad{background:#fee2e2;color:#b91c1c}.dq-status.neutral{background:#f1f5f9;color:#64748b}
      .dq-improvements{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
      /* A single vertical list, not a 2-column grid - with an odd count of
         cards the last one used to sit alone next to empty space. Separate
         class from .dq-improvements since that one is shared with the
         States/Cities table pair below, which is a genuine even 2-up. */
      .dq-improvements-list{display:grid;grid-template-columns:1fr;gap:10px}
      .dq-improvement{background:#fff;border:1px solid var(--line);border-left:4px solid var(--accent);border-radius:8px;padding:14px 16px}
      .dq-improvement strong{display:block;font-size:15px;color:var(--navy,var(--ink));margin-bottom:4px}.dq-improvement span{font-size:13px;color:var(--muted)}
      /* Matches the Location Intelligence sidebar exactly (UIX-07): same
         single-column stack, card padding, label/control type scale and
         heading treatment, so the two tabs' filter rails can't look like
         two different designs. Values mirror .reporting-sidebar-pane /
         .report-filter-group / .report-filter-label / .report-filter-control
         and .report-filter-category-title in integrations.html. */
      .dq-filters{display:grid;grid-template-columns:1fr;gap:10px;align-items:stretch;margin:0 0 18px;padding:16px;background:#fff;border:1px solid var(--line);border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
      .dq-filters::before{content:'Report Filters';padding-bottom:8px;margin-bottom:2px;border-bottom:1px solid var(--line);color:#1e293b;font-size:15px;font-weight:700}
      .dq-filter-field{display:grid;gap:4px;min-width:0;padding:8px;border:1px solid var(--line);border-radius:8px;background:#fff}
      .dq-filter-field label{display:block;font-size:11px;font-weight:600;color:var(--ink);margin-bottom:0}
      .dq-filters select,.dq-filters input{width:100%;box-sizing:border-box;padding:7px 10px;border:1px solid var(--line);border-radius:6px;font-size:11px;font-weight:600;font-family:inherit;color:var(--ink);background:var(--panel,#fff)}
      .dq-filters select:focus,.dq-filters input:focus{outline:2px solid #bfdbfe;outline-offset:1px}
      .dq-filters button{width:100%;box-sizing:border-box;padding:9px;border:1px solid var(--line);border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;background:#fff;color:var(--ink)}
      .dq-filters #applyQualityFiltersBtn{background:var(--accent);color:#fff}.dq-filters #resetQualityFiltersBtn{background:#fff;color:var(--ink)}
      .dq-loading-panel{min-height:360px;display:flex;align-items:center;justify-content:center}
      .dq-loading-panel.hidden,.dq-body.hidden{display:none!important}
      .dq-loading-box{display:flex;align-items:center;gap:12px;padding:16px 20px;background:#fff;border:1px solid var(--line);border-radius:8px;color:var(--ink);font-weight:750;box-shadow:0 8px 24px rgba(15,23,42,.08)}
      .dq-layout{display:grid;grid-template-columns:290px minmax(0,1fr);gap:24px;align-items:start;width:100%;max-width:none}.dq-sidebar{position:sticky;top:16px;min-width:0}.dq-main{display:block;min-width:0;width:100%;max-width:none}.dq-main .dq-table{width:100%;table-layout:auto}.dq-sidebar .dq-filters{display:grid;grid-template-columns:1fr;gap:12px;margin:0;padding:16px}.dq-sidebar .dq-filters::before{grid-column:1}.dq-sidebar .dq-filter-field{padding:12px}.dq-sidebar .dq-filters button{grid-column:1}.dq-sidebar .dq-filters #applyQualityFiltersBtn,.dq-sidebar .dq-filters #resetQualityFiltersBtn{width:100%}
      .dq-history-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(260px,1fr);gap:14px}.dq-history-chart{min-height:190px;padding:8px;border:1px solid var(--line);border-radius:8px;background:#fbfdff}.dq-history-chart svg{width:100%;height:175px;display:block}.dq-period-row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--line);font-size:12px}.dq-period-row strong{color:var(--navy,var(--ink))}
      /* Trends Over Time is its own, bigger chart (explicit request) -
         #dqTrendChart shares .dq-history-chart's box styling but overrides
         the height, since that shared class's svg rule is also used by the
         smaller Historical Quality chart next to it. */
      #dqTrendChart{min-height:360px}#dqTrendChart svg{height:340px}
      @media(max-width:900px){.dq-layout{grid-template-columns:1fr}.dq-sidebar{position:static}.dq-sidebar .dq-filters{grid-template-columns:repeat(2,minmax(0,1fr))}.dq-sidebar .dq-filters::before{grid-column:1/-1}.dq-sidebar .dq-filters button{grid-column:auto}}@media(max-width:520px){.dq-filters{grid-template-columns:1fr}.dq-filters::before{grid-column:1}.dq-sidebar .dq-filters{grid-template-columns:1fr}.dq-sidebar .dq-filters::before{grid-column:1}}
      @media(max-width:1000px){.dq-grid{grid-template-columns:repeat(2,minmax(160px,1fr))}.dq-improvements{grid-template-columns:1fr}}
      .dq-trend-head{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin:0 0 10px}
      .dq-trend-controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
      .dq-trend-controls select{min-height:34px;padding:5px 9px;border:1px solid var(--line);border-radius:6px;background:#fff;font-size:12px}
      .dq-period-toggle{display:flex;gap:4px;padding:3px;background:#eef3f8;border:1px solid var(--line);border-radius:7px}
      .dq-period-toggle button{border:0;background:transparent;color:var(--muted);padding:5px 10px;border-radius:5px;font-size:12px;font-weight:750;cursor:pointer}
      .dq-period-toggle button.active{background:#fff;color:var(--navy,var(--ink));box-shadow:0 1px 3px rgba(15,23,42,.10)}
      .dq-trend-legend{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px;font-size:12px}
      .dq-trend-legend span{display:inline-flex;align-items:center;gap:6px;color:var(--muted)}
      .dq-trend-legend i{width:10px;height:10px;border-radius:3px;display:inline-block}
      .dq-bars{display:grid;gap:8px;padding:16px;background:#fff;border:1px solid var(--line);border-radius:10px}
      .dq-bar-row{display:grid;grid-template-columns:110px 1fr 54px;gap:10px;align-items:center;font-size:12px}
      .dq-bar-track{background:#eef2f7;border-radius:5px;height:16px;overflow:hidden}
      .dq-bar-fill{height:100%;background:#1677ee;border-radius:5px;transition:width .2s}
      .dq-bar-row:hover .dq-bar-fill{background:#0f5fd6}
      .dq-bar-row:hover .dq-bar-track{box-shadow:0 0 0 1px #93c5fd}
    `;
    document.head.appendChild(style);
  }

  function statusClass(value, goodThreshold, warnThreshold, inverse = false) {
    const n = num(value);
    if (inverse) return n <= goodThreshold ? 'good' : n <= warnThreshold ? 'warn' : 'bad';
    return n >= goodThreshold ? 'good' : n >= warnThreshold ? 'warn' : 'bad';
  }

  function metricCard(value, label, note = '') {
    return `<div class="dq-card" data-metric-label="${escapeHtml(label)}"><strong>${value}</strong><span>${label}</span>${note ? `<small>${note}</small>` : ''}<button type="button" class="dq-metric-download" data-metric-label="${escapeHtml(label)}" title="Download the listings behind this number, with its metrics, as Excel">⬇ Excel</button></div>`;
  }

  function metricSlug(label) {
    return String(label || 'metric').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  }

  // A metric download hands over the ENTITIES the number was computed from -
  // one row per listing / error listing, with the flag columns the metric is
  // defined by - so the headline figure can be recomputed from the file. The
  // old client-side path exported a single summary line ("metric,value"),
  // which was not the underlying data at all. The server owns this now.
  // One click => exactly one request. The previous version created an <a>,
  // clicked it, then immediately removed it from the DOM - removing the
  // element while the browser was still resolving the download makes some
  // browsers re-issue the request, which is why a single click produced
  // several download attempts. Fetching the file once and saving the
  // resulting blob makes the request count observable and guaranteed.
  const metricDownloadsInFlight = new Set();

  async function downloadMetricEntities(label, filterIds, button) {
    const slug = metricSlug(label);
    if (metricDownloadsInFlight.has(slug)) return;  // guards double-clicks
    metricDownloadsInFlight.add(slug);
    const previousLabel = button ? button.innerHTML : '';
    if (button) { button.disabled = true; button.innerHTML = 'Preparing'; }
    const query = new URLSearchParams({ metric: slug });
    Object.entries(filterIds || {}).forEach(([key, id]) => {
      const node = $(id);
      if (!node) return;
      // A multi-select (e.g. 20 states) must send every selection, not just
      // the first - the export filters on membership, not equality.
      if (node.multiple) {
        [...node.selectedOptions].map((option) => option.value).filter(Boolean)
          .forEach((value) => query.append(key, value));
        return;
      }
      if (node.value) query.set(key, node.value);
    });
    try {
      const response = await fetch(`/api/reporting/metric-export?${query.toString()}`);
      if (!response.ok) {
        let message = 'Could not build this export.';
        try { message = (await response.json()).error || message; } catch (_) {}
        throw new Error(message);
      }
      // Filename comes from the server's Content-Disposition so the saved
      // file matches what the export actually contains.
      const disposition = response.headers.get('Content-Disposition') || '';
      const named = /filename="?([^"]+)"?/.exec(disposition);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = named ? named[1] : `${slug}.xlsx`;
      document.body.appendChild(link);
      link.click();
      // The blob is already in memory, so the anchor can go immediately -
      // unlike the old server-URL anchor, nothing is still being fetched.
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      const status = $('dqStatus') || $('reportStatus');
      if (status) {
        status.className = 'report-status error';
        status.textContent = error.message || 'Could not build this export.';
        status.classList.remove('hidden');
      }
    } finally {
      metricDownloadsInFlight.delete(slug);
      if (button) { button.disabled = false; button.innerHTML = previousLabel; }
    }
  }

  // One delegated listener - cards are re-rendered on every refresh, so
  // per-card listeners would leak and go stale. Covers both reporting tabs:
  // the quality cards and the location-intelligence cards, which previously
  // had no export at all.
  document.addEventListener('click', (event) => {
    const button = event.target.closest('.dq-metric-download, .report-metric-download');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    const label = button.dataset.metricLabel || 'metric';
    const isLocationTab = button.classList.contains('report-metric-download');
    downloadMetricEntities(label, isLocationTab
      ? { brand: 'reportMainBrandSelect', state: 'reportStateFilter' }
      : { brand: 'dqBrandFilter', state: 'dqStateFilter', reason: 'dqReasonFilter', status: 'dqStatusFilter', start_date: 'dqStartDate', end_date: 'dqEndDate' }, button);
  });

  function buildQualityPanel() {
    if ($('reportQualityPanel')) return $('reportQualityPanel');
    const panel = document.createElement('div');
    panel.id = 'reportQualityPanel';
    panel.className = 'reporting-tab-panel hidden';
    panel.innerHTML = `
      <div class="dq-layout"><aside class="dq-sidebar"><div class="dq-filters"><div class="dq-filter-field"><label for="dqBrandFilter">Primary Brand</label><select id="dqBrandFilter"><option value="">All impacted brands</option></select></div><div class="dq-filter-field"><label for="dqStateFilter">State</label><select id="dqStateFilter"><option value="">All impacted states</option></select></div><div class="dq-filter-field"><label for="dqReasonFilter">Issue Type</label><select id="dqReasonFilter"><option value="">All issue types</option></select></div><div class="dq-filter-field"><label for="dqStatusFilter">Review Status</label><select id="dqStatusFilter"><option value="all">All statuses</option><option value="needs_review">Needs review</option><option value="ai_fixed">AI fixed</option></select></div><div class="dq-filter-field"><label for="dqStartDate">From Date</label><input id="dqStartDate" type="date"></div><div class="dq-filter-field"><label for="dqEndDate">To Date</label><input id="dqEndDate" type="date"></div><div class="dq-filter-field"><label for="dqStaleDays">Stale after (days)</label><select id="dqStaleDays"><option value="1">1 day</option><option value="7">7 days</option><option value="30">30 days</option><option value="90" selected>90 days</option><option value="180">180 days</option><option value="365">365 days</option></select></div><button id="applyQualityFiltersBtn" type="button">Apply All Filters</button><button id="resetQualityFiltersBtn" class="secondary" type="button">Reset All</button></div></aside><main class="dq-main"><div class="dq-intro">
        <div><h2>Data Quality &amp; Improvements</h2><p>Focus on invalid listings, unresolved issues, and measurable improvement from automatic and manual fixes.</p></div>
      </div><div id="dqStatus" class="report-status hidden"></div><div id="dqLoadingPanel" class="dq-loading-panel hidden"><div class="dq-loading-box"><span class="spinner"></span><span>Loading quality metrics</span></div></div>
      <div id="dqBody" class="dq-body hidden">
        <div id="dqMetricGrid" class="dq-grid">${[['0','Invalid listings'],['0','Needs manual review'],['0','Listings fixed automatically'],['0','Listings fixed manually'],['0.00%','Unresolved rate'],['0.00%','ZIP completeness'],['0.00%','Coordinate completeness'],['0.00%','Duplicate rate'],['0','Stale records'],['0','Entity-resolution attempts'],['0.00%','Entity-resolution success'],['0','Active issue types']].map(([value,label]) => metricCard(value,label)).join('')}</div>
        <div class="dq-section"><h3>Quality Signals</h3><div id="dqSignals"></div></div>
        <div class="dq-section"><h3>Issue Type Breakdown</h3><div id="dqReasonsChart"></div></div>
        <div class="dq-section"><h3>Fix State by Failure Field</h3><div id="dqFixStatePivot"></div></div>
        <div class="dq-section"><h3>Improvement Opportunities</h3><div id="dqImprovements" class="dq-improvements-list"></div></div>
        <div class="dq-section"><h3>Quality by Brand</h3><div id="dqBrandTable"></div></div>
        <div class="dq-section"><h3>Most Impacted States and Cities</h3><div id="dqGeoTables" class="dq-improvements"></div></div>
        <div class="dq-section"><h3>Reconciliation</h3><div id="dqReconciliation"></div></div>
        <div class="dq-section"><h3>Historical Quality &amp; Change Tracking</h3><div class="dq-history-grid"><div id="dqHistoryChart" class="dq-history-chart"><div class="report-status">No historical points yet.</div></div><div id="dqPeriodComparisons"><div class="dq-period-row"><span>Last 1 month</span><strong>0 records</strong></div><div class="dq-period-row"><span>Last quarter</span><strong>0 records</strong></div><div class="dq-period-row"><span>Last year</span><strong>0 records</strong></div><div class="dq-period-row"><span>YoY</span><strong>0 records</strong></div></div></div></div>
      </div></main></div>
    `;
    return panel;
  }

  // RPT-08's pivot: the four fix states against the field each row failed
  // on. Replaces the single-dimension pie as the primary breakdown.
  function renderFixStatePivot(rows) {
    const container = $('dqFixStatePivot');
    if (!container) return;
    const data = Array.isArray(rows) ? rows : [];
    if (!data.length) {
      container.innerHTML = '<div class="report-status" style="padding:12px 0;font-size:13px;">No fix-state data recorded yet.</div>';
      return;
    }
    const columns = [
      ['ai_fixed', 'Fixed with AI'],
      ['ai_review_pending', 'AI review pending'],
      ['manual_fixed', 'Manually fixed'],
      ['manual_review_pending', 'Manual review pending'],
    ];
    const totals = columns.map(([key]) => data.reduce((sum, row) => sum + num(row[key]), 0));
    const grand = totals.reduce((a, b) => a + b, 0);
    container.innerHTML = `<table class="dq-table"><thead><tr><th>Failure field</th>${columns.map(([, label]) => `<th style="text-align:right">${label}</th>`).join('')}<th style="text-align:right">Total</th></tr></thead><tbody>${
      data.map((row) => `<tr><td>${escapeHtml(formatIssue(row.reason))}</td>${columns.map(([key]) => `<td style="text-align:right;font-variant-numeric:tabular-nums">${fmt(num(row[key]))}</td>`).join('')}<td style="text-align:right;font-weight:700;font-variant-numeric:tabular-nums">${fmt(num(row.total))}</td></tr>`).join('')
    }</tbody><tfoot><tr><td style="font-weight:700">All fields</td>${totals.map((value) => `<td style="text-align:right;font-weight:700;font-variant-numeric:tabular-nums">${fmt(value)}</td>`).join('')}<td style="text-align:right;font-weight:700;font-variant-numeric:tabular-nums">${fmt(grand)}</td></tr></tfoot></table>`;
  }

  function renderReasonsDonut(containerId, buckets) {
    const container = $(containerId);
    if (!container) return;
    container.innerHTML = '';
    const COLORS = ['#3b82f6','#f59e0b','#10b981','#ef4444','#8b5cf6','#06b6d4','#f97316','#ec4899'];
    const active = (buckets || []).filter((b) => num(b.count) > 0);
    const total = active.reduce((s, b) => s + num(b.count), 0);
    if (!total) {
      container.innerHTML = '<div class="report-status" style="padding:12px 0;font-size:13px;">No validation issues recorded — data looks clean.</div>';
      return;
    }
    if (!hasD3()) {
      container.innerHTML = '<div class="report-status">Charting library failed to load. Refresh the page to try again.</div>';
      return;
    }
    const d3 = window.d3;
    const top = active.slice(0, 8);
    const otherCount = active.slice(8).reduce((s, b) => s + num(b.count), 0);
    const slices = (otherCount > 0 ? [...top, { reason: 'other_issues', count: otherCount }] : top)
      .map((slice, i) => ({ ...slice, color: i < COLORS.length ? COLORS[i] : '#94a3b8', value: num(slice.count) }));

    const shell = document.createElement('div');
    shell.style.cssText = 'display:grid;grid-template-columns:320px minmax(0,1fr);gap:32px;align-items:center;padding:24px 28px;background:#fff;border:1px solid var(--line);border-radius:10px;position:relative;';
    const chartHost = document.createElement('div');
    chartHost.style.cssText = 'position:relative;';
    const legendHost = document.createElement('div');
    legendHost.style.cssText = 'display:grid;gap:2px;';
    shell.appendChild(chartHost);
    shell.appendChild(legendHost);
    container.appendChild(shell);

    const size = 280, radius = size / 2, inner = radius * 0.58;
    const svg = d3.select(chartHost).append('svg')
      .attr('viewBox', `0 0 ${size} ${size}`)
      .attr('width', '100%')
      .attr('height', size)
      .attr('role', 'img')
      .attr('aria-label', 'Issue type breakdown');
    const g = svg.append('g').attr('transform', `translate(${radius},${radius})`);
    const arcs = d3.pie().sort(null).value((d) => d.value)(slices);
    const arc = d3.arc().innerRadius(inner).outerRadius(radius - 4);
    const arcHover = d3.arc().innerRadius(inner).outerRadius(radius);
    const tip = chartTooltip(shell);

    const setActive = (index, on) => {
      g.selectAll('path.dq-donut-slice')
        .filter((d) => d.index === index)
        .transition().duration(120)
        .attr('d', on ? arcHover : arc);
      legendHost.querySelectorAll('.dq-donut-legend-row').forEach((row) => {
        if (Number(row.dataset.slice) === index) row.style.background = on ? '#f1f5f9' : 'transparent';
      });
    };

    g.selectAll('path').data(arcs).enter().append('path')
      .attr('class', 'dq-donut-slice')
      .attr('d', arc)
      .attr('fill', (d) => d.data.color)
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .style('cursor', 'pointer')
      .on('mouseenter', (event, d) => {
        setActive(d.index, true);
        tip.show(`<strong>${escapeHtml(formatIssue(d.data.reason))}</strong><br>${fmt(d.data.value)} (${(d.data.value * 100 / total).toFixed(1)}%)`, event);
      })
      .on('mousemove', (event, d) => {
        tip.show(`<strong>${escapeHtml(formatIssue(d.data.reason))}</strong><br>${fmt(d.data.value)} (${(d.data.value * 100 / total).toFixed(1)}%)`, event);
      })
      .on('mouseleave', (event, d) => { setActive(d.index, false); tip.hide(); });

    g.append('text').attr('text-anchor', 'middle').attr('y', -4)
      .attr('font-size', 28).attr('font-weight', 800).attr('fill', 'var(--navy,#172554)')
      .text(fmt(total));
    g.append('text').attr('text-anchor', 'middle').attr('y', 16)
      .attr('font-size', 11).attr('fill', '#64748b').text('total issues');

    // Legend rows are a real 4-column grid (swatch | label | count |
    // percent) so the numbers line up in their own columns, and each row is
    // hover-linked to its slice.
    legendHost.innerHTML = slices.map((slice, i) => `<div class="dq-donut-legend-row" data-slice="${i}" style="display:grid;grid-template-columns:14px minmax(0,1fr) auto 56px;align-items:center;gap:10px;font-size:13px;padding:7px 8px;border-radius:6px;cursor:pointer;transition:background 120ms ease;"><span style="width:12px;height:12px;border-radius:3px;background:${slice.color};"></span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink);">${escapeHtml(formatIssue(slice.reason))}</span><strong style="color:var(--navy,var(--ink));font-size:13px;font-variant-numeric:tabular-nums;text-align:right;">${fmt(slice.value)}</strong><span style="color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums;text-align:right;">${(slice.value * 100 / total).toFixed(1)}%</span></div>`).join('');
    legendHost.querySelectorAll('.dq-donut-legend-row').forEach((row) => {
      const index = Number(row.dataset.slice);
      row.addEventListener('mouseenter', () => setActive(index, true));
      row.addEventListener('mouseleave', () => setActive(index, false));
    });
  }

  function renderQualityHistory(history = [], current = {}) {
    const chart = $('dqHistoryChart');
    const comparisons = $('dqPeriodComparisons');
    if (!chart || !comparisons) return;
    const points = history.slice(-30);
    if (!points.length) {
      chart.innerHTML = '<div class="report-status">A historical point will be recorded after the first quality refresh.</div>';
      comparisons.innerHTML = '<div class="report-status">No period comparison is available yet.</div>';
      return;
    }
    // Same d3 helper as Trends Over Time, so both charts behave identically
    // (real axes, a hoverable point per snapshot, tooltips).
    renderTimeSeriesChart(chart, [{
      label: 'Invalid records',
      color: '#1677ee',
      points: points.map((point) => ({ date: point.snapshot_date, count: num(point.invalid_records) })),
    }], {
      height: 260,
      ariaLabel: 'Invalid listing history',
      emptyMessage: 'A historical point will be recorded after the first quality refresh.',
    });
    const latest = points[points.length - 1] || current;
    const latestTime = Date.parse(`${latest.snapshot_date}T00:00:00Z`);
    comparisons.innerHTML = [[30, 'Last 1 month'], [91, 'Last quarter'], [365, 'Last year'], [730, 'YoY']].map(([days, label]) => {
      const prior = [...points].reverse().find((point) => latestTime - Date.parse(`${point.snapshot_date}T00:00:00Z`) >= days * 86400000);
      const delta = num(latest.invalid_records) - num(prior?.invalid_records ?? latest.invalid_records);
      return `<div class="dq-period-row"><span>${label}</span><strong>${delta > 0 ? '+' : ''}${fmt(delta)} invalid records</strong></div>`;
    }).join('');
  }

  function renderExtraMetrics(totals = {}, gapsCount = 0) {
    const grid = $('dqExtraGrid');
    if (!grid) return;
    grid.innerHTML = [
      metricCard(fmt(totals.total_locations), 'Total mapped locations'),
      metricCard(fmt(totals.active_market_locations), 'Active market locations'),
      metricCard(fmt(totals.total_brands), 'Brands tracked'),
      metricCard(fmt(totals.total_stores), 'Total stores'),
      metricCard(fmt(totals.total_states), 'States covered'),
      metricCard(fmt(totals.total_cities), 'Cities covered'),
      metricCard(fmt(totals.total_zips), 'ZIP codes covered'),
      metricCard(fmt(gapsCount), 'Whitespace ZIPs (no brand presence)')
    ].join('');
  }

  // Per RPT-05, the legend is never brands - fixed colors per metric
  // dimension so "Locations" (say) is always the same color across period
  // changes, unlike the old per-brand palette which reassigned colors
  // whenever the set of brands in view changed.
  const TREND_METRIC_COLORS = { 'Locations': '#1677ee', 'Errors': '#ef4444', 'AI Fixed': '#10b981', 'Manual Fixed': '#8b5cf6' };

  function renderTrendChart(series = []) {
    const chart = $('dqTrendChart');
    const legend = $('dqTrendLegend');
    if (!chart || !legend) return;
    const withColor = (series || []).map((s) => ({ ...s, color: TREND_METRIC_COLORS[s.label] || '#64748b' }));
    renderTimeSeriesChart(chart, withColor, {
      height: 340,
      ariaLabel: 'Trends over time',
      emptyMessage: 'No trend data for this period yet.',
    });
    const active = withColor.filter((s) => Array.isArray(s.points) && s.points.length);
    legend.innerHTML = active.map((s) => `<span><i style="background:${s.color}"></i>${escapeHtml(s.label)}</span>`).join('');
  }

  function renderTopStatesBar(states = []) {
    const container = $('dqTopStatesBar');
    if (!container) return;
    container.innerHTML = '';
    // top_states rows (from reporting_summary()/the gold mirror) carry the
    // ZIP-coverage count as "locations" - "zip_count"/"count" never existed
    // on this payload, so this always evaluated to 0 for every row.
    const rows = (states || []).slice(0, 10).map((row) => ({
      label: row.state_name || row.state || 'Unknown',
      value: num(row.locations),
    })).filter((row) => row.value > 0);
    if (!rows.length) {
      container.innerHTML = '<div class="report-status" style="padding:12px 0;font-size:13px;">No state coverage data available yet.</div>';
      return;
    }
    if (!hasD3()) {
      container.innerHTML = '<div class="report-status">Charting library failed to load. Refresh the page to try again.</div>';
      return;
    }
    const d3 = window.d3;
    const rowH = 34;
    const margin = { top: 8, right: 64, bottom: 24, left: 132 };
    // clientWidth is 0 while the panel is still hidden (this renders before
    // the tab is shown). The old Math.max(360, 0 || 900) produced a 900px
    // viewBox that the browser then scaled up to the real width - which is
    // why the bars appeared as one oversized solid block. Wait for a real
    // width instead of guessing one.
    if (!container.clientWidth) {
      if (typeof ResizeObserver === 'function' && !container.dataset.awaitingWidth) {
        container.dataset.awaitingWidth = '1';
        const observer = new ResizeObserver(() => {
          if (container.clientWidth) {
            observer.disconnect();
            delete container.dataset.awaitingWidth;
            renderTopStatesBar(states);
          }
        });
        observer.observe(container);
      }
      return;
    }
    delete container.dataset.awaitingWidth;
    const width = container.clientWidth;
    const innerW = Math.max(40, width - margin.left - margin.right);
    const height = rows.length * rowH + margin.top + margin.bottom;

    const svg = d3.select(container).append('svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('width', '100%')
      .attr('height', height)
      .attr('role', 'img')
      .attr('aria-label', 'Top states by coverage');
    const g = svg.append('g').attr('transform', `translate(${margin.left},${margin.top})`);
    const x = d3.scaleLinear().domain([0, d3.max(rows, (r) => r.value) || 1]).nice().range([0, innerW]);
    const y = d3.scaleBand().domain(rows.map((r) => r.label)).range([0, rows.length * rowH]).padding(0.28);
    const tip = chartTooltip(container);

    g.append('g').call(d3.axisLeft(y).tickSize(0))
      .call((sel) => sel.select('.domain').remove())
      .selectAll('text').attr('fill', 'var(--ink)').attr('font-size', 13);
    g.append('g').attr('transform', `translate(0,${rows.length * rowH})`)
      .call(d3.axisBottom(x).ticks(5).tickFormat((v) => fmt(v)))
      .selectAll('text').attr('fill', '#64748b').attr('font-size', 11);
    g.selectAll('.domain').attr('stroke', '#cbd5e1');

    g.selectAll('rect.dq-bar-track').data(rows).enter().append('rect')
      .attr('class', 'dq-bar-track')
      .attr('x', 0).attr('y', (r) => y(r.label))
      .attr('width', innerW).attr('height', y.bandwidth())
      .attr('rx', 5).attr('fill', '#eef2f7').attr('stroke', '#e2e8f0');
    g.selectAll('rect.dq-bar-fill').data(rows).enter().append('rect')
      .attr('class', 'dq-bar-fill')
      .attr('x', 0).attr('y', (r) => y(r.label))
      // One flat blue for every bar against a near-identical track made the
      // chart read as a single block. A sequential ramp keeps the ranking
      // legible at a glance and separates each bar from its neighbour.
      .attr('height', y.bandwidth()).attr('rx', 5)
      .attr('fill', (r, i) => d3.interpolateBlues(0.85 - (i / Math.max(rows.length - 1, 1)) * 0.45))
      .style('cursor', 'pointer')
      .attr('width', 0)
      .on('mouseenter', function (event, r) {
        d3.select(this).attr('fill', '#1d4ed8');
        tip.show(`<strong>${escapeHtml(r.label)}</strong><br>${fmt(r.value)} ZIPs covered`, event);
      })
      .on('mousemove', (event, r) => tip.show(`<strong>${escapeHtml(r.label)}</strong><br>${fmt(r.value)} ZIPs covered`, event))
      .on('mouseleave', function (event, r) {
        const index = rows.indexOf(r);
        d3.select(this).attr('fill', d3.interpolateBlues(0.85 - (index / Math.max(rows.length - 1, 1)) * 0.45));
        tip.hide();
      })
      .transition().duration(450)
      .attr('width', (r) => Math.max(2, x(r.value)));
    g.selectAll('text.dq-bar-value').data(rows).enter().append('text')
      .attr('class', 'dq-bar-value')
      .attr('x', (r) => Math.max(2, x(r.value)) + 8)
      .attr('y', (r) => y(r.label) + y.bandwidth() / 2 + 4)
      .attr('font-size', 12).attr('font-weight', 700).attr('fill', 'var(--ink)')
      .style('font-variant-numeric', 'tabular-nums')
      .text((r) => fmt(r.value));
  }

  let trendState = { period: '1M' };

  async function loadTrendChart() {
    const chart = $('dqTrendChart');
    if (chart) chart.innerHTML = '<div class="report-status">Loading trend data&hellip;</div>';
    try {
      let qs = '';
      try { if (typeof window.reportingQueryString === 'function') qs = window.reportingQueryString(); } catch (_) {}
      const p = new URLSearchParams(qs);
      p.set('period', trendState.period);
      const res = await fetch(`/api/reporting/timeseries?${p.toString()}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Unable to load trend data.');
      renderTrendChart(Array.isArray(data.series) ? data.series : []);
    } catch (err) {
      if (chart) chart.innerHTML = `<div class="report-status">${escapeHtml(typeof productSafeError === 'function' ? productSafeError(err.message, 'Trend data is temporarily unavailable.') : 'Trend data is temporarily unavailable.')}</div>`;
    }
  }

  async function loadExtendedMetrics() {
    const grid = $('dqExtraGrid');
    const bars = $('dqTopStatesBar');
    try {
      let qs = '';
      try { if (typeof window.reportingQueryString === 'function') qs = window.reportingQueryString(); } catch (_) {}
      const res = await fetch(`/api/reporting/summary${qs ? `?${qs}` : ''}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Unable to load coverage metrics.');
      renderExtraMetrics(data.totals || {}, Array.isArray(data.gaps) ? data.gaps.length : 0);
      renderTopStatesBar(Array.isArray(data.top_states) ? data.top_states : []);
    } catch (err) {
      const message = typeof productSafeError === 'function' ? productSafeError(err.message, 'Coverage metrics are temporarily unavailable.') : 'Coverage metrics are temporarily unavailable.';
      if (grid) grid.innerHTML = `<div class="report-status">${escapeHtml(message)}</div>`;
      if (bars) bars.innerHTML = `<div class="report-status">${escapeHtml(message)}</div>`;
    }
    loadTrendChart();
  }

  let qualityWarmupRetries = 0;
  // A warm-but-stale cache is served immediately while the real numbers are
  // recomputed in a background thread. Nothing used to ask for the result,
  // so the donut and the fix counters kept showing the cached figures
  // indefinitely ("still outdated after 5 minutes on the page"). Re-fetch
  // once, quietly, after the background pass has had time to land.
  let qualityStaleRefetches = 0;
  const QUALITY_STALE_REFETCH_LIMIT = 3;
  const QUALITY_STALE_REFETCH_DELAY_MS = 6000;
  async function loadQuality(forceRefresh = false) {
    const status = $('dqStatus');
    if (!status) return;
    const loadingPanel = $('dqLoadingPanel');
    const body = $('dqBody');
    // Both first load and a shared-refresh fully hide the body behind the
    // spinner - the tab switcher itself stays clickable throughout, this
    // only hides this panel's own content while its data is in flight.
    if (loadingPanel) loadingPanel.classList.remove('hidden');
    if (body) body.classList.add('hidden');
    status.className = 'report-status hidden';
    status.textContent = '';
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
      [['brand', 'dqBrandFilter'], ['state', 'dqStateFilter'], ['reason', 'dqReasonFilter'], ['status', 'dqStatusFilter'], ['start_date', 'dqStartDate'], ['end_date', 'dqEndDate']].forEach(([key, id]) => { const node = $(id); if (node?.value) qualityParams.set(key, node.value); });
      const res = await fetch(`/api/reporting/quality${qualityParams.toString() ? `?${qualityParams}` : ''}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Unable to load quality metrics.');
      // A cold cache returns this placeholder immediately while the real
      // aggregation runs in the background (previously the request itself
      // blocked for 30+ seconds) - keep the spinner up and poll again
      // shortly rather than rendering the all-zero shape as real data.
      if (data.quality_cache === 'warming') {
        qualityWarmupRetries += 1;
        if (qualityWarmupRetries <= 40) {
          window.setTimeout(() => loadQuality(forceRefresh), 3000);
          return;
        }
        // Retry budget exhausted (~2 minutes) - this is now rare (the
        // cache is only ever this cold right after a server restart,
        // see invalidate_cache()'s reporting_quality exemption), but if it
        // happens, say so honestly instead of quietly rendering the
        // all-zero placeholder as if it were the real, final answer.
        qualityWarmupRetries = 0;
        if (loadingPanel) loadingPanel.classList.add('hidden');
        if (body) body.classList.remove('hidden');
        status.className = 'report-status error';
        status.textContent = 'Quality metrics are taking longer than usual to prepare. Try refreshing in a moment.';
        return;
      }
      qualityWarmupRetries = 0;
      if (data.refreshing && qualityStaleRefetches < QUALITY_STALE_REFETCH_LIMIT) {
        // Render what we have now (never leave the panel blank), then pick
        // up the fresh numbers when the background pass finishes.
        qualityStaleRefetches += 1;
        window.setTimeout(() => loadQuality(false), QUALITY_STALE_REFETCH_DELAY_MS);
      } else if (!data.refreshing) {
        qualityStaleRefetches = 0;
      }
      const q = data.metrics || {};
      const raw = num(q.invalid_listings);
      const needsReview = num(q.needs_manual_review);
      const aiFixed = num(q.ai_fixed);
      const manualFixed = num(q.manual_fixed);
      const unresolvedRate = num(q.unresolved_rate_pct);
      const zipCompleteness = num(q.zip_completeness_pct);
      const coordinateCompleteness = num(q.coordinate_completeness_pct);
      const duplicateRate = num(q.duplicate_rate_pct);
      const staleRecords = num(q.stale_records);
      const entityAttempts = num(q.entity_resolution_attempts);
      const entitySuccess = num(q.entity_resolution_success_rate_pct);
      const reasons = Array.isArray(data.reasons) ? data.reasons : [];
      const states = Array.isArray(data.states) ? data.states : [];
      const cities = Array.isArray(data.cities) ? data.cities : [];
      [['dqBrandFilter', data.filters?.brands || [], 'All impacted brands'], ['dqStateFilter', data.filters?.states || [], 'All impacted states'], ['dqReasonFilter', data.filters?.reasons || [], 'All issue types']].forEach(([id, values, label]) => {
        const node = $(id); if (!node) return; const previous = node.value;
        node.innerHTML = `<option value="">${label}</option>${values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(formatIssue(value))}</option>`).join('')}`;
        if (values.includes(previous)) node.value = previous;
      });

      // Same INV-15 reasoning as the Quality Signals table below: the
      // coverage-derived cards are zeroed defaults when the coverage query
      // returned nothing, so show "—" rather than a fabricated 0.0%.
      const coverageMeasured = num(q.total_records) > 0;
      // RPT-08: the four fix states first, each with its share, then the
      // rest of the quality figures.
      const aiPending = num(q.ai_review_pending);
      const manualPending = num(q.manual_review_pending);
      $('dqMetricGrid').innerHTML = [
        metricCard(fmt(aiFixed), 'Fixed with AI', pct(num(q.ai_fixed_share_pct))),
        metricCard(fmt(aiPending), 'AI review pending', pct(num(q.ai_review_pending_share_pct))),
        metricCard(fmt(manualFixed), 'Manually fixed', pct(num(q.manual_fixed_share_pct))),
        metricCard(fmt(manualPending), 'Manual review pending', pct(num(q.manual_review_pending_share_pct))),
        metricCard(fmt(raw), 'Invalid listings', 'Active validation and review population'),
        metricCard(fmt(needsReview), 'Needs manual review'),
        metricCard(pct(unresolvedRate), 'Unresolved rate'),
        metricCard(coverageMeasured ? pct(zipCompleteness) : '—', 'ZIP completeness'),
        metricCard(coverageMeasured ? pct(coordinateCompleteness) : '—', 'Coordinate completeness'),
        metricCard(coverageMeasured ? pct(duplicateRate) : '—', 'Duplicate rate'),
        metricCard(coverageMeasured ? fmt(staleRecords) : '—', 'Stale records'),
        metricCard(entityAttempts ? fmt(entityAttempts) : '—', 'Entity-resolution attempts'),
        metricCard(entityAttempts ? pct(entitySuccess) : '—', 'Entity-resolution success'),
        metricCard(fmt(reasons.length), 'Active issue types')
      ].join('');

      const hasData = raw > 0 || needsReview > 0 || aiFixed > 0 || manualFixed > 0 || reasons.length > 0;

      const signals = [
        ['Manual review queue', fmt(needsReview), hasData ? (needsReview ? 'bad' : 'good') : 'neutral'],
        ['Unresolved rate', hasData ? pct(unresolvedRate) : '—', hasData ? statusClass(unresolvedRate, 5, 20, true) : 'neutral'],
        ['Automatic fixes', fmt(aiFixed), hasData ? (aiFixed ? 'good' : 'warn') : 'neutral'],
        ['Manual fixes', fmt(manualFixed), hasData ? (manualFixed ? 'good' : 'warn') : 'neutral'],
        ['Issue categories', fmt(reasons.length), hasData ? (reasons.length ? 'warn' : 'good') : 'neutral']
      ];
      // These are all derived from the coverage query's totals - when that
      // returned nothing, total_records is 0 and every rate below is a
      // zeroed *default*, not a real measurement. Rendering "0.0% - Needs
      // attention" (or worse, "0.0% - Healthy") for a metric that was
      // never actually measured is fabricated data (INV-15); show the same
      // honest "—" / "No data" that Entity resolution already uses.
      const totalRecords = num(q.total_records);
      signals.push(
        ['ZIP completeness', totalRecords ? pct(zipCompleteness) : '—', !totalRecords ? 'neutral' : zipCompleteness >= 95 ? 'good' : zipCompleteness >= 80 ? 'warn' : 'bad'],
        ['Coordinate completeness', totalRecords ? pct(coordinateCompleteness) : '—', !totalRecords ? 'neutral' : coordinateCompleteness >= 95 ? 'good' : coordinateCompleteness >= 80 ? 'warn' : 'bad'],
        ['Duplicate rate', totalRecords ? pct(duplicateRate) : '—', !totalRecords ? 'neutral' : duplicateRate <= 2 ? 'good' : duplicateRate <= 8 ? 'warn' : 'bad'],
        ['Stale records', totalRecords ? fmt(staleRecords) : '—', !totalRecords ? 'neutral' : staleRecords ? 'warn' : 'good'],
        ['Entity resolution success', entityAttempts ? pct(entitySuccess) : '—', entityAttempts ? (entitySuccess >= 60 ? 'good' : 'warn') : 'neutral']
      );
      $('dqSignals').innerHTML = `<table class="dq-table"><thead><tr><th>Signal</th><th>Current</th><th>Status</th></tr></thead><tbody>${signals.map(([name,val,cls]) => `<tr><td>${name}</td><td>${val}</td><td><span class="dq-status ${cls}">${cls === 'good' ? 'Healthy' : cls === 'warn' ? 'Review' : cls === 'bad' ? 'Needs attention' : 'No data'}</span></td></tr>`).join('')}</tbody></table>`;

      renderReasonsDonut('dqReasonsChart', reasons.filter((b) => num(b.count) > 0));
      renderFixStatePivot(data.fix_state_pivot);

      const brandRows = Array.isArray(data.brands) ? data.brands : [];
      $('dqBrandTable').innerHTML = `<table class="dq-table"><thead><tr><th>Brand</th><th>Invalid</th><th>Needs review</th><th>AI fixed</th></tr></thead><tbody>${brandRows.length ? brandRows.map((brand) => `<tr><td>${escapeHtml(formatBrandName(brand.brand))}</td><td>${fmt(brand.invalid)}</td><td>${fmt(brand.needs_review)}</td><td>${fmt(brand.ai_enriched)}</td></tr>`).join('') : '<tr><td colspan="4">No invalid brand records are available for this filter.</td></tr>'}</tbody></table>`;
      // Full state names, not the raw 2-letter code stored on the row -
      // stateCodeToName is already defined globally in reporting.js.
      const stateLabel = (code) => (typeof stateCodeToName === 'object' && stateCodeToName[String(code).toUpperCase()]) || code || 'Unknown';
      $('dqGeoTables').innerHTML = `<div><table class="dq-table"><thead><tr><th>State</th><th>Invalid listings</th></tr></thead><tbody>${states.slice(0, 10).map((row) => `<tr><td>${escapeHtml(stateLabel(row.state))}</td><td>${fmt(row.count)}</td></tr>`).join('') || '<tr><td colspan="2">No impacted states.</td></tr>'}</tbody></table></div><div><table class="dq-table"><thead><tr><th>City</th><th>Invalid listings</th></tr></thead><tbody>${cities.slice(0, 10).map((row) => `<tr><td>${escapeHtml(row.city)}</td><td>${fmt(row.count)}</td></tr>`).join('') || '<tr><td colspan="2">No impacted cities.</td></tr>'}</tbody></table></div>`;

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
        <tr><td>Change history</td><td>${fmt((data.history || []).length)} snapshots</td><td>Daily quality points are retained for period comparisons.</td></tr>
      </tbody></table>`;
      renderQualityHistory(data.history || [], q);

      if (loadingPanel) loadingPanel.classList.add('hidden');
      if (body) body.classList.remove('hidden');
      status.className = 'report-status hidden';
      status.textContent = '';
    } catch (err) {
      if (loadingPanel) loadingPanel.classList.add('hidden');
      if (body) body.classList.remove('hidden');
      status.className = 'report-status error';
      status.textContent = typeof productSafeError === 'function'
        ? productSafeError(err.message, 'Quality metrics are temporarily unavailable. Please try again.')
        : 'Quality metrics are temporarily unavailable. Please try again.';
    } finally {
      if (forceRefresh && status.className !== 'report-status error') { status.className = 'report-status hidden'; status.textContent = ''; }
      const reportingView = $('reportingView');
      if (reportingView) {
        const shell = reportingView.querySelector('.report-shell');
        if (shell) {
          const activeTab = sessionStorage.getItem('reportingInnerTab') === 'quality' ? 'quality' : 'location';
          shell.querySelectorAll('.report-location-panel').forEach((n) => n.classList.toggle('hidden', activeTab !== 'location'));
          const quality = $('reportQualityPanel');
          if (quality) quality.classList.toggle('hidden', activeTab !== 'quality');
          const tabs = $('reportingInnerTabs');
          if (tabs) tabs.querySelectorAll('[data-report-tab]').forEach((b) => b.classList.toggle('active', b.dataset.reportTab === activeTab));
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
      const nextTab = name === 'quality' ? 'quality' : 'location';
      try { sessionStorage.setItem('reportingInnerTab', nextTab); } catch (_) {}
      tabs.querySelectorAll('[data-report-tab]').forEach((b) => b.classList.toggle('active', b.dataset.reportTab === name));
      shell.querySelectorAll('.report-location-panel').forEach((n) => n.classList.toggle('hidden', name !== 'location'));
      quality.classList.toggle('hidden', name !== 'quality');
      if (name === 'quality') loadQuality();
      if (name === 'location') {
        // Extended Coverage Metrics / Trends Over Time / Top States now live
        // on this tab (RPT-05/06/07) and read the summary + timeseries
        // endpoints, so they load with it rather than with the quality tab.
        loadExtendedMetrics();
        if (typeof window.reportingMap?.invalidateSize === 'function') setTimeout(() => window.reportingMap.invalidateSize(), 100);
      }
    }

    tabs.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-report-tab]');
      if (btn) switchTab(btn.dataset.reportTab);
    });
    $('dqTrendPeriod')?.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-period]');
      if (!btn) return;
      trendState.period = btn.dataset.period;
      $('dqTrendPeriod').querySelectorAll('[data-period]').forEach((b) => b.classList.toggle('active', b === btn));
      loadTrendChart();
    });
    $('applyQualityFiltersBtn')?.addEventListener('click', loadQuality);
    // Stale-after-days is a persisted setting, not a per-view filter: load
    // the saved value, and save + recompute whenever it's changed.
    (async () => {
      try {
        const res = await fetch('/api/settings');
        const data = await res.json();
        if (res.ok && $('dqStaleDays') && data.stale_after_days) $('dqStaleDays').value = String(data.stale_after_days);
      } catch (_) {}
    })();
    $('dqStaleDays')?.addEventListener('change', async (e) => {
      try {
        await fetch('/api/settings', {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({ stale_after_days: Number(e.target.value) })
        });
      } catch (_) {}
      loadQuality(true);
    });
    $('resetQualityFiltersBtn')?.addEventListener('click', () => {
      ['dqBrandFilter', 'dqStateFilter', 'dqReasonFilter', 'dqStatusFilter', 'dqStartDate', 'dqEndDate'].forEach((id) => {
        const node = $(id);
        if (node) node.value = id === 'dqStatusFilter' ? 'all' : '';
      });
      loadQuality();
    });
    let initialTab = 'location';
    try {
      const requestedTab = new URLSearchParams(window.location.search).get('reportTab');
      initialTab = requestedTab === 'quality' ? 'quality' : (sessionStorage.getItem('reportingInnerTab') === 'quality' ? 'quality' : 'location');
    } catch (_) {}
    switchTab(initialTab);
    // Exposed so the single Reporting-hero "Refresh Report" button can
    // refresh this tab's data too, whether or not it's the active one -
    // there is no separate refresh control on this panel any more.
    window.reportingRefreshQuality = () => loadQuality(true);
    // A fresh nav click into Reporting (as opposed to a page refresh while
    // already on it) should always land on the first inner tab - exposed so
    // switchView() (common.js) can call it without reaching into this
    // module's closured switchTab().
    window.reportingResetToLocationTab = () => switchTab('location');
    return true;
  }

  let attempts = 0;
  const timer = setInterval(() => {
    attempts += 1;
    if (init() || attempts > 80) clearInterval(timer);
  }, 250);
})();
