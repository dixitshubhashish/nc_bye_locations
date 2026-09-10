(() => {
  const $ = (id) => document.getElementById(id);
  const num = (v) => Number.isFinite(Number(v)) ? Number(v) : 0;
  const fmt = (v) => num(v).toLocaleString();
  const pct = (v) => `${num(v).toFixed(1)}%`;
  const formatIssue = (value) => String(value || '').replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
  // Full state names, not the raw 2-letter code stored on the row -
  // stateCodeToName is already defined globally in reporting.js. Module level
  // because the State filter and the impacted-states table both label states,
  // and the Location rail's State dropdown reads "California", not "CA".
  const stateLabel = (code) => (typeof stateCodeToName === 'object' && stateCodeToName[String(code).toUpperCase()]) || code || 'Unknown';

  // This rail's long selects are searched by the SAME component as the
  // Location rail's and the brand pickers': attachSearchableSelect from
  // common.js. With 1,002 brands in the warehouse a bare <select> is
  // unusable, and a second local implementation is how the two tabs ended
  // up searching differently in the first place.
  const QUALITY_SEARCHABLE_FILTERS = ['dqBrandFilter', 'dqStateFilter', 'dqCountyFilter', 'dqCityFilter', 'dqReasonFilter'];
  // MUST run immediately after loadQuality() rewrites those selects. The
  // component re-reads and caches the option list on every call, so a
  // rebuild without a re-attach leaves the search filtering options the
  // control no longer holds - the BB9/BB10 staleness, where a newly created
  // brand was invisible to the search because the cache predated it.
  const refreshQualityFilterSearch = () => {
    if (typeof attachSearchableSelect !== 'function') return;
    QUALITY_SEARCHABLE_FILTERS.forEach((id) => attachSearchableSelect(id, { threshold: 15, minChars: 1 }));
  };

  // This rail's Geographic Filters ARE the Location rail's: the same four
  // cascading controls, loaded by the same loadGeoOptions(), searched by the
  // same component, and typed into by the same setupZipTypeahead() - both in
  // js/reporting.js. This object is the whole of the difference between the
  // two rails: it names which ids that shared code should read and write
  // here. Nothing about the cascade is reimplemented below, deliberately -
  // the two tabs' geographic filters diverged precisely because they were
  // written twice.
  //
  // ownsStateOptions is false because loadQuality() fills State from the
  // quality response's own list of states that actually have issues ("All
  // impacted states"); the shared cascade reads that select to scope
  // counties, but must not overwrite it with the full 50-state reference
  // list. County/City/ZIP have no impacted-only equivalent to preserve, so
  // they come straight from the shared reference data, exactly as on tab 1.
  const QUALITY_GEO_RAIL = {
    state: 'dqStateFilter',
    county: 'dqCountyFilter',
    city: 'dqCityFilter',
    zip: 'dqZipFilter',
    zipList: 'dqZipSuggestions',
    ownsStateOptions: false,
    onOptionsRebuilt: () => refreshQualityFilterSearch(),
  };
  // Guarded because reporting-tabs.js is loaded independently of
  // js/reporting.js; every other cross-file call in this file is guarded the
  // same way.
  const loadQualityGeoOptions = () => (typeof loadGeoOptions === 'function' ? loadGeoOptions(QUALITY_GEO_RAIL) : Promise.resolve());
  // The four keys this rail now owns on /api/reporting/quality. Listed once
  // because two places need them: the query builder (below) and Reset All.
  const QUALITY_GEO_PARAM_KEYS = ['state', 'county', 'city', 'zip'];

  // ---- d3 charting -------------------------------------------------------
  // Vendored d3 (ui/vendor/d3). Every chart here is built with it; the
  // hand-rolled SVG string versions these replaced could not support real
  // hover/tooltip interaction, axes, or responsive rescaling.
  const hasD3 = () => typeof window.d3 !== 'undefined';

  // One tooltip element per chart container, positioned against the cursor.
  const TREND_POINT_RADIUS = 7;
  const TREND_POINT_HOVER_RADIUS = 10;

  function chartTooltip(container) {
    // The tooltip is position:absolute, so its top/left resolve against the
    // nearest POSITIONED ancestor. These chart containers had none, so an
    // absolute offset meant for the chart was applied against the page and
    // the tooltip flew to the top of the screen, over the nav - user-reported
    // and clearly visible with a single data point. Guaranteed here rather
    // than in each container's CSS so a new chart cannot reintroduce it.
    try {
      if (window.getComputedStyle(container).position === 'static') {
        container.style.position = 'relative';
      }
    } catch (_) { container.style.position = 'relative'; }
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
        // 4px was hard to see and harder to hit - on a single-point series it
        // read as a speck. The white ring keeps it legible over the line.
        .attr('r', TREND_POINT_RADIUS)
        .attr('fill', color)
        .attr('stroke', '#fff')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .on('mouseenter', function (event, p) {
          d3.select(this).attr('r', TREND_POINT_HOVER_RADIUS);
          tip.show(`<strong>${escapeHtml(s.label)}</strong><br>${escapeHtml(d3.timeFormat('%b %d, %Y')(p.date))}<br>${fmt(p.value)}`, event);
        })
        .on('mousemove', (event, p) => {
          tip.show(`<strong>${escapeHtml(s.label)}</strong><br>${escapeHtml(d3.timeFormat('%b %d, %Y')(p.date))}<br>${fmt(p.value)}`, event);
        })
        .on('mouseleave', function () {
          d3.select(this).attr('r', TREND_POINT_RADIUS);
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
      .reporting-inner-tab:not(.active):hover{background:#005fd3;color:#fff}
      .reporting-tab-panel.hidden{display:none!important}
      .dq-intro{display:flex;justify-content:space-between;gap:18px;align-items:flex-start;margin:4px 0 16px;padding:16px;border:1px solid var(--line);border-radius:8px;background:#fff}
      .dq-intro h2{margin:0 0 5px;font-size:20px;color:var(--navy,var(--ink))}
      .dq-intro p{margin:0;color:var(--muted);max-width:760px}
      .reporting-tab-panel{display:block;width:100%;max-width:none;box-sizing:border-box}.dq-body,.dq-section{width:100%;max-width:none;box-sizing:border-box}.dq-grid{display:grid;grid-template-columns:repeat(4,minmax(190px,1fr));gap:14px;margin:14px 0 20px;width:100%;max-width:none}
      .dq-card{background:#fff;border:1px solid var(--line);border-radius:8px;padding:14px;min-height:92px;position:relative}
      /* Colour carries meaning, not decoration: green resolved, blue AI
         resolved, amber waiting on a person. */
      .dq-card.state-ai-fixed{background:#eff6ff;border-color:#bfdbfe}
      .dq-card.state-ai-fixed strong{color:#1d4ed8}
      .dq-card.state-ai-suggested-fixed{background:#eef2ff;border-color:#c7d2fe}
      .dq-card.state-ai-suggested-fixed strong{color:#4338ca}
      .dq-card.state-manual-fixed{background:#ecfdf5;border-color:#a7f3d0}
      .dq-card.state-manual-fixed strong{color:#047857}
      .dq-card.state-ai-pending{background:#f8fafc;border-color:#cbd5e1}
      .dq-card.state-ai-pending strong{color:#475569}
      .dq-card.state-manual-pending{background:#fff7ed;border-color:#fed7aa}
      .dq-card.state-manual-pending strong{color:#b45309}
      .dq-card strong{display:block;font-size:25px;line-height:1.1;color:var(--navy,var(--ink));font-weight:800}
      .dq-card span{display:block;margin-top:6px;color:var(--muted);font-size:11px;font-weight:750;text-transform:uppercase;letter-spacing:.02em}
      .dq-card small{display:block;margin-top:4px;color:var(--muted);font-size:11px}
      /* Matches the plain h2 style Location Intelligence's table sections
         use (15px/700 weight, var(--ink)) - was 18px with no explicit
         weight, a visibly different header style between the two tabs'
         tables for no reason other than one used h2 and the other h3.
         Charts/cards keep their own styling; this is table sections only. */
      .dq-section{margin:22px 0}.dq-section h3{margin:0 0 10px;font-size:15px;font-weight:700;color:var(--ink)}
      /* Issue Type Breakdown (a compact donut+legend) and Improvement
         Opportunities (a handful of short one-line cards) side by side
         instead of each full-width and stacked (explicit user ask,
         2026-09-10) - both left a lot of unused horizontal space on their
         own row. flex, not a rigid 50/50 grid, so each shares space by its
         own actual content width ("auto resize... pie chart right space is
         empty") rather than forcing the donut's mostly-empty right half to
         stay exactly half the row. Wraps to stacked full-width below
         1000px, matching this file's existing breakpoint. */
      .dq-section-row{display:flex;gap:16px;align-items:flex-start;flex-wrap:wrap}
      .dq-section-row>.dq-section{flex:1 1 380px;min-width:0;margin:0}
      @media(max-width:1000px){.dq-section-row{flex-direction:column}}
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
      /* Wide tables scroll inside their own box rather than overflowing the
         panel - tab 1 already did this via div:has(> table); tab 2 injects
         bare tables, so it needs its own rule. */
      .dq-section > div:has(> table),.dq-main div:has(> .dq-table){overflow-x:auto;border-radius:8px;max-width:100%}
      .dq-table th,.dq-table td{padding:12px 14px;border-bottom:1px solid var(--line);font-size:14px;line-height:1.35;text-align:left}
      /* Matched to Location Intelligence's .comp-bench-table th (font-size
         14px, font-weight 700) - these two tabs' table headers must read as
         one visual system, not two (2026-09-10 UI parity ask). Background/
         color left as-is; only the size/weight mismatch was the reported gap. */
      .dq-table th{background:#eef4fc;color:var(--navy,var(--ink));font-size:14px;font-weight:700}
      /* Two-row alternating bands across every reporting table: scanning a
         wide row left-to-right is where the eye slips a line, and a single
         flat background gives it nothing to hold on to. */
      .dq-table tbody tr:nth-child(4n+1),.dq-table tbody tr:nth-child(4n+2){background:linear-gradient(180deg,#fbfdff 0%,#f4f8fd 100%)}
      .dq-table tbody tr:nth-child(4n+3),.dq-table tbody tr:nth-child(4n+4){background:#ffffff}
      .dq-table tbody tr:hover{background:#e8f1fd}
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
      /* No filter-rail styling here on purpose. This panel's sidebar is the
         SAME component as the Location Intelligence one - .report-filter-rail
         and friends, defined once under "REPORT FILTER RAIL" in
         integrations.html. Every previous attempt to keep a parallel set of
         .dq-filters rules "matching" it ended with the two tabs looking
         different again. */
      .dq-loading-panel{min-height:360px;display:flex;align-items:center;justify-content:center}
      .dq-loading-panel.hidden,.dq-body.hidden{display:none!important}
      .dq-loading-box{display:flex;align-items:center;gap:12px;padding:16px 20px;background:#fff;border:1px solid var(--line);border-radius:8px;color:var(--ink);font-weight:750;box-shadow:0 8px 24px rgba(15,23,42,.08)}
      .dq-layout{display:grid;grid-template-columns:290px minmax(0,1fr);gap:24px;align-items:start;width:100%;max-width:none}.dq-main{display:block;min-width:0;width:100%;max-width:none}.dq-main .dq-table{width:100%;table-layout:auto}
      .dq-history-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(260px,1fr);gap:14px}.dq-history-chart{min-height:360px;padding:8px;border:1px solid var(--line);border-radius:8px;background:#fbfdff}.dq-history-chart svg{width:100%;height:340px;display:block}.dq-period-row{display:flex;justify-content:space-between;gap:12px;padding:10px 0;border-bottom:1px solid var(--line);font-size:12px}.dq-period-row strong{color:var(--navy,var(--ink))}
      @media(max-width:900px){.dq-layout{grid-template-columns:1fr}}
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

  // Paged table for the quality tab's hand-built tables. Keeps its own page
  // per target so two tables side by side cannot fight over one counter.
  const dqTablePages = new Map();
  const dqTableData = new Map();
  const DQ_TABLE_PAGE_SIZE = 10;
  // "Quality by <dimension>" dropdown (explicit user ask, 2026-09-10):
  // brand/city/state/country all now come back from the backend in the
  // SAME shape (invalid/needs_review/ai_enriched), so one table swaps
  // rows on dropdown change instead of needing four bespoke sections.
  // Data is stashed here on every loadQuality() so the dropdown's own
  // change listener (wired once, outside the render pass) always reads
  // the latest fetch, not a stale closure over the render that happened
  // to be running when the user switched dimensions.
  const dqDimensionData = { brands: [], cities: [], states: [], countries: [] };
  const DQ_DIMENSION_LABELS = { brands: 'Brand', cities: 'City', states: 'State', countries: 'Country' };
  const DQ_DIMENSION_KEYS = { brands: 'brand', cities: 'city', states: 'state', countries: 'country' };
  function renderDimensionTable(resetPage = false) {
    // resetPage only on an actual dropdown switch (below) - a plain data
    // refresh on the SAME dimension should not jar the user back to page 1.
    if (resetPage) dqTablePages.delete('dqDimensionTable');
    const dimension = $('dqDimensionSelect')?.value || 'brands';
    const rows = dqDimensionData[dimension] || [];
    const labelKey = DQ_DIMENSION_KEYS[dimension];
    const label = DQ_DIMENSION_LABELS[dimension];
    const formatLabel = dimension === 'brands' ? formatBrandName : (v) => v || 'Unknown';
    renderPagedDqTable('dqDimensionTable', [label, 'Invalid', 'Needs review', 'AI fixed'],
      rows.map((row) => [formatLabel(row[labelKey]), fmt(row.invalid), fmt(row.needs_review), fmt(row.ai_enriched)]),
      `No invalid ${label.toLowerCase()} records are available for this filter.`);
  }
  if (!window.__dqDimensionSelectWired) {
    window.__dqDimensionSelectWired = true;
    document.addEventListener('change', (event) => {
      if (event.target && event.target.id === 'dqDimensionSelect') renderDimensionTable(true);
    });
  }

  function renderPagedDqTable(targetId, headers, rows, emptyMessage) {
    const host = $(targetId);
    if (!host) return;
    dqTableData.set(targetId, { headers, rows, emptyMessage });
    if (!rows.length) {
      host.innerHTML = `<table class="dq-table"><thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody><tr><td colspan="${headers.length}">${escapeHtml(emptyMessage)}</td></tr></tbody></table>`;
      return;
    }
    const pageCount = Math.ceil(rows.length / DQ_TABLE_PAGE_SIZE);
    const page = Math.min(Math.max(dqTablePages.get(targetId) || 0, 0), pageCount - 1);
    dqTablePages.set(targetId, page);
    const slice = rows.slice(page * DQ_TABLE_PAGE_SIZE, (page + 1) * DQ_TABLE_PAGE_SIZE);
    const pager = pageCount > 1
      ? `<div style="display:flex;justify-content:center;align-items:center;gap:8px;margin-top:8px;">
           <button type="button" class="secondary" data-dq-page="prev" data-target="${escapeHtml(targetId)}"${page === 0 ? ' disabled' : ''}>Previous</button>
           <span style="font-size:12px;color:var(--muted);">Page ${page + 1} of ${pageCount} &middot; ${rows.length.toLocaleString()} rows</span>
           <button type="button" class="secondary" data-dq-page="next" data-target="${escapeHtml(targetId)}"${page >= pageCount - 1 ? ' disabled' : ''}>Next</button>
         </div>`
      : '';
    host.innerHTML = `<div style="overflow-x:auto;"><table class="dq-table"><thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${slice.map((cells) => `<tr>${cells.map((c) => `<td>${escapeHtml(c)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>` + pager;
  }

  document.addEventListener('click', (event) => {
    const button = event.target?.closest?.('button[data-dq-page]');
    if (!button) return;
    event.preventDefault();
    const targetId = button.dataset.target;
    const stored = dqTableData.get(targetId);
    if (!stored) return;
    const current = dqTablePages.get(targetId) || 0;
    dqTablePages.set(targetId, button.dataset.dqPage === 'next' ? current + 1 : current - 1);
    renderPagedDqTable(targetId, stored.headers, stored.rows, stored.emptyMessage);
  });

  function metricCard(value, label, note = '', tone = '') {
    return `<div class="dq-card${tone ? ` ${tone}` : ''}" data-metric-label="${escapeHtml(label)}"><strong>${value}</strong><span>${label}</span>${note ? `<small>${note}</small>` : ''}<button type="button" class="dq-metric-download" data-metric-label="${escapeHtml(label)}" title="Download the listings behind this number, with its metrics, as Excel">⬇ Excel</button></div>`;
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

  // Per-table downloads. A reporting TABLE exports its own shape (gap ZIPs,
  // brand rows) rather than raw listings - shipping listing columns for a
  // market-gap table would be noise. Same one-request-per-click guard as the
  // metric cards.
  const tableDownloadsInFlight = new Set();

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-table-export]');
    if (!button) return;
    event.preventDefault();
    const table = button.dataset.tableExport;
    if (!table || tableDownloadsInFlight.has(table)) return;
    tableDownloadsInFlight.add(table);
    const previous = button.innerHTML;
    button.disabled = true;
    button.innerHTML = 'Preparing';
    try {
      let qs = '';
      try { if (typeof window.reportingQueryString === 'function') qs = window.reportingQueryString(); } catch (_) {}
      const query = new URLSearchParams(qs);
      query.set('table', table);
      const response = await fetch(`/api/reporting/table-export?${query.toString()}`);
      if (!response.ok) {
        let message = 'Could not build this table export.';
        try { message = (await response.json()).error || message; } catch (_) {}
        throw new Error(message);
      }
      const disposition = response.headers.get('Content-Disposition') || '';
      const named = /filename="?([^"]+)"?/.exec(disposition);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = named ? named[1] : `${table}.zip`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      const status = $('reportStatus') || $('dqStatus');
      if (status) {
        status.className = 'report-status error';
        status.textContent = error.message || 'Could not build this table export.';
        status.classList.remove('hidden');
      }
    } finally {
      tableDownloadsInFlight.delete(table);
      button.disabled = false;
      button.innerHTML = previous;
    }
  });

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
      : { brand: 'dqBrandFilter', state: 'dqStateFilter', county: 'dqCountyFilter', city: 'dqCityFilter', zip: 'dqZipFilter', reason: 'dqReasonFilter', status: 'dqStatusFilter', start_date: 'dqStartDate', end_date: 'dqEndDate' }, button);
  });

  function buildQualityPanel() {
    if ($('reportQualityPanel')) return $('reportQualityPanel');
    const panel = document.createElement('div');
    panel.id = 'reportQualityPanel';
    panel.className = 'reporting-tab-panel hidden';
    panel.innerHTML = `
      <div class="dq-layout">
      <!-- The filter rail: identical structure, classes and spacing to the
           Location Intelligence one in integrations.html (search it for
           "report-filter-rail"). Section titles, cards and the auto-apply
           switch above Apply/Reset all come from there; only the filters
           themselves differ. -->
      <aside class="report-filter-rail">
        <div class="report-filter-rail-head"><h2>Report Filters</h2></div>
        <div class="report-filter-section">
          <div class="report-filter-section-title">&#127991;&#65039; Brand Filters</div>
          <div class="report-filter-group"><label for="dqBrandFilter" class="report-filter-label">Primary Brand</label><select id="dqBrandFilter" class="report-filter-control"><option value="">All impacted brands</option></select></div>
        </div>
        <div class="report-filter-section">
          <div class="report-filter-section-title">&#128205; Geographic Filters</div>
          <div class="report-filter-group"><label for="dqStateFilter" class="report-filter-label">State</label><select id="dqStateFilter" class="report-filter-control"><option value="">All impacted states</option></select></div>
          <div class="report-filter-group"><label for="dqCountyFilter" class="report-filter-label">County</label><select id="dqCountyFilter" class="report-filter-control"><option value="">All Counties</option></select></div>
          <div class="report-filter-group"><label for="dqCityFilter" class="report-filter-label">City</label><select id="dqCityFilter" class="report-filter-control"><option value="">All Cities</option></select></div>
          <!-- The one control here that is NOT a searchable select, same as
               the Location rail: ZIP matches are fetched from the server as
               you type (setupZipTypeahead, given QUALITY_GEO_RAIL), because
               30k+ ZIPs are never all in the page. -->
          <div class="report-filter-group"><label for="dqZipFilter" class="report-filter-label">ZIP Code</label><input id="dqZipFilter" list="dqZipSuggestions" class="report-filter-control" placeholder="Search ZIP"><datalist id="dqZipSuggestions"></datalist></div>
        </div>
        <div class="report-filter-section">
          <div class="report-filter-section-title">&#128269; Issue Filters</div>
          <div class="report-filter-group"><label for="dqReasonFilter" class="report-filter-label">Issue Type</label><select id="dqReasonFilter" class="report-filter-control"><option value="">All issue types</option></select></div>
          <div class="report-filter-group"><label for="dqStatusFilter" class="report-filter-label">Review Status</label><select id="dqStatusFilter" class="report-filter-control"><option value="all">All statuses</option><option value="needs_review">Needs review</option><option value="ai_fixed">AI fixed</option></select></div>
        </div>
        <div class="report-filter-section">
          <div class="report-filter-section-title">&#128197; Date Range</div>
          <div class="report-filter-group"><label for="dqStartDate" class="report-filter-label">From Date</label><input id="dqStartDate" type="date" class="report-filter-control"></div>
          <div class="report-filter-group"><label for="dqEndDate" class="report-filter-label">To Date</label><input id="dqEndDate" type="date" class="report-filter-control"></div>
        </div>
        <div class="report-filter-section">
          <div class="report-filter-section-title">&#9881;&#65039; Settings</div>
          <div class="report-filter-group"><label for="dqStaleDays" class="report-filter-label">Stale after (days)</label><select id="dqStaleDays" class="report-filter-control"><option value="1">1 day</option><option value="7">7 days</option><option value="30">30 days</option><option value="90" selected>90 days</option><option value="180">180 days</option><option value="365">365 days</option></select></div>
        </div>
        <div class="report-filter-section report-filter-actions">
          <div id="dqAutoApplyHost"></div>
          <button id="applyQualityFiltersBtn" type="button">Apply All Filters</button>
          <button id="resetQualityFiltersBtn" class="secondary" type="button">Reset All</button>
        </div>
      </aside><main class="dq-main"><div class="dq-intro">
        <div><h2>Data Quality &amp; Improvements</h2><p>Review rejected listings and quality mirrors to see issue patterns, fix progress, freshness risk, and where automatic or manual repair is improving the dataset.</p></div>
      </div><div id="dqStatus" class="report-status hidden"></div><div id="dqLoadingPanel" class="dq-loading-panel hidden"><div class="dq-loading-box"><span class="spinner"></span><span>Loading quality metrics</span></div></div>
      <div id="dqBody" class="dq-body hidden">
        <div id="dqMetricGrid" class="dq-grid">${[['0','Invalid listings'],['0','Needs manual review'],['0','Listings fixed automatically'],['0','Listings fixed manually'],['0.00%','Unresolved rate'],['0.00%','ZIP completeness'],['0.00%','Coordinate completeness'],['0.00%','Duplicate rate'],['0','Stale records'],['0','Entity-resolution attempts'],['0.00%','Entity-resolution success'],['0','Active issue types']].map(([value,label]) => metricCard(value,label)).join('')}</div>
        <div class="dq-section"><h3>Quality Signals</h3><div id="dqSignals"></div></div>
        <div class="dq-section-row">
          <div class="dq-section"><h3>Issue Type Breakdown</h3><div id="dqReasonsChart"></div></div>
          <div class="dq-section"><h3>Improvement Opportunities</h3><div id="dqImprovements" class="dq-improvements-list"></div></div>
        </div>
        <div class="dq-section"><h3>Fix State by Failure Field</h3><div id="dqFixStatePivot"></div></div>
        <div class="dq-section">
          <h3 style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">Quality by
            <select id="dqDimensionSelect" aria-label="Group quality metrics by" style="font-size:13px;padding:4px 8px;border:1px solid var(--line);border-radius:6px;font-weight:600;">
              <option value="brands">Brand</option>
              <option value="cities">City</option>
              <option value="states">State</option>
              <option value="countries">Country</option>
            </select>
          </h3>
          <div id="dqDimensionTable"></div>
        </div>
        <div class="dq-section"><h3>Reconciliation</h3><div id="dqReconciliation"></div></div>

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

  // Historical Quality & Change Tracking. Moved to tab 1 and rebuilt: it used
  // to plot a single "invalid records" series from the quality snapshot, with
  // no period control. It now plots LISTINGS over time from the same
  // timeseries endpoint Trends uses, keeps errors as the quality line, and
  // overlays a competitor series when competitors are selected - so it
  // answers "is our footprint growing, and is quality keeping up".
  // Default all period-toggle chart features to 1H. Same-day datasets collapse
  // to one point under longer buckets, which makes first paint look empty even
  // when useful minute-level/hourly shape exists.
  let historyPeriod = '1H';
  // Same reasoning and same one-shot guard as trendAutoFallbackDone above.
  let historyAutoFallbackDone = false;

  async function loadQualityHistory() {
    const chart = $('dqHistoryChart');
    const comparisons = $('dqPeriodComparisons');
    if (!chart) return;
    const mainBrand = $('reportMainBrandSelect')?.value || '';
    const competitors = (typeof window.selectedCompetitorBrands === 'function')
      ? window.selectedCompetitorBrands() : [];
    const fetchSeries = async (brands, periodOverride) => {
      const params = new URLSearchParams({ period: periodOverride || historyPeriod });
      // ONE `brands` parameter, comma-separated. This used to append a
      // repeated `brand` parameter, which /api/reporting/timeseries never
      // reads - it takes params.get("brands")[0] and splits it on commas - so
      // every brand filter on this chart was silently discarded and the
      // "competitors" line was really a second copy of the all-brands line.
      const brandList = (brands || []).filter(Boolean);
      if (brandList.length) params.set('brands', brandList.join(','));
      const response = await fetch(`/api/reporting/timeseries?${params}`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || 'Unable to load history.');
      return Array.isArray(payload.series) ? payload.series : [];
    };
    const hasAnyPoints = (entries) => (entries || []).some((s) => Array.isArray(s.points) && s.points.length);
    try {
      const ownBrands = mainBrand ? [mainBrand] : [];
      let own;
      if (historyPeriod === '1H' && !historyAutoFallbackDone) {
        // Same reasoning as trendAutoFallbackDone's concurrent probe: fetch
        // both periods together rather than one-then-the-other, since a cold
        // cache makes each of these several seconds on live BigQuery.
        historyAutoFallbackDone = true;
        const [oneHour, oneDay] = await Promise.all([fetchSeries(ownBrands, '1H'), fetchSeries(ownBrands, '1D')]);
        const useDay = !hasAnyPoints(oneHour) && hasAnyPoints(oneDay);
        own = useDay ? oneDay : oneHour;
        historyPeriod = useDay ? '1D' : '1H';
        document.querySelectorAll('[data-history-period]').forEach((node) => {
          node.classList.toggle('active', node.dataset.historyPeriod === historyPeriod);
        });
      } else {
        own = await fetchSeries(ownBrands);
      }
      const pick = (label) => own.find((entry) => entry.label === label)?.points || [];
      const series = [
        { label: mainBrand ? `${mainBrand} listings` : 'Listings', color: '#1677ee', points: pick('Locations') },
        { label: 'Errors', color: '#ef4444', points: pick('Errors') },
      ];
      if (competitors.length) {
        // Competitors are fetched as one combined series rather than one per
        // brand: the question here is "us versus the rest", and a line per
        // competitor makes the chart unreadable past three or four.
        const rival = await fetchSeries(competitors);
        series.push({
          label: `Competitors (${competitors.length})`,
          color: '#8b5cf6',
          points: rival.find((entry) => entry.label === 'Locations')?.points || [],
        });
      }
      renderTimeSeriesChart(chart, series, {
        height: 340,
        ariaLabel: 'Listings and errors over time',
        emptyMessage: 'No history for this period yet.',
      });
      if (comparisons) {
        const listingPoints = series[0].points || [];
        const latest = listingPoints[listingPoints.length - 1];
        comparisons.innerHTML = listingPoints.length
          ? [['Listings now', num(latest?.count)],
             ['Change over period', num(latest?.count) - num(listingPoints[0]?.count)],
             ['Points plotted', listingPoints.length]]
              .map(([label, value]) => `<div class="dq-period-row"><span>${escapeHtml(label)}</span><strong>${value > 0 && label === 'Change over period' ? '+' : ''}${fmt(value)}</strong></div>`).join('')
          : '<div class="report-status">No period comparison available yet.</div>';
      }
    } catch (error) {
      chart.innerHTML = `<div class="report-status">${escapeHtml(typeof productSafeError === 'function' ? productSafeError(error.message, 'History is temporarily unavailable.') : 'History is temporarily unavailable.')}</div>`;
    }
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-history-period]');
    if (!button) return;
    event.preventDefault();
    historyPeriod = button.dataset.historyPeriod;
    document.querySelectorAll('[data-history-period]').forEach((node) => {
      node.classList.toggle('active', node === button);
    });
    loadQualityHistory();
  });

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

  // Plain SVG, deliberately not d3. Two previous versions of this chart were
  // broken by the same root cause: they sized themselves from
  // container.clientWidth, which is 0 while the panel is hidden - first
  // producing a 900px viewBox the browser scaled into one solid block, then
  // needing a ResizeObserver that could re-enter and stack a second chart on
  // top of the first (overlapping full-height rectangles). A fixed-viewBox
  // SVG scales to any container width without measuring anything, so there
  // is no zero-width case and no re-entrancy to get wrong.
  const TOP_STATES_VIEW_W = 1000;
  const TOP_STATES_ROW_H = 34;
  const TOP_STATES_LABEL_W = 150;
  const TOP_STATES_VALUE_W = 86;

  function renderTopStatesBar(states = []) {
    const container = $('dqTopStatesBar');
    if (!container) return;
    // top_states rows (from reporting_summary()/the gold mirror) carry the
    // ZIP-coverage count as "locations" - "zip_count"/"count" never existed
    // on this payload, so this always evaluated to 0 for every row.
    const rows = (states || []).slice(0, 10).map((row) => ({
      label: row.state_name || row.state || 'Unknown',
      value: num(row.locations),
    })).filter((row) => row.value > 0);
    container.innerHTML = '';
    if (!rows.length) {
      container.innerHTML = '<div class="report-status" style="padding:12px 0;font-size:13px;">No state coverage data available yet.</div>';
      return;
    }

    const max = Math.max(...rows.map((r) => r.value)) || 1;
    const trackW = TOP_STATES_VIEW_W - TOP_STATES_LABEL_W - TOP_STATES_VALUE_W;
    const height = rows.length * TOP_STATES_ROW_H + 8;
    const barH = 20;
    // Birdeye theme: one accent hue (--accent #0b70f0), stepped in lightness
    // so the ranking reads at a glance without introducing colours that mean
    // nothing. Darkest = biggest, which matches the sort order.
    const fillFor = (index) => {
      const step = rows.length > 1 ? index / (rows.length - 1) : 0;
      return `hsl(213, 88%, ${34 + step * 30}%)`;
    };

    const bars = rows.map((row, index) => {
      const y = index * TOP_STATES_ROW_H + 4;
      const w = Math.max(2, (row.value / max) * trackW);
      const label = escapeHtml(row.label);
      return `
        <g class="dq-state-bar" data-label="${label}" data-value="${fmt(row.value)}">
          <text x="${TOP_STATES_LABEL_W - 12}" y="${y + barH / 2 + 4}" text-anchor="end"
                font-size="13" fill="var(--ink)">${label}</text>
          <rect x="${TOP_STATES_LABEL_W}" y="${y}" width="${trackW}" height="${barH}"
                rx="4" fill="#eef2f7"></rect>
          <rect class="dq-state-bar-fill" x="${TOP_STATES_LABEL_W}" y="${y}" width="${w.toFixed(1)}"
                height="${barH}" rx="4" fill="${fillFor(index)}"></rect>
          <text x="${TOP_STATES_LABEL_W + w + 10}" y="${y + barH / 2 + 4}" font-size="12"
                font-weight="700" fill="var(--ink)"
                style="font-variant-numeric: tabular-nums;">${fmt(row.value)}</text>
        </g>`;
    }).join('');

    container.insertAdjacentHTML('beforeend', `
      <svg viewBox="0 0 ${TOP_STATES_VIEW_W} ${height}" width="100%" height="${height}"
           preserveAspectRatio="xMinYMin meet" role="img" aria-label="Top states by ZIP coverage">
        ${bars}
      </svg>`);

    const tip = chartTooltip(container);
    container.querySelectorAll('.dq-state-bar').forEach((group) => {
      const show = (event) => tip.show(
        `<strong>${group.dataset.label}</strong><br>${group.dataset.value} ZIPs covered`, event);
      group.addEventListener('mouseenter', show);
      group.addEventListener('mousemove', show);
      group.addEventListener('mouseleave', () => tip.hide());
    });
  }

  let trendState = { period: '1H' };
  // 1H is the default because same-day datasets collapse to one point under
  // longer buckets - but a dataset with nothing in the last hour (the load
  // happened earlier today, or yesterday) makes that default look broken:
  // an empty chart the user has to notice and manually switch away from.
  // Tried once, automatically, on first load only - never fights a later
  // explicit click back to 1H, which must be allowed to show "no data" if
  // that is genuinely true right now.
  let trendAutoFallbackDone = false;

  // Set once a real chart has been drawn, never reset - the same rule the
  // location report uses (reportHasRenderedOnce). Without it every call tore
  // the chart down and put "Loading trend data" back up, including the ones
  // answered from the SQLite cache in milliseconds, so the chart appeared to
  // reload constantly when in fact nothing was being re-queried.
  let trendHasRenderedOnce = false;

  async function loadTrendChart() {
    const chart = $('dqTrendChart');
    // Only blank the panel when there is nothing to keep. A refresh leaves
    // the current chart on screen and swaps it when the new data lands.
    if (chart && !trendHasRenderedOnce) {
      chart.innerHTML = '<div class="report-status"><span class="spinner"></span> Loading trend data</div>';
    }
    try {
      let qs = '';
      try { if (typeof window.reportingQueryString === 'function') qs = window.reportingQueryString(); } catch (_) {}
      const fetchPeriod = async (period) => {
        const p = new URLSearchParams(qs);
        p.set('period', period);
        const res = await fetch(`/api/reporting/timeseries?${p.toString()}`);
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || 'Unable to load trend data.');
        return Array.isArray(data.series) ? data.series : [];
      };
      const hasPoints = (series) => series.some((s) => Array.isArray(s.points) && s.points.length);
      let series;
      if (trendState.period === '1H' && !trendAutoFallbackDone) {
        // Both periods fetched together, not one-then-the-other: neither has
        // a SQLite-mirror fast path of its own (only a per-period query-result
        // cache), so a cold cache means each request can take several seconds
        // on live BigQuery - fetching sequentially would mean paying for BOTH,
        // back to back, on exactly the case this fallback exists for.
        trendAutoFallbackDone = true;
        const [oneHour, oneDay] = await Promise.all([fetchPeriod('1H'), fetchPeriod('1D')]);
        const useDay = !hasPoints(oneHour) && hasPoints(oneDay);
        series = useDay ? oneDay : oneHour;
        trendState.period = useDay ? '1D' : '1H';
        $('dqTrendPeriod')?.querySelectorAll('[data-period]').forEach((b) => b.classList.toggle('active', b.dataset.period === trendState.period));
      } else {
        series = await fetchPeriod(trendState.period);
      }
      renderTrendChart(series);
      trendHasRenderedOnce = true;
    } catch (err) {
      // Only replace a drawn chart with an error if there is no chart to
      // keep - a transient failure must not wipe good data off the screen.
      if (chart && !trendHasRenderedOnce) {
        chart.innerHTML = `<div class="report-status">${escapeHtml(typeof productSafeError === 'function' ? productSafeError(err.message, 'Trend data is temporarily unavailable.') : 'Trend data is temporarily unavailable.')}</div>`;
      }
    }
  }

  // Extended Coverage Metrics was removed: measured against the top row it
  // held 3 exact duplicates (Active Brands, Total Stores, Covered Markets),
  // restated Market ZIPs as "ZIP codes covered", and showed three figures
  // that contradicted the correct ones - "States covered 57" and "Cities
  // covered 21,788" are universe totals mislabelled as coverage, and
  // "Whitespace ZIPs 100" was data.gaps.length, i.e. the PAGE SIZE, not the
  // real uncovered count. This loader now serves only the Top States chart.
  async function loadExtendedMetrics() {
    const bars = $('dqTopStatesBar');
    try {
      let qs = '';
      try { if (typeof window.reportingQueryString === 'function') qs = window.reportingQueryString(); } catch (_) {}
      const res = await fetch(`/api/reporting/summary${qs ? `?${qs}` : ''}`);
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Unable to load coverage metrics.');
      renderTopStatesBar(Array.isArray(data.top_states) ? data.top_states : []);
    } catch (err) {
      const message = typeof productSafeError === 'function' ? productSafeError(err.message, 'Coverage metrics are temporarily unavailable.') : 'Coverage metrics are temporarily unavailable.';
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
  // Set once real data has rendered here at least once this page load.
  // Superseded twice now by explicit user ask: first, that the blocking
  // spinner should not reappear on every call, only the true first one
  // (fixed by gating it on this flag); then, that it should not exist even
  // ON the true first load either - the static #dqBody markup already ships
  // with the full table/card structure at "0" (see the panel() builder
  // above), so tab 2 must show that same structure immediately on open, the
  // same way it is never blank on tab 1, rather than a full-panel spinner
  // hiding it. Real numbers replace the zeros silently once they land,
  // whether this is the first load, a background refresh, or a warm-cache
  // poll retry - there is no longer a load state that hides the body.
  let dqQualityLoadedOnce = false;
  async function loadQuality(forceRefresh = false) {
    const status = $('dqStatus');
    if (!status) return;
    const loadingPanel = $('dqLoadingPanel');
    const body = $('dqBody');
    if (loadingPanel) loadingPanel.classList.add('hidden');
    if (body) body.classList.remove('hidden');
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
      // County/City/ZIP travel with State now that this rail has all four.
      // The blank case matters as much as the set one: qs above is seeded
      // from the LOCATION rail's query string (for brand scope), which also
      // carries its state/county/city/zip - so a control left empty here has
      // to delete the inherited key rather than leave tab 1's geography
      // quietly filtering tab 2's numbers while tab 2's own boxes read "All".
      // A rail that does not describe what is filtered is the bug this whole
      // change exists to remove.
      [['brand', 'dqBrandFilter'], ['state', 'dqStateFilter'], ['county', 'dqCountyFilter'], ['city', 'dqCityFilter'], ['zip', 'dqZipFilter'], ['reason', 'dqReasonFilter'], ['status', 'dqStatusFilter'], ['start_date', 'dqStartDate'], ['end_date', 'dqEndDate']].forEach(([key, id]) => {
        const node = $(id);
        if (node?.value) qualityParams.set(key, node.value);
        else if (QUALITY_GEO_PARAM_KEYS.includes(key)) qualityParams.delete(key);
      });
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
      const brandMergesCount = num(q.brand_merges_count);
      const staleRecords = num(q.stale_records);
      // The backend halves the configured stale-after threshold (down to a
      // 30-minute floor) when nothing is stale at the configured one, so
      // this can legitimately differ from the saved setting - state which
      // threshold actually produced the number rather than always saying
      // "days" when it might have been minutes.
      const staleThresholdDays = num(q.stale_after_days_used ?? q.stale_after_days);
      // Below 1 day the halving sequence still spans a wide range (up to
      // ~23.9 hours down to a 30-minute floor) - always showing raw minutes
      // there produced unreadable labels like ">675 min" instead of a
      // "Listings older than 11.3 hrs" scale appropriate to the magnitude
      // (user ask, 2026-09-10: plain "older than X min/hr/days" language,
      // no ">" symbol).
      const staleThresholdLabel = (() => {
        if (staleThresholdDays >= 1) {
          const days = staleThresholdDays % 1 === 0 ? staleThresholdDays : staleThresholdDays.toFixed(1);
          return `Listings older than ${days} day${staleThresholdDays === 1 ? '' : 's'}`;
        }
        const totalMinutes = Math.max(1, Math.round(staleThresholdDays * 24 * 60));
        if (totalMinutes >= 60) {
          const hours = totalMinutes / 60;
          const hoursLabel = hours % 1 === 0 ? hours : hours.toFixed(1);
          return `Listings older than ${hoursLabel} hr${hours === 1 ? '' : 's'}`;
        }
        return `Listings older than ${totalMinutes} min`;
      })();
      const entityAttempts = num(q.entity_resolution_attempts);
      const entitySuccess = num(q.entity_resolution_success_rate_pct);
      const reasons = Array.isArray(data.reasons) ? data.reasons : [];
      const states = Array.isArray(data.states) ? data.states : [];
      const cities = Array.isArray(data.cities) ? data.cities : [];
      const countries = Array.isArray(data.countries) ? data.countries : [];
      const brandsForDimension = Array.isArray(data.brands) ? data.brands : [];
      // Per-filter option labels. States read as full names, because that is
      // what the Location rail's State dropdown shows and what its search box
      // matches on - a rail that says "CA" next to one that says "California"
      // is the same mismatch in smaller print. The option VALUE is still the
      // raw code, so what gets sent to /api/reporting/quality is unchanged.
      [['dqBrandFilter', data.filters?.brands || [], 'All impacted brands', formatIssue],
       ['dqStateFilter', data.filters?.states || [], 'All impacted states', stateLabel],
       ['dqReasonFilter', data.filters?.reasons || [], 'All issue types', formatIssue]].forEach(([id, values, label, optionLabel]) => {
        const node = $(id); if (!node) return; const previous = node.value;
        node.innerHTML = `<option value="">${label}</option>${values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(optionLabel(value))}</option>`).join('')}`;
        if (values.includes(previous)) node.value = previous;
      });
      refreshQualityFilterSearch();

      // Same INV-15 reasoning as the Quality Signals table below: the
      // coverage-derived cards are zeroed defaults when the coverage query
      // returned nothing, so show "—" rather than a fabricated 0.0%.
      const coverageMeasured = num(q.total_records) > 0;
      // RPT-08: the four fix states first, each with its share, then the
      // rest of the quality figures.
      const aiPending = num(q.ai_review_pending);
      const manualPending = num(q.manual_review_pending);
      // Five mutually exclusive states over every listing that was EVER
      // invalid, so the totals accumulate day over day instead of resetting
      // when a record gets fixed (a fix soft-deletes the error row).
      // Colour carries meaning: green = resolved, amber = waiting on a human,
      // blue = AI resolved, grey-blue = AI suggestion waiting for review.
      const fixStates = data.fix_states || {};
      const statesComputed = fixStates.computed === true;
      const stateCard = (key, label, tone, note) => metricCard(
        statesComputed ? fmt(num(fixStates[key])) : '—', label, note, tone);
      const totalEverInvalid = num(fixStates.total_ever_invalid);
      const sharePct = (key) => (statesComputed && totalEverInvalid)
        ? pct(num(fixStates[key]) * 100 / totalEverInvalid) : '';
      $('dqMetricGrid').innerHTML = [
        stateCard('ai_fixed', 'Fixed by AI', 'state-ai-fixed', sharePct('ai_fixed')),
        stateCard('ai_suggested_fixed', 'Fixed from AI suggestion', 'state-ai-suggested-fixed', sharePct('ai_suggested_fixed')),
        stateCard('manual_fixed', 'Fixed manually', 'state-manual-fixed', sharePct('manual_fixed')),
        stateCard('ai_suggested_pending', 'AI suggestion awaiting review', 'state-ai-pending', sharePct('ai_suggested_pending')),
        stateCard('manual_pending', 'Awaiting manual review', 'state-manual-pending', sharePct('manual_pending')),
        metricCard(statesComputed ? fmt(totalEverInvalid) : '—', 'Ever invalid (all time)', 'Cumulative across every load'),
        metricCard(fmt(raw), 'Invalid listings', 'Active validation and review population'),
        metricCard(fmt(needsReview), 'Needs manual review'),
        metricCard(pct(unresolvedRate), 'Unresolved rate'),
        metricCard(coverageMeasured ? pct(zipCompleteness) : '—', 'ZIP completeness'),
        metricCard(coverageMeasured ? pct(coordinateCompleteness) : '—', 'Coordinate completeness'),
        metricCard(coverageMeasured ? pct(duplicateRate) : '—', 'Duplicate rate', `${fmt(brandMergesCount)} brand merge${brandMergesCount === 1 ? '' : 's'} applied`),
        metricCard(coverageMeasured ? fmt(staleRecords) : '—', 'Stale records', staleThresholdLabel),
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

      // One dropdown-driven table instead of separate Brand/State/City
      // sections (explicit user ask, 2026-09-10) - stash this load's data
      // for all four dimensions, then render whichever one the dropdown
      // is currently set to (defaults to Brand, matching the old default
      // section). Was a hard .slice(0, 10)/no pagination on the old
      // per-dimension tables - rows past 10 were simply hidden with no
      // pager and no indication they existed; renderPagedDqTable (already
      // used elsewhere on this tab) fixes that for all four dimensions now.
      dqDimensionData.brands = brandsForDimension;
      dqDimensionData.cities = cities;
      dqDimensionData.states = states.map((row) => ({ ...row, state: stateLabel(row.state) }));
      dqDimensionData.countries = countries;
      renderDimensionTable();

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

      if (loadingPanel) loadingPanel.classList.add('hidden');
      if (body) body.classList.remove('hidden');
      status.className = 'report-status hidden';
      status.textContent = '';
      dqQualityLoadedOnce = true;
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
        loadQualityHistory();
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
    // Everything Reset All clears. The geographic four are listed here but
    // deliberately NOT watched by the auto-apply switch below: they carry
    // their own change handlers, because changing State has to refresh the
    // dependent dropdowns whether auto-apply is on or off, and those handlers
    // hand only the reload back via schedule(). That is exactly how the
    // Location rail splits the same work between integrations.html and
    // setupReportAutoApply().
    const QUALITY_GEO_FILTER_IDS = [QUALITY_GEO_RAIL.state, QUALITY_GEO_RAIL.county, QUALITY_GEO_RAIL.city, QUALITY_GEO_RAIL.zip];
    const QUALITY_FILTER_IDS = ['dqBrandFilter', ...QUALITY_GEO_FILTER_IDS, 'dqReasonFilter', 'dqStatusFilter', 'dqStartDate', 'dqEndDate'];
    // Filters apply themselves as they change; the button below stays for an
    // explicit re-run, and the switch beside it stops that for anyone setting
    // several filters at once who does not want a query fired after every
    // keystroke. The switch, its 400ms debounce and the "turning it back on
    // applies whatever moved while it was off" rule all come from
    // attachAutoApplyToggle() in js/reporting.js, shared with the Location
    // Intelligence rail so the two tabs cannot end up behaving differently.
    const qualityAutoApply = typeof attachAutoApplyToggle === 'function' ? attachAutoApplyToggle('dqAutoApplyHost', {
      id: 'dqAutoApplyToggle',
      title: 'Reload this tab automatically whenever a filter changes. Turn it off to set several filters first, then use Apply All Filters.',
      watchIds: QUALITY_FILTER_IDS.filter((id) => !QUALITY_GEO_FILTER_IDS.includes(id)),
      onApply: () => loadQuality()
    }) : null;
    // An explicit Apply subsumes a debounce still counting down, so cancel it
    // rather than let it fire the same query again a moment later.
    $('applyQualityFiltersBtn')?.addEventListener('click', () => {
      qualityAutoApply?.cancel();
      loadQuality();
    });

    // Geographic filters: State -> County -> City -> ZIP, cascading, all
    // searchable - identical to tab 1 because it IS tab 1's code, pointed at
    // this rail's ids through QUALITY_GEO_RAIL. What is written here is only
    // the wiring: which control clears which dependents before the shared
    // loader refetches. Clearing them is tab 1's rule too - a county left
    // over from the previously selected state is not a filter anyone asked
    // for, and it would silently keep filtering the numbers.
    if (typeof setupZipTypeahead === 'function') setupZipTypeahead(QUALITY_GEO_RAIL);
    const clearQualityFilters = (ids) => ids.forEach((id) => { const node = $(id); if (node) node.value = ''; });
    $(QUALITY_GEO_RAIL.state)?.addEventListener('change', async () => {
      clearQualityFilters([QUALITY_GEO_RAIL.county, QUALITY_GEO_RAIL.city, QUALITY_GEO_RAIL.zip]);
      // The dependent dropdowns always refresh - that keeps the controls
      // coherent and is not the query - while the reload itself goes through
      // the auto-apply switch, so turning it off silences the geographic
      // filters too rather than only part of the rail.
      await loadQualityGeoOptions();
      qualityAutoApply?.schedule();
    });
    $(QUALITY_GEO_RAIL.county)?.addEventListener('change', async () => {
      clearQualityFilters([QUALITY_GEO_RAIL.city, QUALITY_GEO_RAIL.zip]);
      await loadQualityGeoOptions();
      qualityAutoApply?.schedule();
    });
    [QUALITY_GEO_RAIL.city, QUALITY_GEO_RAIL.zip].forEach((id) => {
      $(id)?.addEventListener('change', () => qualityAutoApply?.schedule());
      $(id)?.addEventListener('keydown', (event) => {
        // Enter in these boxes is an explicit submit, the same gesture as
        // clicking Apply All Filters, so it still runs with the auto-apply
        // switch off - and cancels the debounce for the same reason that
        // button does.
        if (event.key !== 'Enter') return;
        qualityAutoApply?.cancel();
        loadQuality();
      });
    });
    // Populate County/City up front so the rail is usable the moment the tab
    // is opened, instead of staying empty until the first State change.
    loadQualityGeoOptions();
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
    $('resetQualityFiltersBtn')?.addEventListener('click', async () => {
      QUALITY_FILTER_IDS.forEach((id) => {
        const node = $(id);
        if (node) node.value = id === 'dqStatusFilter' ? 'all' : '';
      });
      if (typeof clearReportFilterSearch === 'function') clearReportFilterSearch($('resetQualityFiltersBtn'));
      // County/City were narrowed to the cleared State, so put the full lists
      // back before the query runs - otherwise "Reset All" leaves a rail
      // still showing one state's counties. Tab 1's Reset All awaits the same
      // call for the same reason.
      await loadQualityGeoOptions();
      // Same reason as Apply: this clears every filter and runs the query
      // itself, so anything the switch had queued is stale.
      qualityAutoApply?.cancel();
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
