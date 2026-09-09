import inspect
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "ui" / "integrations.html").read_text()
COMMON_JS = (ROOT / "ui" / "js" / "common.js").read_text()


def test_header_groups_keep_primary_tabs_and_compact_utilities():
    assert '<nav class="top-tabs" aria-label="Primary navigation">' in HTML
    assert '<div class="header-data-actions">' in HTML
    assert '<div class="header-account-actions">' in HTML
    assert 'grid-template-areas: "title tabs utilities"' in HTML
    assert 'grid-template-areas: "sample reset zipstatus" "sample restart zipsync"' in HTML
    assert '.header-account-actions { display: flex; flex-direction: row;' in HTML
    assert '.header-account-actions #appHelpBtn::before' in HTML
    assert 'el("restartMappingBtn").classList.toggle("hidden", viewId !== "mapperView")' not in COMMON_JS
    # Reversal of an earlier decision (2026-09-09, explicit user request):
    # Reset Fields Mapping only makes sense on the Mapper tab and must be
    # hidden elsewhere again - Restart Mapping was not part of that ask and
    # stays visible everywhere, per the assertion just above.
    assert 'el("resetMappingBtn")?.classList.toggle("hidden", viewId !== "mapperView");' in COMMON_JS
    assert '.top-tab {' in HTML
    assert 'font-size: 14px;' in HTML

    sample_index = HTML.index('id="loadSampleDatasetHeaderBtn"')
    reset_index = HTML.index('id="resetMappingBtn"')
    restart_index = HTML.index('id="restartMappingBtn"')
    zip_index = HTML.index('id="headerReadinessStatus"')
    sync_index = HTML.index('id="testReadinessBtn"')

    assert sample_index < reset_index < restart_index < zip_index < sync_index


def test_sample_dataset_load_is_single_shared_header_action():
    assert HTML.count('id="loadSampleDatasetHeaderBtn"') == 1
    assert 'id="loadSampleDatasetBtn"' not in HTML
    assert 'el("loadSampleDatasetBtn")?.addEventListener' in HTML


def test_reporting_hero_actions_are_refresh_and_download_only():
    # Clear Sample Data lives with Load Sample Dataset in the header now (see
    # test_clear_sample_data_sits_directly_below_load_sample_in_header), so
    # the Reporting hero itself only carries Refresh Report + Download Excel.
    assert 'id="refreshReportBtn"' in HTML
    assert 'id="downloadSampleCsvBtn"' in HTML
    assert 'id="reloadSampleDatasetLink"' not in HTML
    assert 'grid-template-columns: auto auto;' in HTML
    assert 'justify-content: end;' in HTML
    assert '.sample-load-link.danger' in HTML
    assert 'min-height: 44px;' in HTML
    assert 'background: #dc2626;' in HTML
    assert 'refreshReportingNow();' in HTML
    assert 'el("clearSampleDatasetLink")?.addEventListener("click", () => clearSampleDataset());' in HTML
    assert 'el("reloadSampleDatasetLink")?.addEventListener' in HTML


def test_clear_sample_data_sits_directly_below_load_sample_in_header():
    # Both sample-dataset controls now live together in the header's
    # "sample" grid cell: Load Sample Dataset on top, Clear Sample Data
    # directly below it, same red/danger styling as before the move.
    stack = HTML.split('<div class="sample-dataset-stack">', 1)[1].split('</div>', 1)[0]
    assert 'id="loadSampleDatasetHeaderBtn"' in stack
    assert 'id="clearSampleDatasetLink"' in stack
    assert stack.index('id="loadSampleDatasetHeaderBtn"') < stack.index('id="clearSampleDatasetLink"')
    assert 'sample-load-link danger hidden' in stack
    assert '.header-data-actions .sample-dataset-stack { grid-area: sample;' in HTML


def test_sample_dataset_button_has_idle_loading_ready_color_states():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert 'sample-state-idle' in HTML
    assert '#loadSampleDatasetHeaderBtn.sample-state-loading' in HTML
    assert '#loadSampleDatasetHeaderBtn.sample-state-ready' in HTML
    assert "sampleButton.classList.toggle('sample-state-ready', loaded);" in mapper_js
    assert "sampleButton.classList.toggle('sample-state-idle', !loaded);" in mapper_js


def test_sample_load_success_shows_confirmation_popup():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert '<dialog id="sampleLoadedDialog"' in HTML
    assert 'const dialog = el("sampleLoadedDialog");' in mapper_js
    assert 'dialog.showModal();' in mapper_js


def test_reporting_quality_uses_existing_single_internal_view_module():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    server_py = (ROOT / "whitespace_tool" / "workflow_server.py").read_text()
    schema_py = (ROOT / "whitespace_tool" / "warehouse_bigquery.py").read_text()

    assert 'src="reporting-tabs.js?v=quality-layout-v4"' in HTML
    assert "tabs.id = 'reportingInnerTabs'" in reporting_tabs_js
    assert 'data-report-tab="location"' in reporting_tabs_js
    assert 'data-report-tab="quality"' in reporting_tabs_js
    assert "sessionStorage.setItem('reportingInnerTab', nextTab)" in reporting_tabs_js
    assert "sessionStorage.getItem('reportingInnerTab') === 'quality'" in reporting_tabs_js
    assert 'id="reportLocationsTab"' not in HTML
    assert 'id="reportQualityTab"' not in HTML
    assert 'fetch(`/api/reporting/quality' in reporting_tabs_js
    assert 'reporting_quality_snapshots' in server_py
    assert '"name": "snapshot_date"' in schema_py
    assert '"name": "content_hash"' in schema_py


def test_reporting_quality_loader_does_not_blank_location_tab():
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    load_quality = reporting_tabs_js.split("async function loadQuality", 1)[1].split("\n  function init()", 1)[0]

    assert "const activeTab = sessionStorage.getItem('reportingInnerTab') === 'quality' ? 'quality' : 'location';" in load_quality
    assert "classList.toggle('hidden', activeTab !== 'location')" in load_quality
    assert "quality.classList.toggle('hidden', activeTab !== 'quality')" in load_quality
    assert "dataset.reportTab === activeTab" in load_quality
    assert "classList.add('hidden'));" not in load_quality


def test_reporting_location_loader_does_not_fail_silently():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    catch_block = reporting_js.split("async function loadReporting", 1)[1].split("} catch (error) {", 1)[1].split("} finally {", 1)[0]

    assert "renderEmptyReportingStructure();" in catch_block
    assert 'status.className = "report-status";' in catch_block
    assert 'No reporting records found for the current filters.' in catch_block
    assert "reportLoaded = false;" in catch_block
    assert "if (interactive)" not in catch_block


def test_reporting_location_first_tab_loader_wires_all_real_panels():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    load_reporting = reporting_js.split("async function loadReporting", 1)[1].split("function startEnrichmentStatusPolling", 1)[0]

    assert "renderEmptyReportingStructure();" in load_reporting
    assert 'fetch(`/api/reporting${queryString ? `?${queryString}` : ""}`)' in load_reporting
    assert "syncReportingFilters(result);" in load_reporting
    assert 'el("reportContent").classList.remove("hidden");' in load_reporting
    for kpi_id in [
        "reportLocations", "reportBrands", "reportStates", "reportCities",
        "reportZips", "reportStores", "reportBrandStates", "reportWhitespaceGaps",
    ]:
        assert f'el("{kpi_id}")' in load_reporting
    assert "renderReportingMap(result.map_records || [], result.gaps || [], result.top_states || [], result.filters || {});" in load_reporting
    for table_id in [
        "reportTopStates", "reportTopCities", "reportBrandsTable",
        "reportSampleRecords",
    ]:
        assert f'renderSimpleTable("{table_id}"' in load_reporting
    assert "renderMarketGapsWithPagination(result.gaps || [], 1);" in load_reporting
    assert "currentSampleRecords = result.sample_records || [];" in load_reporting
    assert "reportLoaded = true;" in load_reporting


def test_reporting_location_empty_structure_initializes_visible_first_tab_contract():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    empty_renderer = reporting_js.split("function renderEmptyReportingStructure()", 1)[1].split("function productSafeError", 1)[0]

    assert 'el("reportContent").classList.remove("hidden");' in empty_renderer
    for kpi_id in [
        "reportLocations", "reportBrands", "reportStates", "reportCities",
        "reportZips", "reportStores", "reportBrandStates", "reportWhitespaceGaps",
    ]:
        assert f'el("{kpi_id}")' in empty_renderer
    assert "renderReportingMap([], [], []);" in empty_renderer
    assert 'el("reportTopStateCards").innerHTML' in empty_renderer
    for table_id in [
        "reportTopStates", "reportTopCities", "reportBrandsTable",
        "reportGapsTable", "reportSampleRecords",
    ]:
        assert f'renderSimpleTable("{table_id}"' in empty_renderer
    assert "Every tracked state and territory has at least one active location." in empty_renderer


def test_reporting_filter_category_titles_stay_single_line_when_space_allows():
    # The filter-rail unification renamed this class:
    # .report-filter-category-title -> .report-filter-section-title, defined
    # once and used by BOTH reporting rails. The contract is unchanged - the
    # headings must not wrap inside a 290px rail - so the assertion is
    # retargeted at the new name rather than dropped.
    assert "report-filter-category-title" not in HTML, "old class name resurrected"
    rule = HTML.split(".report-filter-section-title {", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap;" in rule
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    # Both rails write the heading with the shared class and no inline style.
    for marker in (
        '<div class="report-filter-section-title">&#128205; Geographic Filters</div>',
        '<div class="report-filter-section-title">&#127991;&#65039; Brand Filters</div>',
    ):
        assert marker in HTML, marker
        assert marker in tabs_js, marker
    assert '<div class="report-filter-section-title">&#128101; Demographic Filters</div>' in HTML


def test_reporting_zip_filter_has_debounced_scoped_typeahead():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    # setupZipTypeahead now serves BOTH filter rails, so it takes the rail's
    # control ids instead of hard-coding the Location tab's.
    typeahead = reporting_js.split("function setupZipTypeahead(rail = REPORT_GEO_RAIL)", 1)[1].split("function reportingQueryString()", 1)[0]

    assert 'id="reportZipFilter" list="zipSuggestions"' in HTML
    assert 'id="zipSuggestions"' in HTML
    # Debounce timer and request id are per rail (closure state), NOT module
    # level: shared state would let a keystroke on one rail cancel the other
    # rail's in-flight request and silently drop its suggestions.
    assert "let zipTypeaheadRequestId = 0;" not in reporting_js
    assert "let typeaheadTimer = null;" in typeahead
    assert "let latestRequestId = 0;" in typeahead
    assert 'zipInput.addEventListener("input"' in typeahead
    assert "if (!query)" in typeahead
    assert "query.length < 2" not in typeahead
    assert 'datalist.innerHTML = "";' in typeahead
    assert "setTimeout(async () =>" in typeahead
    assert "}, 250);" in typeahead
    # Scoped by this rail's own State -> County -> City cascade.
    assert "el(rail.state)?.value" in typeahead
    assert "el(rail.county)?.value" in typeahead
    assert "el(rail.city)?.value" in typeahead
    assert "fetch(`/api/zips/search?q=${encodeURIComponent(query)}&state=${encodeURIComponent(state)}&county=${encodeURIComponent(county)}&city=${encodeURIComponent(city)}`)" in typeahead
    # Out-of-order responses are dropped, per rail.
    assert "if (requestId !== latestRequestId) return;" in typeahead


def test_refresh_report_button_starts_backend_refresh_and_shows_status():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    refresh_function = reporting_js.split("async function refreshReportingNow()", 1)[1].split("function startEnrichmentStatusPolling", 1)[0]

    assert "refreshReportingNow();" in HTML
    assert 'fetch("/api/reporting/refresh"' in refresh_function
    assert 'method: "POST"' in refresh_function
    assert 'body: JSON.stringify({ low_priority: true })' in refresh_function
    # No duplicate status line: the Refresh button itself shows the
    # in-flight state with a spinner, and its reserved height was the
    # empty band under the button.
    assert "Report refresh started. Updating numbers" not in refresh_function
    assert "Report refresh is already running" not in refresh_function
    assert 'if (status) status.classList.add("hidden");' in refresh_function
    assert "await loadReporting({ interactive: true });" in refresh_function
    assert "clearButtonBusy(refreshBtn, previousRefreshBtn);" in refresh_function


def test_interactive_reporting_reload_keeps_visible_background_refresh_status():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    load_reporting = reporting_js.split("async function loadReporting", 1)[1].split("async function refreshReportingNow", 1)[0]

    assert "interactive && result.refreshing" in load_reporting
    # The redundant "Refreshing report in the background..." status line was
    # removed - the Refresh Report button itself already shows "Refreshing
    # Reports" with a spinner while this is in flight (see
    # test_single_shared_refresh_report_button_drives_both_reporting_tabs-
    # adjacent button-label tests), so this branch just hides the status line.
    assert "Refreshing report in the background..." not in load_reporting
    assert "if (interactive && !result.refreshing) status.classList.add(\"hidden\");" not in load_reporting
    assert "if (interactive && !result.refreshing && hasBusinessData) status.classList.add(\"hidden\");" in load_reporting


def test_reporting_zero_setup_polls_frequently_until_business_data_exists():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    load_reporting = reporting_js.split("async function loadReporting", 1)[1].split("async function refreshReportingNow", 1)[0]

    assert "let reportingWarmupTimer = null;" in reporting_js
    assert "function reportHasBusinessData" in reporting_js
    assert "function scheduleReportingWarmupPoll" in reporting_js
    assert "window.setTimeout" in reporting_js
    assert "Preparing reporting data" in load_reporting
    assert "scheduleReportingWarmupPoll(3000);" in load_reporting
    assert "clearTimeout(reportingWarmupTimer);" in load_reporting


def test_reporting_tab_refresh_preserves_selected_inner_tab():
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    init_block = reporting_tabs_js.split("function init()", 1)[1]

    assert "new URLSearchParams(window.location.search).get('reportTab')" in init_block
    assert "sessionStorage.getItem('reportingInnerTab')" in init_block
    assert "initialTab = requestedTab === 'quality' ? 'quality' : (sessionStorage.getItem('reportingInnerTab') === 'quality' ? 'quality' : 'location');" in init_block
    assert "switchTab(initialTab);" in init_block
    # The Data Quality tab no longer has its own refresh button - the
    # shared Reporting-hero "Refresh Report" button drives it instead,
    # via window.reportingRefreshQuality (see test_single_shared_refresh_
    # report_button_drives_both_reporting_tabs).
    assert "window.reportingRefreshQuality = () => loadQuality(true);" in init_block


def test_reporting_has_both_tab_panels_and_switches_each_independently():
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    switch_tab = reporting_tabs_js.split("function switchTab(name)", 1)[1].split("tabs.addEventListener", 1)[0]

    assert 'data-report-tab="location"' in reporting_tabs_js
    assert 'data-report-tab="quality"' in reporting_tabs_js
    assert "shell.querySelectorAll('.report-location-panel').forEach((n) => n.classList.toggle('hidden', name !== 'location'));" in switch_tab
    assert "quality.classList.toggle('hidden', name !== 'quality');" in switch_tab
    assert "if (name === 'quality') loadQuality();" in switch_tab
    assert "if (name === 'location') {" in switch_tab
    assert "typeof window.reportingMap?.invalidateSize === 'function'" in switch_tab
    # Extended Coverage Metrics / Trends Over Time / Top States moved to
    # tab 1 (RPT-05/06/07), so they load with it rather than with the
    # quality tab - switchTab(initialTab) at init covers first paint too.
    assert "loadExtendedMetrics();" in switch_tab


def test_mapping_first_render_has_pre_parse_workspace_and_dark_header_logo():
    assert 'data-logo-src="birdeyeLogoDarkUrl"' in HTML
    assert '<div id="mapperView" class="pre-parse-active preparse-booting">' in HTML
    assert 'id="preParseBrandPanel"' in HTML
    assert 'id="preParseBrandHost"' in HTML
    assert 'id="preParseParserHost"' in HTML
    assert 'id="parserBusinessSelect"' in HTML
    assert 'id="parserBusinessValidation"' in HTML
    assert '#mapperView.pre-parse-active aside > .panel:not(#sourceControlsPanel):not(.left-rail-persistent) { display: none; }' in HTML
    assert '#mapperView.preparse-booting .left-rail-persistent { visibility: hidden; }' in HTML
    assert '#mapperView.preparse-booting > #status { visibility: hidden; }' in HTML
    assert '<div class="panel left-rail-persistent">\n        <h2>Brand Entity Resolution</h2>' in HTML
    assert '<div class="panel left-rail-persistent">\n        <h2>Job History</h2>' in HTML
    assert '<div class="panel data-danger-panel left-rail-persistent">\n        <h2>&#9888;&#65039; Data Controls</h2>' in HTML
    assert 'js/mapper.js?v=preparse-layout-v6' in HTML


def test_mapper_booting_gate_clears_after_pre_parse_hosts_are_synced():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    render_fn = mapper_js.split("function renderMappings()", 1)[1].split("\nfunction syncPreParseWorkspace", 1)[0]
    sync_fn = mapper_js.split("function syncPreParseWorkspace", 1)[1].split("\nfunction updatePreParseBrandMode", 1)[0]

    assert 'if (hasMappingContent) mapperView?.classList.remove("preparse-booting");' in render_fn
    assert 'el("mapperView")?.classList.remove("preparse-booting");' in sync_fn
    assert sync_fn.index('parserHost.classList.remove("hidden");') < sync_fn.index('classList.remove("preparse-booting")')


def test_country_is_available_but_not_mandatory_in_mapper():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    registry = (ROOT / "config" / "field_registry.json").read_text()

    assert '{ key: "country", table: "listings", field: "country", label: "Country", required: false' in mapper_js
    assert '"key":"country","table":"listings","field":"country","label":"Country","type":"string","required":false' in registry


def test_only_brand_is_mandatory_across_field_config_and_db_level():
    # Everything except brand relaxed to optional, at every layer: the
    # field registry (drives the mapper UI + validate_normalized_location),
    # the mapper-shape gate (validate_mapper), the per-row acceptance gate
    # (normalize_location), the redundant required-values recheck later in
    # save_mapper, and the BigQuery listings schema itself.
    server_py = (ROOT / "whitespace_tool" / "workflow_server.py").read_text()
    registry_json = json.loads((ROOT / "config" / "field_registry.json").read_text())
    normalization_py = (ROOT / "whitespace_tool" / "normalization.py").read_text()
    warehouse_py = (ROOT / "whitespace_tool" / "warehouse_bigquery.py").read_text()

    assert 'REQUIRED_MAPPER_FIELDS: set[str] = set()' in server_py
    assert 'REQUIRED_LOCATION_VALUES: tuple[str, ...] = ()' in server_py
    assert 'if not brand:\n        return None' in normalization_py

    non_brand_required = [f["key"] for f in registry_json if f.get("required") and f["key"] != "brand"]
    assert non_brand_required == []

    for column in ("name", "address", "city_name", "state_code", "zip_code", "country"):
        assert f'"name": "{column}", "type": "STRING", "mode": "NULLABLE"' in warehouse_py


def test_parse_once_keeps_standard_mapping_workspace_until_reset():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    assert "let mappingWorkspaceActivated = false;" in mapper_js
    assert "mappingWorkspaceActivated || sourceParsed || sourceFields.length || activeTemplateId" in mapper_js
    assert "sourceParsed = true;\n        pendingUnsavedParse = true;\n        mappingWorkspaceActivated = true;" in mapper_js
    assert "sourceParsed = false;\n      pendingUnsavedParse = false;\n      mappingWorkspaceActivated = false;" in mapper_js


def test_restart_mapping_returns_to_fresh_pre_parse_workspace():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    assert 'sessionStorage.removeItem(draftStorageKey);' in mapper_js
    assert 'sessionStorage.setItem("activeTab", "mapperView");' in mapper_js
    assert 'restartUrl.searchParams.set("view", "mapperView");' in mapper_js
    assert 'window.location.assign(restartUrl.toString());' in mapper_js


def test_mapper_boot_refresh_does_not_restore_old_mapping_draft():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    restore_fn = mapper_js.split("function restoreDraft()", 1)[1].split("\nasync function loadFieldRegistry", 1)[0]

    assert 'const bootView = new URLSearchParams(window.location.search).get("view") || sessionStorage.getItem("activeTab") || "mapperView";' in restore_fn
    assert 'if (bootView === "mapperView") {' in restore_fn
    assert 'sessionStorage.removeItem(draftStorageKey);' in restore_fn
    assert 'const draft = JSON.parse(sessionStorage.getItem(draftStorageKey) || "null");' in restore_fn
    assert restore_fn.index('if (bootView === "mapperView") {') < restore_fn.index('const draft = JSON.parse(sessionStorage.getItem(draftStorageKey) || "null");')


def test_selected_brand_locks_required_brand_name_mapping():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    render_fn = mapper_js.split("function renderMappings()", 1)[1].split("\nfunction syncPreParseWorkspace", 1)[0]
    save_fn = mapper_js.split("async function saveMapper()", 1)[1].split("\nfunction resetMapping", 1)[0]

    assert '{ key: "name", table: "listings", field: "name", label: "Brand Name", required: true' in mapper_js
    assert 'mappingSelections.name = "__brand";' in render_fn
    assert 'const isLockedBrandMapping = target.key === "name" && selected === "__brand" && Boolean(selectedBrand?.business_id);' in render_fn
    assert 'disabled title="Brand is fixed by the selected dropdown value."' in render_fn
    assert 'sourceField === "__brand" ? formatBrandName(selectedBrand?.name || "Selected brand") : sourceField' in render_fn
    assert 'if (path === "__brand") return formatBrandName(selectedBrand?.name || "");' in mapper_js
    assert 'rows: batch.rows.map((row) => mappingSelections.name === "__brand" ? { ...row, __brand: selectedBrand?.name || mapper.brand } : row),' in save_fn
    assert 'source_fields: mapper.source_fields || sourceFields,' in save_fn


def test_brand_selection_does_not_auto_open_edit_form_before_parse():
    html = (ROOT / "ui" / "integrations.html").read_text()
    brand_change = html.split('el("brandSelect").addEventListener("change"', 1)[1].split('el("parserBusinessSelect")?.addEventListener("change"', 1)[0]
    explicit_edit_change = html.split('el("preParseEditBrand")?.addEventListener("change"', 1)[1].split('el("defaultBrandModelBtn")', 1)[0]

    assert 'openBrandEditorForm("edit")' not in brand_change
    assert 'openBrandEditorForm("edit")' in explicit_edit_change


def test_pre_parse_requires_saved_business_before_source_parse():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    assert 'id="preParseBrandValidation"' in HTML
    assert 'id="parserBusinessValidation"' in HTML
    assert 'id="brandSelectValidation"' in HTML
    assert 'Select an existing brand or create a new one before parsing.' in mapper_js
    assert 'function setPreParseBrandValidation' in mapper_js
    assert 'function hasSelectedBusiness' in mapper_js
    assert 'function syncParserBusinessSelect' in mapper_js
    assert 'function setBusinessSelectValue' in mapper_js
    assert 'let businessRequirementTouched = false;' in mapper_js
    assert 'el("mapperView")?.classList.contains("pre-parse-active") && !hasSelectedBusiness()' in mapper_js
    assert 'value !== "__create_new__"' in mapper_js


def test_pre_parse_business_warning_is_not_duplicated_or_on_load():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    assert 'const ids = inPreParse ? ["parserBusinessValidation"] : ["brandSelectValidation"];' in mapper_js
    assert 'if (hasSelectedBusiness()) setPreParseBrandValidation("");' in mapper_js
    assert 'if (!hasSelectedBusiness()) setPreParseBrandValidation("Select an existing brand or create a new one before parsing.");' not in mapper_js.split('function updatePreParseBrandMode()', 1)[1].split('function openBrandEditorForm', 1)[0]
    assert 'setStatus(message, "warn");' not in mapper_js.split('async function parseSource()', 1)[1].split('setPreParseBrandValidation("");', 1)[0]


def test_source_setup_switches_do_not_show_missing_url_warning():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    for function_name in ["resetCsvDemoLock", "resetExcelDemoLock", "resetJsonDemoLock", "resetXmlDemoLock", "resetApiDemoLock"]:
        body = mapper_js.split(f"function {function_name}", 1)[1].split("\n    }", 1)[0]
        assert 'sourceReadyToParseMessage()' not in body
        assert 'Choose a source and parse it to start mapping in left pane.' in body


def test_pre_parse_parser_heading_stays_above_status_message():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    assert 'const parserTitle = parserHost.querySelector("h2");' in mapper_js
    assert 'parserHost.insertBefore(status, parserTitle?.nextSibling || parserHost.firstChild);' in mapper_js


def test_mapper_typography_is_externalized_and_responsive():
    mapper_css = (ROOT / "ui" / "css" / "mapper.css").read_text()

    assert 'href="css/mapper.css?v=parser-type-v1"' in HTML
    assert "#mapperView #preParseParserHost" in mapper_css
    assert "font-size: 16px;" in mapper_css
    assert "@media (max-width: 900px)" in mapper_css
    assert "#mapperView main.pre-parse-layout" in mapper_css


def test_mapper_css_does_not_override_global_app_styles():
    mapper_css = (ROOT / "ui" / "css" / "mapper.css").read_text()

    forbidden_global_selectors = [
        "\nbody",
        "\nhtml",
        "\ninput",
        "\nselect",
        "\ntextarea",
        "\nbutton",
        "\nlabel",
        "\nmain",
        "\naside",
        "\n.panel",
      ]
    for selector in forbidden_global_selectors:
        assert selector not in mapper_css

    selectors = [line.strip() for line in mapper_css.splitlines() if line.strip().endswith("{")]
    assert selectors
    assert all(
        selector.startswith("#mapperView") or selector.startswith("@media")
        for selector in selectors
    )


def test_unmatched_demo_brand_opens_prefilled_create_form_generically():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    helper = mapper_js.split("function openPrefilledBrandCreateForm", 1)[1].split("function dominosPythonCode", 1)[0]
    sync_brand = mapper_js.split("function syncBrandSelection", 1)[1].split("function fillDominosBrand", 1)[0]

    assert 'presetCreateMode = Boolean(activeCsvPresetConfig);' in helper
    assert 'el("brandSelect").value = "__create_new__";' in helper
    assert 'syncParserBusinessSelect();' in helper
    assert 'el("newBrandFields").classList.remove("hidden");' in helper
    assert 'el("brandFormHeading").textContent = brandConfig.name ? `Create ${brandConfig.name}` : "Create new brand";' in helper
    assert 'fillBrandFields({}, brandConfig);' in helper
    assert 'openPrefilledBrandCreateForm(brandConfig);' in sync_brand
    for function_name in ["applyCsvPreset", "applyDemoRestaurantExcel", "applyDominosJsonFunction", "applyDemoXml", "applyLittleCaesarsApiDemo", "applyDemoPeBrandFunction"]:
        assert function_name in mapper_js
    assert 'fillBrandFromConfig(activeCsvPresetConfig.brand);' in mapper_js


def test_brand_form_dialog_uses_mapper_scoped_blue_white_styles():
    mapper_css = (ROOT / "ui" / "css" / "mapper.css").read_text()

    assert "#mapperView #newBrandFields.brand-edit-modal.is-open" in mapper_css
    assert "border-top: 4px solid var(--accent);" in mapper_css
    assert "background: rgba(239, 246, 255, 0.82);" in mapper_css
    assert "#newBrandFields.brand-edit-modal.is-open" not in HTML


def test_brand_description_fields_start_compact_and_auto_grow():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    mapper_css = (ROOT / "ui" / "css" / "mapper.css").read_text()

    assert "#mapperView #newBrandDescription" in mapper_css
    assert "#mapperView #newBrandMetaDescription" in mapper_css
    assert "height: 38px;" in mapper_css
    assert "max-height: 140px;" in mapper_css
    assert "function autoGrowBrandTextarea" in mapper_js
    assert "function autoGrowBrandTextareas" in mapper_js
    assert "autoGrowBrandTextareas();" in mapper_js
    assert 'el("newBrandDescription").addEventListener("input"' in HTML
    assert 'el("newBrandMetaDescription").addEventListener("input"' in HTML


def test_single_shared_refresh_report_button_drives_both_reporting_tabs():
    # There must be exactly one refresh control on the whole Reporting view
    # (the hero's "Refresh Report" button) - the Data Quality tab's own
    # "Refresh Quality Metrics" button was removed so refreshing never
    # requires knowing which of the two inner tabs you're looking at.
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()

    assert 'refreshDataQualityBtn' not in reporting_tabs_js
    assert 'refreshDataQualityBtn' not in HTML
    assert 'id="refreshReportBtn"' in HTML
    assert 'window.reportingRefreshQuality = () => loadQuality(true);' in reporting_tabs_js
    assert 'if (typeof window.reportingRefreshQuality === "function") window.reportingRefreshQuality();' in reporting_js
    # It must fire after the location tab's own refresh resolves, inside
    # refreshReportingNow's try block - not detached from the click handler.
    refresh_now = reporting_js.split("async function refreshReportingNow()", 1)[1].split("\nfunction ", 1)[0]
    assert "await loadReporting({ interactive: true });" in refresh_now
    assert "window.reportingRefreshQuality" in refresh_now


def test_quality_tab_loading_hides_body_without_blocking_tab_switch():
    # Both the first load and a shared refresh must fully hide #dqBody
    # behind #dqLoadingPanel (no stale numbers visible underneath), while
    # switchTab itself stays reachable - it must not be gated on any
    # "is quality data loading" flag.
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    load_quality = reporting_tabs_js.split("async function loadQuality", 1)[1].split("\n  function init()", 1)[0]

    assert "if (loadingPanel) loadingPanel.classList.remove('hidden');" in load_quality
    assert "if (body) body.classList.add('hidden');" in load_quality

    switch_tab = reporting_tabs_js.split("function switchTab(name)", 1)[1].split("\n    tabs.addEventListener", 1)[0]
    assert "loading" not in switch_tab.lower()
    assert "disabled" not in switch_tab


def test_login_readiness_copy_states_what_is_happening():
    login_js = (ROOT / "ui" / "js" / "login.js").read_text()
    assert "You can sign in now — this finishes in the background." in login_js
    assert "You can sign in now — maps and filters will sharpen as reference data finishes syncing." in login_js
    # The old vague "start working" / "will improve" phrasing must be gone.
    assert "Sign in now and start working." not in login_js
    assert "will improve as reference data" not in login_js


def test_sample_dataset_button_label_matches_its_own_already_loaded_copy():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    # Half-loaded and fully-loaded are now different states, so the copy is
    # different too: a plain "Loaded" while the second NTILE(2) half is still
    # landing, a ticked "Already Loaded" only once every source row is in.
    assert '"The whole sample dataset is in place."' in mapper_js
    assert "Part of the sample dataset is in place" in mapper_js
    assert '(complete ? "\\u2713 Sample Dataset Already Loaded" : "Sample Dataset Loaded")' in mapper_js
    assert '"Load Sample Dataset";' in mapper_js


def test_enrichment_status_polling_stops_after_terminal_state():
    # startEnrichmentStatusPolling's setInterval used to run forever with no
    # stop condition - once it ever saw the job running, it must clear
    # itself the next time the job is no longer running (idle/stopped/failed).
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    assert "function stopEnrichmentStatusPolling()" in reporting_js
    assert "window.clearInterval(enrichmentStatusTimer);" in reporting_js
    poll_fn = reporting_js.split("function startEnrichmentStatusPolling()", 1)[1].split("\nasync function refreshReportingData", 1)[0]
    assert "let sawWork = false;" in poll_fn
    assert "if (running || eased) sawWork = true;" in poll_fn
    # "eased" is NOT terminal (renamed from sawRunning for exactly this): the
    # queue is still draining under the throttle, and the toggle has to keep
    # reflecting the server's pace or it sits offering the wrong action. So an
    # eased run keeps polling - at the quiet cadence rather than every 3s.
    assert "if (sawWork && !running && !eased) {" in poll_fn
    assert "stopEnrichmentStatusPolling();" in poll_fn
    assert "const wanted = running ? ENRICHMENT_POLL_MS : ENRICHMENT_QUIET_POLL_MS;" in poll_fn


def test_template_page_cache_evicts_expired_entries_on_write():
    # templatePageCache is a module-level Map keyed by search/filter/page -
    # entries were only ever added, never removed, so a long Template
    # Library session grew it unbounded. Expired entries must be swept out
    # whenever a new entry is written.
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    fetch_fn = templates_js.split("async function _fetchTemplatesPage", 1)[1].split("\nfunction _renderTemplateRows", 1)[0]
    assert "for (const [key, entry] of templatePageCache) {" in fetch_fn
    assert "if (now - entry.createdAt >= TEMPLATE_CACHE_TTL_MS) templatePageCache.delete(key);" in fetch_fn


def test_wide_tables_scroll_instead_of_clipping_app_wide():
    # A bare <table> with overflow:hidden silently clipped columns that
    # overflowed a narrow viewport instead of letting the user scroll to
    # see them - this applied everywhere renderSimpleTable() or a raw
    # <table> markup string is used (reporting.js, reporting-tabs.js's
    # Data Quality tables). Fixed once, app-wide, via a CSS rule that gives
    # any div directly wrapping a table horizontal scroll, rather than
    # patching every table's markup individually.
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()

    table_rule = HTML.split("table {", 1)[1].split("}", 1)[0]
    assert "overflow: hidden" not in table_rule
    assert "div:has(> table) {" in HTML
    has_table_rule = HTML.split("div:has(> table) {", 1)[1].split("}", 1)[0]
    assert "overflow-x: auto" in has_table_rule

    dq_table_rule = reporting_tabs_js.split(".dq-table{", 1)[1].split("}", 1)[0]
    assert "overflow:hidden" not in dq_table_rule


def test_state_distribution_and_top_cities_stack_full_width_with_extra_metrics():
    # Both tables grew from 3 columns to 6+ (population, median income,
    # pop/listing, subject-vs-competitor split) - a cramped 2-column
    # side-by-side layout no longer fits either comfortably, so they're
    # stacked full-width instead, each independently horizontally
    # scrollable via the generic div:has(> table) rule.
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()

    assert 'id="reportStateCityTables" class="report-columns" style="display: grid; grid-template-columns: 1fr;' in HTML
    # .reporting-main-pane .report-columns forces 2 columns with !important -
    # an ID selector is required to outrank it for this specific instance.
    assert ".reporting-main-pane #reportStateCityTables {" in HTML
    override_rule = HTML.split(".reporting-main-pane #reportStateCityTables {", 1)[1].split("}", 1)[0]
    assert "grid-template-columns: 1fr !important;" in override_rule

    assert '{ key: "median_household_income", label: "Median Income"' in reporting_js
    assert '{ key: "city_population", label: "Population"' in reporting_js
    assert '{ key: "pop_per_listing", label: "Population Per Listing"' in reporting_js
    assert "const hasBrandVsCompetitorFilter = Boolean((result.filters?.main_brands || []).length && (result.filters?.competitor_brands || []).length);" in reporting_js
    assert '{ key: "main_brand_locations", label: "Subject Brand Listings", format: formatNumber }' in reporting_js
    assert '{ key: "competitor_brand_locations", label: "Competitor Listings", format: formatNumber }' in reporting_js


def test_save_completion_message_shows_inserted_duplicate_and_review_counts():
    # save_mapper() already computed duplicate_listings_skipped - it just
    # wasn't surfaced. "X inserted, Y duplicate, Z need review" replaces
    # the older "N records processed" wording, which hid whether any of
    # those N were actually duplicates skipped rather than newly inserted.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    save_fn = mapper_js.split("async function saveMapper()", 1)[1].split("\nfunction showSaveCompletion", 1)[0]

    assert "duplicateListings += result.duplicate_listings_skipped || 0;" in save_fn
    assert "const insertedCount = Math.max(0, mappedRows - duplicateListings);" in save_fn
    # Compact one-line summary: names the brand and source type (not just
    # bare counts), so it reads clearly on its own if the user only sees it
    # after a backgrounded save finished.
    assert "const brandLabel = mapper.brand ? formatBrandName(mapper.brand) : \"This brand\";" in save_fn
    assert '`${prefix}${brandLabel} ${sourceLabel}: ${sourceRows.length} read, ${insertedCount} saved${duplicateNote}, ${errorListings} need${errorListings === 1 ? "s" : ""} review${reviewNote}.`' in save_fn


def test_preparing_records_status_uses_spinner_not_ellipsis():
    # setStatus() writes plain textContent, so a "..." string could never
    # actually show a spinner through it - this bypasses setStatus for this
    # one message and builds the same spinner markup busyMarkup() uses
    # elsewhere, dropping the trailing ellipsis to match that convention.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert 'statusEl.innerHTML = \'<span class="spinner"></span> Preparing your records\';' in mapper_js
    assert 'setStatus("Preparing your records...", "");' not in mapper_js


def test_job_history_panel_exists_and_is_populated_after_save_and_reprocess():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()

    assert 'id="jobHistoryList"' in HTML
    # Sits directly below Brand Entity Resolution (renamed from "Data
    # Enrichment"), per the explicit placement ask.
    assert HTML.index("<h2>Brand Entity Resolution</h2>") < HTML.index("<h2>Job History</h2>")
    assert "async function loadJobHistory()" in mapper_js
    assert "const JOB_HISTORY_PANEL_LIMIT = 10;" in mapper_js
    assert "fetch(`/api/jobs/recent?limit=${JOB_HISTORY_PANEL_LIMIT}`)" in mapper_js
    assert "loadJobHistory();" in mapper_js.split("showSaveCompletion(", 1)[1][:400]
    assert "if (typeof loadJobHistory === \"function\") loadJobHistory();" in review_js


def test_adopting_a_suggestion_or_hierarchy_option_counts_as_ai_fixed():
    # reprocess_rejected() branches AI vs manual fix attribution purely on
    # the is_ai_enriched flag in the request payload - adopting either the
    # quick-fill ZIP suggestion or a hierarchy-conflict option must set it,
    # even though a human clicked a button, per the explicit decision that
    # an adopted suggestion counts as an automatic fix.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "let suggestionAdopted = false;" in review_js
    assert review_js.count("suggestionAdopted = true;") >= 2  # quick-fill button + hierarchy picker
    assert "is_ai_enriched: suggestionAdopted" in review_js


def test_retry_button_splits_into_ai_suggested_vs_manual_review_with_attempt_badge():
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    # Icon updated: the AI action now carries an AI-depicting robot rather
    # than a generic lightbulb (see test_the_ai_action_carries_an_ai_icon...).
    assert 'data-open-edit="${escapeHtml(record.row_number)}" data-event="${escapeHtml(record.event_id)}" style="background:#1677ee; border-color:#1677ee; color:#fff;">\U0001F916 AI Suggested Fix</button>' in review_js
    assert 'data-open-edit="${escapeHtml(record.row_number)}" data-event="${escapeHtml(record.event_id)}" style="background:#fff; border-color:#d97706; color:#b45309;">🛠️ Manual Review</button>' in review_js
    assert "const attemptCount = Number(record.attempt_count || 0);" in review_js
    # The words "Attempt N" became an effort icon + the count: it reads at a
    # glance in a dense table. Drawn inline because the page CSP blocks
    # external images and an inline path carries no licensing question.
    assert 'class="review-attempt-badge"' in review_js
    assert "<svg viewBox=\"0 0 24 24\"" in review_js
    assert "</svg>${attemptCount}</span>" in review_js


def test_hierarchy_conflict_picker_offers_both_readings_without_auto_applying():
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "function renderHierarchyConflictPicker(conflict)" in review_js
    picker_fn = review_js.split("function renderHierarchyConflictPicker(conflict)", 1)[1].split("\nasync function openEditRecordModal", 1)[0]
    assert 'data-hierarchy-option="zip_based"' in picker_fn or "renderOption(\"zip_based\"" in picker_fn
    assert "renderOption(\"coordinate_based\"" in picker_fn
    assert "suggestionAdopted = true;" in picker_fn
    assert "if (result.hierarchy_conflict) renderHierarchyConflictPicker(result.hierarchy_conflict);" in review_js


def test_non_us_suggestion_box_offers_explicit_save_action_without_auto_applying():
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "function renderNonUsSuggestion(suggestion)" in review_js
    suggestion_fn = review_js.split("function renderNonUsSuggestion(suggestion)", 1)[1].split("\n    }\n", 1)[0]
    assert 'id="saveAsNonUsBtn"' in suggestion_fn
    assert "Save as Non-US Data" in suggestion_fn
    assert "suggestionAdopted = true;" in suggestion_fn
    assert 'setField("country", suggestion.country);' in suggestion_fn
    assert "if (result.non_us_suggestion) renderNonUsSuggestion(result.non_us_suggestion);" in review_js


def test_review_toolbar_declares_a_column_for_every_control_so_buttons_do_not_wrap():
    html = (ROOT / "ui" / "integrations.html").read_text()
    toolbar_markup = html.split('<div class="review-toolbar">', 1)[1].split("</div>", 1)[0]
    control_count = toolbar_markup.count("<input") + toolbar_markup.count("<select") + toolbar_markup.count("<button")
    toolbar_css = html.split(".review-toolbar { display: grid; grid-template-columns:", 1)[1].split(";", 1)[0]
    # One grid column per control, and the search input is capped rather than
    # taking 1fr, so "Try Auto-Fixing with AI" stays on the same line.
    assert control_count == 5
    assert toolbar_css.count("minmax(") + toolbar_css.count("auto") == 5
    assert "1fr)" not in toolbar_css


def test_reporting_sidebar_filters_share_one_label_and_control_style():
    html = (ROOT / "ui" / "integrations.html").read_text()
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert ".report-filter-label {" in html
    assert ".report-filter-control {" in html
    # <aside class="reporting-sidebar-pane"> is gone: BOTH reporting tabs now
    # open the same <aside class="report-filter-rail">, so the same structural
    # assertion runs against each of them.
    assert "reporting-sidebar-pane" not in html, "the pre-unification rail is back"
    for source, tab in ((html, "Location Intelligence"), (tabs_js, "Data Quality")):
        rail = source.split('<aside class="report-filter-rail">', 1)[1].split("</aside>", 1)[0]
        # Every filter label/control must use the shared classes - inline
        # font-size/font-weight is what let the groups drift out of sync.
        assert 'class="report-filter-label"' in rail, tab
        assert 'class="report-filter-control"' in rail, tab
        assert 'class="report-filter-section-title"' in rail, tab
        assert 'class="report-filter-group"' in rail, tab
        assert "font-size: 11px; font-weight: 600; color: var(--ink); margin-bottom" not in rail, tab
        # Both rails end in the same actions block, in the same order:
        # auto-apply switch, then Apply, then Reset.
        actions = rail.split('class="report-filter-section report-filter-actions"', 1)[1]
        assert actions.index("AutoApplyHost") < actions.index("Apply All Filters") < actions.index("Reset All"), tab
    location_rail = html.split('<aside class="report-filter-rail">', 1)[1].split("</aside>", 1)[0]
    assert location_rail.count('class="report-filter-control"') >= 8
    # Brand / Geographic / Demographic - each a class, not a hand-copied clone.
    assert location_rail.count('class="report-filter-section-title"') == 3


def test_geo_and_competitor_filters_are_searchable():
    # Was test_geo_and_competitor_filters_search_only_after_two_characters.
    # The rail unification deleted setupGeoFilterSearch()/applyGeoOptionSearch()
    # - a local, 2-character-minimum implementation - and handed the <select>
    # filters to the SHARED component (attachSearchableSelect, common.js) at
    # minChars 1, the same setting the brand pickers use. So the two-character
    # rule now survives only where that component does not apply: the
    # competitor picker, which is a checkbox list rather than a <select>.
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    html = (ROOT / "ui" / "integrations.html").read_text()
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()

    for dead in ("setupGeoFilterSearch", "applyGeoOptionSearch"):
        assert dead not in reporting_js, f"{dead} is back - the local implementation was replaced"
        assert dead not in html, dead

    # Location Intelligence rail.
    assert "function refreshReportFilterSearch()" in reporting_js
    assert 'const REPORT_SEARCHABLE_FILTERS = ["reportMainBrandSelect", "reportStateFilter", "reportCountyFilter", "reportCityFilter"];' in reporting_js
    assert "REPORT_SEARCHABLE_FILTERS.forEach((selectId) => attachSearchableSelect(selectId, { threshold: 15, minChars: 1 }));" in reporting_js
    assert "refreshReportFilterSearch();" in html
    # Data Quality rail - the same component, not a second implementation.
    # Membership rather than a literal array: this list grows as filters are
    # added to the rail (it picked up County/City with the shared geo block),
    # and pinning its exact text makes the test fail on every addition without
    # protecting anything.
    quality_searchable = tabs_js.split("const QUALITY_SEARCHABLE_FILTERS = [", 1)[1].split("]", 1)[0]
    for select_id in ("dqBrandFilter", "dqStateFilter", "dqReasonFilter"):
        assert f"'{select_id}'" in quality_searchable, select_id
    assert "QUALITY_SEARCHABLE_FILTERS.forEach((id) => attachSearchableSelect(id, { threshold: 15, minChars: 1 }));" in tabs_js

    # The component caches the option list on attach, so EVERY rebuild of one
    # of those selects has to be followed by a re-attach, or the search keeps
    # filtering a list the control no longer holds - it would go on offering
    # the previous state's counties (BB9/BB10 staleness).
    #
    # Asserted structurally rather than by counting call sites: both rails now
    # share loadGeoOptions(), so the guarantee lives in that one loader, which
    # calls each rail's own re-attach hook after rewriting the options.
    assert "async function loadGeoOptions(rail = REPORT_GEO_RAIL)" in reporting_js
    geo_loader = reporting_js.split("async function loadGeoOptions(rail = REPORT_GEO_RAIL)", 1)[1].split("\nfunction ", 1)[0]
    assert "(rail.onOptionsRebuilt || refreshReportFilterSearch)();" in geo_loader
    # ...and each rail supplies one, pointed at its own controls.
    assert "onOptionsRebuilt: () => refreshReportFilterSearch()," in reporting_js
    assert "onOptionsRebuilt: () => refreshQualityFilterSearch()," in tabs_js
    # The brand select is rebuilt outside that loader, so it re-attaches too.
    assert "refreshReportFilterSearch();" in reporting_js
    # Reset All clears the rail's search boxes too - shared by both rails.
    assert "function clearReportFilterSearch(nodeInRail)" in reporting_js
    assert "clearReportFilterSearch(" in tabs_js

    # The active selection and the blank "All X" option always survive the
    # filter - that rule moved into the shared component with everything else.
    assert "allOptions.filter((option) => !option.value" in common_js
    assert "|| option.value === selected" in common_js

    # The competitor picker is a checkbox list, not a <select>, so it keeps
    # its own two-character rule.
    assert 'class="competitor-brand-search"' in reporting_js
    search_handler = reporting_js.split('container.querySelector(".competitor-brand-search")', 1)[1].split("\n      }", 1)[0]
    assert "query.length < 2" in search_handler
    # Hidden, not removed - a checked-but-filtered-out brand stays selected.
    assert 'row.style.display = matches ? "" : "none";' in search_handler


def test_job_history_show_more_opens_a_paginated_popup_not_inline_expansion():
    html = (ROOT / "ui" / "integrations.html").read_text()
    assert 'id="jobHistoryShowMoreBtn"' in html
    assert '<dialog id="jobHistoryDialog" class="app-help-dialog"' in html
    assert 'id="jobHistoryDialogPrevBtn"' in html
    assert 'id="jobHistoryDialogNextBtn"' in html
    assert 'el("jobHistoryShowMoreBtn")?.addEventListener("click", openJobHistoryDialog);' in html
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "function openJobHistoryDialog()" in mapper_js
    assert "function loadJobHistoryDialogPage()" in mapper_js
    assert "/api/jobs/recent?limit=${JOB_HISTORY_DIALOG_PAGE_SIZE}&offset=${offset}" in mapper_js


def test_edit_existing_brand_text_link_is_force_hidden_but_not_removed():
    # editExistingBrandLink and the CSV-preset panel's presetBrandEditBtn
    # both open the same #newBrandFields edit form (fillBrandFields()) - a
    # product decision kept the text-link one but force-hid it, rather than
    # deleting its markup/JS, so it can be restored later without rebuilding it.
    html = (ROOT / "ui" / "integrations.html").read_text()
    assert "#editExistingBrandLink { display: none !important; }" in html
    assert 'id="editExistingBrandLink"' in html
    assert 'el("editExistingBrandLink").addEventListener("click"' in html
    assert 'id="presetBrandEditBtn"' in html
    assert 'el("presetBrandEditBtn").addEventListener("click"' in html


def test_save_progress_can_be_hidden_and_continues_reporting_via_job_history():
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    html = (ROOT / "ui" / "integrations.html").read_text()

    assert 'id="loadingHideBtn"' in html
    assert "let saveProgressHiddenByUser = false;" in common_js
    # setProgress() must actually stop redrawing once dismissed, not just
    # hide the DOM once and get silently re-shown on the next tick.
    setprogress_fn = common_js.split("function setProgress(percent, message)", 1)[1].split("\nfunction hideProgress", 1)[0]
    assert "if (saveProgressHiddenByUser) return;" in setprogress_fn
    assert "showBackgroundSaveNotice" in setprogress_fn
    # hideProgress() (called on both save success and failure) must reset
    # the flag and clear the synthetic Job History row either way.
    hideprogress_fn = common_js.split("function hideProgress()", 1)[1].split("\n    }", 1)[0]
    assert "saveProgressHiddenByUser = false;" in hideprogress_fn
    assert "clearBackgroundSaveNotice" in hideprogress_fn
    assert "function showBackgroundSaveNotice()" in mapper_js
    assert "function clearBackgroundSaveNotice()" in mapper_js


def test_header_utilities_column_wraps_instead_of_overlapping_or_silently_clipping():
    # Live-reported bug (two rounds of screenshots): header-data-actions +
    # header-account-actions have a fixed ~600px minimum content width that
    # doesn't always fit above the 900px block-layout breakpoint.
    # Round 1 (overflow-x: auto + flex-wrap: nowrap) stopped the box from
    # bleeding over the top-tabs, but live-reproduced a worse regression:
    # flex-end justification scrolls an overflowing nowrap line to show its
    # END by default, so header-data-actions's own START (the Load Sample
    # Dataset button) was silently clipped with no visible scrollbar to
    # reveal it. flex-wrap: wrap is the real fix - header-account-actions
    # (the smaller group) drops to its own line, freeing header-data-actions
    # to render in full, untouched, on the first line.
    html = (ROOT / "ui" / "integrations.html").read_text()
    assert 'header .header-actions { justify-self: end; min-width: 0; max-width: 100%; overflow-x: auto; flex-wrap: wrap; justify-content: flex-end; row-gap: 8px; }' in html
    assert "flex-wrap: nowrap;" not in html.split("header .header-actions {", 1)[1].split("}", 1)[0]


def test_trends_and_top_states_live_on_tab_one():
    # Extended Coverage Metrics used to be asserted here too; it was deleted
    # for duplicating/contradicting the top row (see
    # test_extended_coverage_metrics_panel_is_gone).
    # RPT-05/06/07: all three read /api/reporting/summary and
    # /api/reporting/timeseries (not the slow quality payload), so they
    # belong with Location Intelligence. Extended Coverage Metrics sits
    # directly after the first number-card block per RPT-07.
    html = (ROOT / "ui" / "integrations.html").read_text()
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    for marker in ('id="dqTrendChart"', 'id="dqTopStatesBar"'):
        assert marker in html, f"{marker} should now live in tab 1's markup"
        assert marker not in reporting_tabs_js, f"{marker} still in the Data Quality panel"
    tab_one = html.split('<div id="reportContent" class="hidden">', 1)[1].split("<!-- Location Map Section -->", 1)[0]
    assert 'id="dqTrendChart"' in tab_one
    assert 'id="dqTopStatesBar"' in tab_one
    # Trends sits before Top States within tab 1.
    # No longer driven by the quality load path.
    quality_fn = reporting_tabs_js.split("async function loadQuality(forceRefresh = false)", 1)[1].split("\n  function ", 1)[0]
    assert "loadExtendedMetrics()" not in quality_fn


def test_d3_is_vendored_locally_and_every_chart_uses_it():
    # Explicit requirement: "no chart should be without d3.js". d3 was not
    # previously loaded anywhere in this app (only Leaflet/Monaco/Pyodide),
    # so it is vendored locally the same way leaflet/topojson are, rather
    # than pulled from a CDN at runtime.
    d3_path = ROOT / "ui" / "vendor" / "d3" / "d3.min.js"
    assert d3_path.exists(), "d3 is not vendored"
    assert d3_path.stat().st_size > 100_000, "vendored d3 looks truncated"
    assert "d3js.org" in d3_path.read_text()[:200]
    assert (ROOT / "ui" / "vendor" / "d3" / "LICENSE").exists(), "vendored d3 is missing its LICENSE"

    html = (ROOT / "ui" / "integrations.html").read_text()
    assert '<script src="vendor/d3/d3.min.js"></script>' in html
    # Must load inside the AMD-define guard, or d3's UMD build registers
    # with Monaco's AMD loader instead of defining window.d3.
    guard_block = html.split("window.define = undefined;", 1)[1].split("window.define = window.__amdDefineBackup;", 1)[0]
    assert 'vendor/d3/d3.min.js' in guard_block

    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    # Every chart renderer goes through d3 EXCEPT renderTopStatesBar, which
    # was moved to a fixed-viewBox SVG on purpose - see
    # test_top_states_bar_reads_the_real_locations_field_not_a_nonexistent_one
    # for why measuring width made it unfixable in d3.
    assert "function renderTimeSeriesChart(container, series, options = {})" in reporting_tabs_js
    assert "function chartTooltip(container)" in reporting_tabs_js
    for marker in ("d3.scaleTime()", "d3.scaleLinear()", "d3.pie()", "d3.arc()", "d3.axisBottom", "d3.axisLeft"):
        assert marker in reporting_tabs_js, marker
    # Each d3 renderer degrades honestly if the library somehow fails to
    # load. Top States no longer needs the guard - it does not use d3 at all,
    # so claiming the library failed would be a false explanation.
    assert reporting_tabs_js.count("Charting library failed to load") >= 2
    bar_fn = reporting_tabs_js.split("function renderTopStatesBar(states = [])", 1)[1].split("\n  function ", 1)[0]
    assert "Charting library failed to load" not in bar_fn


def test_fix_state_cards_show_a_dash_until_the_counts_are_really_computed():
    """Live-reported: "critical bug - no data showing on chart on left side -
    is it not mapped yet?". The five fix-state cards and "Ever invalid (all
    time)" rendered as "-" while the donut and brand table beside them showed
    real data (50 error listings across 1 brand).

    The cause was a stale per-filter cache entry pinning fix_states to
    {"computed": false} - covered by the backend half in
    unit_tests/test_reporting_cache.py
    (test_a_stale_cached_payload_cannot_pin_the_fix_state_cards_to_dashes).

    This half guards the gate itself, which is CORRECT and must stay. "Not
    computed yet" has to read as a dash and never as a fabricated 0: five
    zeros are indistinguishable from "you have no errors", which is the exact
    opposite of the truth, and that distinction is the only reason the
    computed flag exists. A future edit must not "tidy" the dash into a 0.
    """
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()

    assert "const fixStates = data.fix_states || {};" in tabs_js
    # Strict identity, deliberately: the cold "warming" payload carries no
    # fix_states at all, so a missing flag must not read as computed.
    assert "const statesComputed = fixStates.computed === true;" in tabs_js
    assert "fixStates.computed ?" not in tabs_js, "the computed gate went truthy"

    # Dash, not zero, on the shared card renderer and on the all-time total.
    assert "statesComputed ? fmt(num(fixStates[key])) : '—'" in tabs_js
    assert "metricCard(statesComputed ? fmt(totalEverInvalid) : '—', 'Ever invalid (all time)'" in tabs_js
    for fabricated in ("statesComputed ? fmt(num(fixStates[key])) : '0'",
                       "statesComputed ? fmt(num(fixStates[key])) : 0",
                       "statesComputed ? fmt(totalEverInvalid) : '0'",
                       "statesComputed ? fmt(totalEverInvalid) : 0"):
        assert fabricated not in tabs_js, f"a dash was turned into a zero: {fabricated}"

    # The share-of-total note is suppressed rather than printing a false 0%.
    assert "const sharePct = (key) => (statesComputed && totalEverInvalid)" in tabs_js

    # All five states plus the all-time total go through that one gate - a
    # card added outside it would silently reintroduce the fabricated zero.
    card_block = tabs_js.split("$('dqMetricGrid').innerHTML = [", 1)[1].split("].join('')", 1)[0]
    for key, label in (("ai_fixed", "Fixed by AI"),
                       ("ai_suggested_fixed", "Fixed from AI suggestion"),
                       ("manual_fixed", "Fixed manually"),
                       ("ai_suggested_pending", "AI suggestion awaiting review"),
                       ("manual_pending", "Awaiting manual review")):
        assert f"stateCard('{key}', '{label}'" in card_block, label
    assert "'Ever invalid (all time)'" in card_block
    # The five keys are exactly the backend's FIX_STATE_KEYS, so a rename on
    # either side cannot leave the cards reading undefined.
    import whitespace_tool.workflow_server as ws
    assert set(ws.FIX_STATE_KEYS) == {
        "ai_fixed", "ai_suggested_fixed", "manual_fixed",
        "ai_suggested_pending", "manual_pending",
    }
    for key in ws.FIX_STATE_KEYS:
        assert f"stateCard('{key}'" in card_block, key


def test_number_cards_offer_a_hover_download_of_their_data():
    # Explicit request: "for number chart also on hover there should be
    # option to download that particular data set across to fix accordingly".
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert 'class="dq-metric-download"' in reporting_tabs_js
    # Shown on hover only.
    assert ".dq-card:hover .dq-metric-download{display:inline-flex}" in reporting_tabs_js
    assert ".report-metric:hover .report-metric-download{display:inline-flex}" in reporting_tabs_js
    # Delegated listener - cards re-render on every refresh, so per-card
    # listeners would go stale. It covers BOTH tabs' cards.
    assert "event.target.closest('.dq-metric-download, .report-metric-download')" in reporting_tabs_js
    # The download must hand over the ENTITIES behind the number (listing
    # level), not a one-line restatement of the figure - the old client-side
    # toCsv/metricDatasets path exported "metric,value,filters,generated_at",
    # which is not the underlying data at all. The server owns it now.
    assert "async function downloadMetricEntities(label, filterIds, button)" in reporting_tabs_js
    assert "/api/reporting/metric-export?" in reporting_tabs_js
    # One click => exactly one request. Creating an <a> to a server URL and
    # removing it immediately made some browsers re-issue the download, so a
    # single click produced several attempts.
    assert "const metricDownloadsInFlight = new Set();" in reporting_tabs_js
    assert "if (metricDownloadsInFlight.has(slug)) return;" in reporting_tabs_js
    assert "const blob = await response.blob();" in reporting_tabs_js
    assert "const metricDatasets = new Map();" not in reporting_tabs_js
    assert "registerMetric(" not in reporting_tabs_js


def test_location_tab_number_cards_are_exportable_too():
    # Explicit report: "first tab CSV export math is missing" - the location
    # intelligence cards had no download affordance at all.
    html = (ROOT / "ui" / "integrations.html").read_text()
    for label in ("Total States", "Market ZIPs", "Active Brands", "Total Listings",
                  "Covered Markets (ZIPs)", "Covered States", "Covered Cities", "Uncovered ZIPs"):
        assert f'class="report-metric-download" data-metric-label="{label}"' in html, label
    assert "⬇ Excel</button>" in html
    assert "⬇ CSV</button>" not in html


def test_metric_export_endpoint_returns_entity_rows_with_reproducible_flags():
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.reporting_metric_export)
    # Error-population metrics export one row per error listing.
    assert "FROM `{project_id}.{dataset_id}.error_listings` e" in source
    # Fix counts must come from quality_fix_events - the same source the card
    # and the Trends chart count from. Exporting error_listings.is_ai_enriched
    # instead would hand back a different population than the card displays.
    assert "FROM `{project_id}.{dataset_id}.quality_fix_events` qf" in source
    assert "WHERE UPPER(qf.fix_type) = '{fix_type}' AND qf.processed AND qf.improved" in source
    # fix_type is stored upper-cased; 'Manual' would silently match nothing.
    assert set(ws._FIX_EVENT_METRIC_TYPES.values()) == {"AI", "MANUAL"}
    # An uncovered ZIP has no listing by definition, so market-coverage
    # metrics export at ZIP grain, not listing grain.
    assert "vw_reporting_gap_base" in source
    assert "location_count > 0 AS is_covered" in source
    # Coverage metrics export one row per listing, carrying the boolean flag
    # each rate is defined by, so the headline % is recomputable from the CSV.
    for flag in ("has_valid_zip", "has_valid_coordinates", "is_stale", "is_duplicate"):
        assert flag in source, flag
    # Same f-string brace-doubling discipline as the coverage query: a bare
    # {5} would be eaten as a format field and silently match nothing.
    assert r"r'^[0-9]{{5}}$'" in source
    # Bounded - this runs against the full warehouse on a 512MB box.
    assert "LIMIT {METRIC_EXPORT_ROW_LIMIT}" in source
    # Two sheets: the entity rows, then the metrics computed over exactly
    # those rows so the workbook proves its own headline figure.
    workbook = inspect.getsource(ws._metric_export_workbook)
    assert 'ws_data.title = "Listing Data"' in workbook
    assert 'wb.create_sheet(title="Metrics")' in workbook
    summary = inspect.getsource(ws._metric_export_summary)
    assert "Computing these from the sheet-1 rows" in summary
    assert "_METRIC_EXPORT_DEFINITIONS" in summary
    # Delivered as a ZIP bundle: the workbook plus normalized CSVs and a
    # README, so one click hands over everything needed to work with the
    # number in whatever form the consumer wants it.
    assert 'filename = f"{metric}-{stamp}.zip"' in source
    bundle = inspect.getsource(ws._metric_export_bundle)
    for member in ('f"{metric}.xlsx"', '"listings.csv"', '"metrics.csv"', '"README.txt"', '"competitors.csv"'):
        assert member in bundle, member
    # Per-brand competitor breakdown is derived from the SAME rows as sheet 1,
    # so the two can never disagree.
    competitors = inspect.getsource(ws._metric_export_competitors)
    assert '"share_pct"' in competitors
    assert "out.sort(key=lambda item: item[\"listings\"], reverse=True)" in competitors
    # An unknown metric is an error, never a fabricated/empty file.
    assert 'raise ValueError(f"unknown metric: {metric}")' in source
    # Every card label on both tabs must resolve to a known metric slug.
    known = (set(ws._ERROR_METRIC_PREDICATES) | set(ws._FIX_EVENT_METRIC_TYPES)
             | set(ws._LISTING_METRIC_SLUGS) | set(ws._LOCATION_VIEW_METRIC_SLUGS)
             | set(ws._ZIP_METRIC_SLUGS) | set(ws._BRAND_METRIC_SLUGS))
    labels = [
        "Fixed with AI", "AI review pending", "Manually fixed", "Manual review pending",
        "Invalid listings", "Needs manual review", "Unresolved rate", "ZIP completeness",
        "Coordinate completeness", "Duplicate rate", "Stale records",
        "Entity-resolution attempts", "Entity-resolution success", "Active issue types",
        "Total States", "Market ZIPs", "Active Brands", "Total Stores",
        "Covered Markets (ZIPs)", "Covered States", "Covered Cities", "Uncovered ZIPs",
    ]
    for label in labels:
        slug = re.sub(r"^-|-$", "", re.sub(r"[^a-z0-9]+", "-", label.lower()))
        assert slug in known, f"{label} -> {slug} has no export mapping"


def test_issue_type_donut_is_interactive_with_aligned_legend_columns():
    # Live-reported across rounds: too small, legend numbers not aligned,
    # then "should be interactable". Now built with d3 (pie/arc + hover
    # tooltips + slice<->legend linking) rather than a hand-rolled SVG
    # string, which could not support real interaction.
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    donut_fn = reporting_tabs_js.split("function renderReasonsDonut(containerId, buckets)", 1)[1].split("\n  function ", 1)[0]
    assert "d3.pie()" in donut_fn
    assert "d3.arc()" in donut_fn
    assert "chartTooltip(shell)" in donut_fn
    assert "grid-template-columns:14px minmax(0,1fr) auto 56px" in donut_fn
    assert "font-variant-numeric:tabular-nums" in donut_fn
    assert "const setActive = (index, on)" in donut_fn
    assert "dq-donut-legend-row" in donut_fn


def test_improvement_opportunities_is_a_single_column_list():
    # Live-reported ("should be a proper down list"): a 2-column grid left an
    # odd-numbered last card orphaned next to empty space. Given its own
    # class (not the shared .dq-improvements 2-up used by the States/Cities
    # table pair, which is a genuine even 2-up and must stay untouched).
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert ".dq-improvements-list{display:grid;grid-template-columns:1fr;gap:10px}" in reporting_tabs_js
    assert 'id="dqImprovements" class="dq-improvements-list"' in reporting_tabs_js
    assert 'id="dqGeoTables" class="dq-improvements"' in reporting_tabs_js
    assert ".dq-improvement strong{display:block;font-size:15px;" in reporting_tabs_js


def test_fix_counters_refresh_once_on_review_tab_open_not_only_during_an_active_run():
    # Root-caused live bug: #reviewAiFixedCount/#reviewManualFixedCount only
    # ever updated inside pollAutoRepairStatus(), which only runs while an
    # auto-repair job is actively in flight - so a fresh page load (or right
    # after logging back in) showed the static HTML default "0" forever,
    # looking exactly like "the counters reset on logout/login", even though
    # the real persisted count (reconciled from quality_fix_events in
    # BigQuery) was available the whole time and never actually reset.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "function renderFixCounters(state)" in review_js
    assert "async function refreshFixCountersOnce()" in review_js
    poll_fn = review_js.split("async function pollAutoRepairStatus()", 1)[1].split("\n}\n", 1)[0]
    assert "renderFixCounters(state);" in poll_fn
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    assert 'if (typeof refreshFixCountersOnce === "function") refreshFixCountersOnce();' in common_js


def test_global_hotels_preset_lat_long_are_pruned_against_the_real_csv_fields():
    # Live-verified regression (MAP-01/MAP-02): the real global-hotels demo
    # CSV (fetched live via /api/source-url + /api/preview against the
    # running server) has NO Latitude/Longitude columns at all - its real
    # header is HotelId,HotelName,Description,Category,Tags,ParkingIncluded,
    # LastRenovationDate,Rating,StreetAddress,City,StateProvince,PostalCode,
    # Country,IsDeleted. setGlobalHotelsMappings() hardcodes
    # latitude: "Latitude" / longitude: "Longitude" (neither present), so
    # pruneMappingSelectionsToParsedFields() must strip both after the
    # preset applies, or save_mapper() rejects with "unknown source fields".
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "function pruneMappingSelectionsToParsedFields()" in mapper_js
    parse_fn = mapper_js.split('if (csvFunctionMode === "pizza_hut") setPizzaHutMappings();', 1)[1].split("\n        renderMappings();", 1)[0]
    assert 'else if (csvFunctionMode === "global_hotels") setGlobalHotelsMappings();' in parse_fn
    assert "pruneMappingSelectionsToParsedFields();" in parse_fn
    # Ordering matters: pruning must run AFTER the preset overwrites
    # mappingSelections, not before.
    preset_index = parse_fn.index('setGlobalHotelsMappings();')
    prune_index = parse_fn.index("pruneMappingSelectionsToParsedFields();")
    assert preset_index < prune_index


def test_template_library_button_always_reads_review_never_load():
    # TPL-02: the action opens the template for viewing/review, so it should
    # never read "Load" - not as the initial label, and not as its busy
    # state while loadTemplateIntoEditor() runs.
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    row_fn = templates_js.split("function _templateRowHtml(template)", 1)[1].split("\n    }", 1)[0]
    assert ">Review</button>" in row_fn
    assert ">Load</button>" not in row_fn
    click_handler = templates_js.split('button.addEventListener("click", () => {', 1)[1].split("\n        });", 1)[0]
    assert 'setButtonBusy(button, "Reviewing")' in click_handler
    assert '"Loading"' not in click_handler


def test_template_review_forces_the_brand_form_closed():
    # Root-caused live bug (TPL-01): syncPreParseWorkspace() (mapper.js)
    # relocates #newBrandFields between panels when toggling pre-parse vs.
    # mapping mode, but only ever toggles the surrounding panel's hidden
    # state - if the brand-create form was left open from an earlier brand
    # edit on the same page load, it rides along still-visible and pops up
    # here even though nothing on this path asked to open it. Reviewing a
    # template never needs that form, so it must be force-closed
    # unconditionally rather than left to whatever state it was already in.
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    load_fn = templates_js.split("function loadTemplateIntoEditor(template)", 1)[1].split("\n    }\n", 1)[0]
    assert 'el("newBrandFields")?.classList.add("hidden");' in load_fn
    assert "brandEditMode = false;" in load_fn
    assert "presetCreateMode = false;" in load_fn


def test_header_account_actions_are_side_by_side_not_stacked():
    # Explicit user request, after the header wrap fix moved this group to
    # its own row: How this works + Log out side by side (How this works on
    # the left) instead of stacked top/bottom, to save vertical space.
    html = (ROOT / "ui" / "integrations.html").read_text()
    assert ".header-account-actions { display: flex; flex-direction: row;" in html
    account_actions_markup = html.split('<div class="header-account-actions">', 1)[1].split("</div>", 1)[0]
    help_index = account_actions_markup.index('id="appHelpBtn"')
    logout_index = account_actions_markup.index('id="logoutBtn"')
    assert help_index < logout_index


def test_brand_select_gets_the_shared_searchable_select_component():
    # FLT-05: "same searchable-select component as FLT-02/FLT-03, build once
    # with threshold as a prop" - attachSearchableSelect() is that shared
    # function (removes/rebuilds real <option> elements rather than hiding
    # them with CSS, since a native <select>'s open dropdown does not
    # reliably respect display:none on options cross-browser). Explicit
    # 1-character threshold for this dropdown per the user's direct ask
    # (FLT-02/FLT-03 use 2).
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    assert "function attachSearchableSelect(selectId, { threshold = 15, minChars = 2 } = {})" in common_js
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert 'attachSearchableSelect("brandSelect", { threshold: 15, minChars: 1 })' in mapper_js


def test_created_and_updated_timestamps_display_down_to_the_second():
    # Explicit user request: created_at/updated_at should read down to the
    # second (not a raw ISO string with fractional seconds, and not
    # date-only either) - shared formatTimestamp() applied everywhere a
    # stored timestamp is displayed, so it can't drift per call site.
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    assert "function formatTimestamp(value)" in common_js
    assert "pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}" in common_js
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    assert "formatTimestamp(template.created_at)" in templates_js
    assert "formatTimestamp(template.updated_at)" in templates_js
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "formatTimestamp(brand.created_at)" in mapper_js


def test_header_data_actions_reflow_when_reset_mapping_is_hidden():
    # Live-reported: Reset Fields Mapping only shows on the Mapper tab
    # (MAP-05), but display:none on it still left its named grid-template-
    # areas slot reserved, showing as an empty, "orphaned" gap on every
    # other tab. switchView() must toggle a class that drops that slot from
    # the template whenever the button itself is hidden.
    html = (ROOT / "ui" / "integrations.html").read_text()
    assert '.header-data-actions.reset-mapping-hidden { grid-template-areas: "sample restart zipstatus" "sample restart zipsync"; }' in html


def test_header_navigation_is_larger_than_utility_buttons():
    html = (ROOT / "ui" / "integrations.html").read_text()

    assert ".top-tab {\n      background: transparent;" in html
    themed_top_tab = html.split(".top-tab {\n      background: transparent;", 1)[1].split("}", 1)[0]
    assert "min-height: 44px;" in themed_top_tab
    assert "padding: 10px 18px;" in themed_top_tab
    assert "font-size: 15px;" in themed_top_tab
    assert "font-weight: 800;" in themed_top_tab
    assert ".header-actions button { min-height: 24px; font-size: 10px; padding: 4px 7px; }" in html
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    switch_view_fn = common_js.split("function switchView(viewId, isBootRestore = false) {", 1)[1].split("\n    }\n", 1)[0]
    assert 'el("resetMappingBtn")?.classList.toggle("hidden", viewId !== "mapperView");' in switch_view_fn
    assert '.classList.toggle("reset-mapping-hidden", viewId !== "mapperView");' in switch_view_fn


def test_fix_counters_also_refresh_unconditionally_at_boot():
    # Live-reproduced (screenshots): the switchView("reviewView")-only hook
    # (test_fix_counters_refresh_once_on_review_tab_open_not_only_during_an_active_run)
    # did not fire for a real login case - the Review Queue's "Listings
    # Fixed Automatically" card stayed stuck at its static HTML "0" default
    # until the user manually clicked "Try Auto-Fixing with AI", even
    # though the real backend value was already correct and non-zero
    # (verified live via curl). Call it a second, independent time directly
    # in the boot sequence - unconditional on which tab is active - mirroring
    # the proven-working refreshReviewCount() call right next to it.
    html = (ROOT / "ui" / "integrations.html").read_text()
    boot_fn = html.split("switchView(activeTab, true);", 1)[1].split("})();", 1)[0]
    assert "refreshReviewCount();" in boot_fn
    assert 'if (typeof refreshFixCountersOnce === "function") refreshFixCountersOnce();' in boot_fn
    assert boot_fn.index("refreshReviewCount();") < boot_fn.index("refreshFixCountersOnce();")


def test_trends_over_time_legends_by_metric_not_brand_and_is_bigger():
    # RPT-05: legend is the metric dimension (Locations/Errors/AI Fixed/
    # Manual Fixed), never brands. Now drawn through the shared d3
    # renderTimeSeriesChart() helper so it and the history chart can't drift.
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert "const TREND_METRIC_COLORS = { 'Locations': '#1677ee', 'Errors': '#ef4444', 'AI Fixed': '#10b981', 'Manual Fixed': '#8b5cf6' };" in reporting_tabs_js
    trend_fn = reporting_tabs_js.split("function renderTrendChart(series = [])", 1)[1].split("\n  function ", 1)[0]
    assert "renderTimeSeriesChart(chart, withColor" in trend_fn
    assert "TREND_METRIC_COLORS[s.label]" in trend_fn
    assert "s.brand" not in trend_fn
    assert "formatBrandName(s.brand)" not in reporting_tabs_js
    assert 'id="dqTrendMetric"' not in reporting_tabs_js


def test_edit_record_form_uses_the_records_own_saved_template_mapping():
    # Live-reported bug: the edit-record form built its field list from
    # getMapper()'s live Mapper-tab UI state, not the mapping that actually
    # produced this record - easily empty/unrelated (a different brand
    # loaded, or nothing parsed this session). A flagged field like
    # "Seating Capacity" then only ever showed up (if at all) under its raw
    # source column name (e.g. "seats"), unrecognizable against the error
    # text naming the target field - "I could not see such fields loaded".
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    modal_fn = review_js.split("async function openEditRecordModal(record)", 1)[1]
    # Looked up by business_id, not template_id - live-verified against a
    # real rejected record that template_id is frequently null (only set
    # when a save explicitly created/updated a template), so gating the
    # whole lookup on it skipped the fetch entirely for the common case.
    # The lookup and the template-picking both moved into shared helpers
    # (reviewTemplatesFor / reviewMapperFieldsFor, also used by the row
    # prefetcher), so the dialog asserts the wiring rather than an inline fetch.
    assert "if (record.business_id) {" in modal_fn
    assert "const templates = await reviewTemplatesFor(record.business_id, record.template_id);" in modal_fn
    assert "mapperFields = reviewMapperFieldsFor(record, templates);" in modal_fn
    # template_id only picks the exact match out of several candidates.
    assert "const matched = (record.template_id && list.find((template) => template.workflow_template_id === record.template_id)) || list[0];" in review_js
    assert "const sourceKeyToTargetKey = {};" in modal_fn
    # The form's field list is the record's own TARGET fields - core fields
    # (what US validation needs, always offered) plus everything the template
    # maps plus everything it declares unmapped - never the raw JSON keys. That
    # is what makes a flagged field appear under the name the error text uses.
    assert 'const templateTargetKeys = Object.keys(mapperFields).filter((key) => key && typeof mapperFields[key] === "string");' in modal_fn
    assert "templateUnmappedFields = reviewUnmappedFieldsFor(record, templates);" in modal_fn
    assert "const fieldKeys = [...new Set([...CORE_FIELD_ORDER, ...templateTargetKeys, ...templateUnmappedFields])];" in modal_fn
    # Each box is labelled from the TARGET key ("Seating Capacity"), not the
    # source column ("seats")...
    assert 'const label = spec.label || (typeof formatFieldLabel === "function" ? formatFieldLabel(key) : key) || key;' in modal_fn
    # ...while the value it reads and the data-raw-key it writes back stay on
    # the SOURCE column, or /api/reprocess would re-apply the mapping over a
    # row that never received the edit.
    assert "const source = mapperFields[key];" in modal_fn
    assert "const path = source || key;" in modal_fn
    assert "const rawVal = getNestedRawValue(rawObj, path);" in modal_fn
    # The flagged field is surfaced first rather than buried in a 20-box form.
    assert "fieldKeys.sort((a, b) => (errorsByField.has(b) ? 1 : 0) - (errorsByField.has(a) ? 1 : 0));" in modal_fn
    # Falls back to the live Mapper UI state only when no saved mapping
    # was found (e.g. a legacy row with no template_id) - never silently
    # skips populating fields altogether. Resolved BEFORE that branch, not
    # const-scoped inside it: it is read again further down for the brand and
    # business_id fallbacks, and scoping it to the branch threw ReferenceError
    # on every record whose template DID supply fields.
    assert "let activeMapper = { fields: {} };" in modal_fn
    assert 'if (typeof getMapper === "function") activeMapper = getMapper() || activeMapper;' in modal_fn
    assert "if (!Object.keys(mapperFields).length) {" in modal_fn
    assert "mapperFields = activeMapper.fields || {};" in modal_fn


def test_source_parser_half_of_the_left_rail_hides_in_template_edit_mode():
    # Repeatedly-reported: reviewing a saved template still showed the whole
    # source-parser rail (format picker, demo-source radios, upload/URL,
    # record-extraction mode, Parse/Reset) even though there's no source to
    # pick or parse in that mode - only the mapping is being edited. The
    # brand section, source name, and mapping grid stay.
    html = (ROOT / "ui" / "integrations.html").read_text()
    assert "#mapperView.template-edit-mode .source-parser-only { display: none !important; }" in html
    # Every part of the parser half carries the marker class.
    for marker in [
        '<label for="sourceType" class="source-parser-only">',
        '<select id="sourceType" class="source-parser-only">',
        'class="field-group csv-function-field source-parser-only hidden"',
        'class="field-group file-field source-parser-only"',
        'class="field-group record-field source-parser-only"',
        'class="button-row source-parser-only"',
    ]:
        assert marker in html, marker
    # Brand controls must NOT be marked - they stay visible.
    brand_select_line = [line for line in html.split("\n") if 'id="brandSelect"' in line and "<select" in line][0]
    assert "source-parser-only" not in brand_select_line
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    assert 'el("mapperView")?.classList.add("template-edit-mode");' in templates_js
    # Cleared everywhere templateEditMode goes back to false.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert mapper_js.count('el("mapperView")?.classList.remove("template-edit-mode");') == 3


def test_both_reporting_tabs_place_their_intro_inside_the_main_pane():
    # The two tabs put their heading/description block in different places
    # (tab 1 inside the content pane right of the filters, tab 2 full-width
    # above everything) - make Data Quality match tab 1.
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert '<main class="dq-main"><div class="dq-intro">' in reporting_tabs_js
    # Not sitting above .dq-layout any more.
    assert '<div class="dq-intro">\n        <div><h2>Data Quality &amp; Improvements</h2>' not in reporting_tabs_js.split('<div class="dq-layout">', 1)[0]
    html = (ROOT / "ui" / "integrations.html").read_text()
    assert '<div id="reportContent" class="hidden">\n              <div class="dq-intro">' in html
    assert "Use validated location records to compare your footprint with competitors, inspect map coverage, find open ZIPs, and follow market movement over time." in html
    assert "Review rejected listings and quality mirrors to see issue patterns, fix progress, freshness risk, and where automatic or manual repair is improving the dataset." in reporting_tabs_js


def test_unmeasured_coverage_metrics_show_no_data_not_a_fabricated_zero():
    # Live-reported: ZIP/Coordinate completeness rendered "0.0% - Needs
    # attention" and Duplicate rate "0.0% - Healthy" when those are zeroed
    # *defaults* from a coverage query that returned nothing, not real
    # measurements - a verdict on unmeasured data is fabricated (INV-15).
    # Entity resolution already did this correctly ("—" / No data).
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert "const totalRecords = num(q.total_records);" in reporting_tabs_js
    assert "const coverageMeasured = num(q.total_records) > 0;" in reporting_tabs_js
    for signal in ["ZIP completeness", "Coordinate completeness", "Duplicate rate", "Stale records"]:
        row = [line for line in reporting_tabs_js.split("\n") if f"['{signal}'," in line][0]
        assert "totalRecords ?" in row, signal
        assert "!totalRecords ? 'neutral'" in row, signal
    for card in ["ZIP completeness", "Coordinate completeness", "Duplicate rate", "Stale records"]:
        card_line = [line for line in reporting_tabs_js.split("\n") if f"'{card}')" in line and "metricCard(" in line][0]
        assert "coverageMeasured ?" in card_line, card


def test_most_impacted_states_shows_full_names_not_two_letter_codes():
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert "const stateLabel = (code) =>" in reporting_tabs_js
    assert "stateCodeToName[String(code).toUpperCase()]" in reporting_tabs_js
    # The geo tables moved to the paginated renderer, which escapes in one
    # place - the label conversion still happens at the call site.
    assert "states.map((row) => [stateLabel(row.state), fmt(row.count)])" in reporting_tabs_js


def test_top_states_bar_reads_the_real_locations_field_not_a_nonexistent_one():
    # Live-verified bug: renderTopStatesBar() read row.zip_count ?? row.count,
    # but the real top_states payload uses "locations" - neither other name
    # ever existed on it, so every bar computed to 0.
    #
    # This chart is deliberately NOT d3 (unlike every other chart here). Two
    # d3 versions were broken by the same root cause: sizing from
    # container.clientWidth, which is 0 while the panel is hidden. The first
    # produced a 900px viewBox scaled into one solid block; the second needed
    # a ResizeObserver that could re-enter and stack a second chart over the
    # first (overlapping full-height rectangles, user-reported). A fixed
    # viewBox scales to any width without measuring, so neither case exists.
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    bar_fn = reporting_tabs_js.split("function renderTopStatesBar(states = [])", 1)[1].split("\n  function ", 1)[0]
    assert "num(row.locations)" in bar_fn
    assert "r.zip_count" not in bar_fn
    assert "row.zip_count" not in bar_fn
    # No width measurement and no observer means no zero-width or re-entrancy.
    assert "clientWidth" not in bar_fn
    assert "ResizeObserver" not in bar_fn
    assert "d3." not in bar_fn
    assert 'viewBox="0 0 ${TOP_STATES_VIEW_W} ${height}"' in bar_fn
    # Birdeye accent hue, labels, and hover interactivity all still required.
    assert "hsl(213, 88%" in reporting_tabs_js
    assert "chartTooltip(container)" in bar_fn
    assert "group.addEventListener('mouseenter', show);" in bar_fn


def test_mapping_confidence_snapshot_and_diff_are_wired_into_save():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "let originalAutoMapping = {};" in mapper_js
    assert "originalAutoMapping = { ...mappingSelections };" in mapper_js
    assert "function computeMappingConfidenceEvents()" in mapper_js
    assert "mapping_confidence_events: index === 0 ? computeMappingConfidenceEvents() : []" in mapper_js


def test_template_load_button_stops_being_stuck_on_loading():
    # loadTemplateIntoEditor() is synchronous, but nothing ever restored
    # this button after setButtonBusy() - it stayed reading "Reviewing"
    # (disabled) even after navigating back to Template Library later.
    # (Button now reads "Review" from the start, not "Load" - see
    # test_template_library_button_always_reads_review_never_load - so
    # restoring just re-applies the same label rather than relabeling it.)
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    load_click_fn = templates_js.split('button.addEventListener("click", () => {', 1)[1].split("});", 1)[0]
    assert "clearButtonBusy(button, previousHtml);" in load_click_fn


def test_header_account_actions_has_no_separator_border():
    # Explicit user request: remove the vertical divider between the
    # header's data-actions group (Sync US ZIPs etc.) and account-actions
    # group (Log out, How this works).
    assert "border-left: 1px solid var(--line);" not in HTML.split(".header-account-actions {", 1)[1].split("}", 1)[0]


def test_review_queue_has_ai_suggested_vs_manual_review_filter():
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert 'id="reviewFixTypeFilter"' in HTML
    assert '<option value="ai_suggested">AI Suggested Fix</option>' in HTML
    assert '<option value="manual_review">Manual Review</option>' in HTML
    assert 'el("reviewFixTypeFilter")?.addEventListener("change", loadRejectedRecords);' in HTML
    assert "function recordHasSuggestionAvailable(record)" in review_js
    assert 'const fixTypeFilter = el("reviewFixTypeFilter")?.value || "";' in review_js
    # The filter and the per-row button color must use the exact same
    # heuristic function, or "AI Suggested Fix" in the dropdown could show
    # different rows than the blue-button rows already on screen.
    assert "const hasSuggestionAvailable = recordHasSuggestionAvailable(record);" in review_js


def test_field_label_formatter_is_shared_and_used_in_review_hints():
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "function formatFieldLabel(value)" in common_js
    assert "formatFieldLabel(e.field)" in review_js


def test_reporting_heading_is_smaller_with_more_explanatory_subtitle():
    # Explicit user request: the "Reporting" page title rendered larger
    # than Template Library's equivalent heading - shrink it and move more
    # explanation into the subtitle text below instead.
    hero_h1_rule = HTML.split(".report-hero h1 {", 1)[1].split("}", 1)[0]
    assert "font-size: 20px;" in hero_h1_rule
    assert "font-size: 30px;" not in hero_h1_rule
    assert "<p>Explore the gold reporting layer: market coverage, competitor overlap, whitespace ZIPs, trend movement, and the data quality signals behind every filtered view.</p>" in HTML
    assert "Where your brand stands versus competitors" not in HTML


def test_mapping_and_template_library_have_page_intro_copy():
    mapper_intro = (
        '<h1>Mappings</h1>\n'
        '        <p>Choose the brand and source, preview incoming fields, then map that structure into the location model before saving clean rows and routing exceptions to Review.</p>'
    )
    template_intro = (
        '<h2>Template Library</h2>\n'
        '        <p>Reuse saved source mappings by brand and format, inspect stored source fields, repair assignments, and keep future loads aligned to the same template structure.</p>'
    )
    assert mapper_intro in HTML
    assert template_intro in HTML


def test_source_input_uses_radio_choices_with_url_default():
    assert '<label id="sourceInputModeLabel">Source input</label>' in HTML
    assert '<div class="source-input-options" role="radiogroup" aria-labelledby="sourceInputModeLabel">' in HTML
    assert '<label><input type="radio" name="sourceInputModeChoice" value="url" checked> Public URL</label>' in HTML
    assert '<label><input type="radio" name="sourceInputModeChoice" value="file"> Upload file</label>' in HTML
    assert '<select id="sourceInputMode" class="source-input-mode-select" aria-hidden="true" tabindex="-1">' in HTML
    assert ".source-input-mode-select {" in HTML
    assert "display: none;" in HTML.split(".source-input-mode-select {", 1)[1].split("}", 1)[0]

    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "function syncSourceInputModeRadios()" in mapper_js
    assert "radio.checked = radio.value === select.value;" in mapper_js
    assert "syncSourceInputModeRadios();" in mapper_js.split("function updateSourceVisibility()", 1)[1].split("\n}", 1)[0]

    source_input_handler = HTML.split('document.querySelectorAll("input[name=\'sourceInputModeChoice\']").forEach((input) => {', 1)[1].split("});", 1)[0]
    assert 'el("sourceInputMode").value = input.value;' in source_input_handler
    assert 'el("sourceInputMode").dispatchEvent(new Event("change", { bubbles: true }));' in source_input_handler


def test_pre_parse_brand_selectors_split_search_and_selected_brand_only_when_wide():
    css = HTML.split(".wide-brand-selector {", 1)[1].split("@media (max-width: 900px)", 1)[0]
    assert "grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);" in css
    assert '.wide-brand-selector > input[type="search"]' in HTML
    assert "grid-column: 1;" in HTML.split('.wide-brand-selector > input[type="search"]', 1)[1].split("}", 1)[0]
    assert ".wide-brand-selector > select" in HTML
    assert "grid-column: 2;" in HTML.split(".wide-brand-selector > select", 1)[1].split("}", 1)[0]

    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    sync = mapper_js.split("function syncPreParseWorkspace", 1)[1].split("\nfunction ", 1)[0]
    assert 'brandHost.classList.add("wide-brand-selector");' in sync
    assert 'parserBusinessField?.classList.add("wide-brand-selector");' in sync
    assert 'brandHost.classList.remove("wide-brand-selector");' in sync
    assert 'parserBusinessField?.classList.remove("wide-brand-selector");' in sync


def test_unsaved_parse_navigation_guard():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "let pendingUnsavedParse = false;" in mapper_js
    assert "pendingUnsavedParse = true;" in mapper_js
    assert "pendingUnsavedParse = false;" in mapper_js.split("showSaveCompletion(", 1)[1][:400]

    assert 'id="unsavedChangesDialog"' in HTML
    assert 'id="unsavedChangesSaveBtn"' in HTML
    assert 'id="unsavedChangesContinueBtn"' in HTML
    nav_click_fn = HTML.split('document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {', 1)[1].split("}));", 1)[0]
    assert "const onMapper = !el(\"mapperView\")?.classList.contains(\"hidden\");" in nav_click_fn
    assert "pendingUnsavedParse" in nav_click_fn
    assert 'el("unsavedChangesDialog")?.showModal();' in nav_click_fn


def test_hiding_save_progress_returns_the_mapper_to_the_pre_parse_layout():
    # Reported: after hiding the parser progress the post-parse mapping
    # workspace stayed on screen, so a new source could not be parsed. The
    # hide action must restore the pre-parse 40/60 workspace.
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    hide_handler = common_js.split("saveProgressHiddenByUser = true;", 1)[1].split("});", 1)[0]
    assert 'if (typeof resetMapping === "function") resetMapping();' in hide_handler
    # resetMapping() is what drops back to the pre-parse layout, via
    # renderMappings() seeing no mapping content.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    reset = mapper_js.split("function resetMapping() {", 1)[1].split("\nfunction ", 1)[0]
    for marker in ("sourceParsed = false;", "mappingWorkspaceActivated = false;", "renderMappings();"):
        assert marker in reset, marker
    # And renderMappings() is what toggles the 40/60 class pair.
    assert 'mapperMain?.classList.toggle("pre-parse-layout", !hasMappingContent);' in mapper_js
    assert 'mapperView?.classList.toggle("pre-parse-active", !hasMappingContent);' in mapper_js
    assert "grid-template-columns: minmax(320px, 40%) minmax(0, 60%);" in HTML


def test_error_listings_schema_is_ensured_before_it_is_queried():
    # Live-verified: has_ai_suggestion was added to TABLE_SCHEMAS for the
    # AI/manual review-pending split, but error_listings had no ensure-pass
    # at all (unlike listings/businesses), so the column never reached the
    # deployed table. Every query selecting it failed with "Name
    # has_ai_suggestion not found inside e", taking the whole quality tab
    # and its exports down. Same class as the coverage-query bug.
    import whitespace_tool.workflow_server as ws
    from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS

    assert "has_ai_suggestion" in {f["name"] for f in TABLE_SCHEMAS["error_listings"]}
    ensure = inspect.getsource(ws._ensure_error_listings_table)
    assert 'TABLE_SCHEMAS["error_listings"]' in ensure
    assert "client.update_table(existing, [\"schema\"])" in ensure
    # Routed through the once-per-process memo now: the ensure pass still
    # runs before the query, but a repeat save no longer pays the ~1.75s
    # BigQuery round trip for a schema that cannot have changed.
    for reader in (ws.reporting_quality_summary, ws.reporting_metric_export):
        source = inspect.getsource(reader)
        assert '_ensure_once("error_listings", _ensure_error_listings_table, client, project_id, dataset_id)' in source, reader.__name__


def test_empty_metric_export_says_whether_the_source_was_missing():
    # An empty workbook that looks identical to a genuine zero is the same
    # silent-zero trap that once made every coverage metric read 0%. A
    # missing table/view must be labelled as unavailable, not presented as
    # a measured result (INV-15).
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.reporting_metric_export)
    assert "unavailable_reason" in source
    assert "not because" in source
    summary = ws._metric_export_summary("uncovered-zips", [], "view missing")
    assert any(row["metric"] == "DATA UNAVAILABLE" for row in summary)
    # A genuine empty result must NOT claim unavailability.
    assert not any(row["metric"] == "DATA UNAVAILABLE" for row in ws._metric_export_summary("uncovered-zips", []))


def test_duplicate_brands_never_reach_the_brand_dropdown():
    # DAT-04, screenshot-confirmed: loading the same brand twice put two
    # identical "Domino's Pizza" rows in the dropdown, indistinguishable and
    # unmergeable from there. Only one survivor per similar-name group may be
    # offered; the rest surface in the left rail to be merged.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    # The render half was split out of loadBrands() so a remembered list from
    # localStorage and a fresh fetch build the dropdown through exactly one
    # code path - the de-duplication must apply to both, which is why this
    # reads renderBrandOptions and not the fetch wrapper around it.
    render = mapper_js.split("function renderBrandOptions(brands)", 1)[1].split("\nfunction ", 1)[0]

    assert "const duplicateGroups = duplicateBusinessGroups(brands);" in render
    assert "hiddenDuplicateIds" in render
    # The dropdown is built from the FILTERED list, never the raw one.
    assert "const selectableBrands = brands.filter((brand) => !hiddenDuplicateIds.has(brand.business_id));" in render
    assert "selectableBrands.map((brand) =>" in render
    # A currently-selected duplicate stays visible, or the dropdown would
    # silently blank out the user's own selection.
    assert "if (selectedBrand?.business_id) hiddenDuplicateIds.delete(selectedBrand.business_id);" in render
    # dataset.brands keeps the FULL list so the rail can still see duplicates.
    assert "el(\"brandSelect\").dataset.brands = JSON.stringify(brands);" in render
    assert "renderDuplicateBrandRail(duplicateGroups);" in render


def test_duplicate_brand_detection_runs_on_app_load():
    # "should run in backend soon as we load the /app url" - loadAppData()
    # is the /app boot path, and it already calls loadBrands(), which is now
    # what performs the detection.
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    boot = common_js.split("async function loadAppData()", 1)[1].split("\n}", 1)[0]
    assert "loadBrands()" in boot


def test_there_is_only_one_brand_merge_ui():
    # Two competing merge forms for the same problem is how this stayed
    # unresolved - the old "Similar Brands" block inside the Active Brands
    # box was removed in favour of the left rail.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "data-merge-action" not in mapper_js
    assert "mergeHtml" not in mapper_js
    # One call site (the rail) plus the function definition itself.
    # Bulk merge calls it once per group inside one loop - still a single
    # call site, not a second competing UI.
    assert mapper_js.count("await mergeDuplicateBusinesses(plan.targetId, plan.sourceIds);") == 1


def test_review_action_buttons_are_bound_once_at_load_not_per_render():
    # Two live failures here: per-button listeners died when the sortable
    # helper rebuilt the tbody, and the per-render container listener was
    # skipped entirely whenever anything threw between drawing the table and
    # reaching the bind line - leaving visible buttons that did nothing. A
    # handler installed once at load cannot be skipped.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "const reviewRecordsByKey = new Map();" in review_js
    assert 'document.addEventListener("click", (event) => {' in review_js
    assert 'const button = event.target?.closest?.("button[data-open-edit]");' in review_js
    # Capture phase, so a stray stopPropagation upstream cannot swallow it.
    assert "}, true);" in review_js
    # Record lookup is by the same key the button carries.
    assert 'reviewRecordsByKey.get(`${button.dataset.event}::${button.dataset.openEdit}`)' in review_js
    assert 'reviewRecordsByKey.set(`${record.event_id}::${record.row_number}`, record)' in review_js
    # The fragile per-render binding must not come back.
    assert "reviewActionHandler" not in review_js
    assert 'target.querySelectorAll("button[data-open-edit]").forEach(' not in review_js


def test_empty_review_queue_clears_the_record_store():
    # A stale record must not stay openable from a previous page of results.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    empty_branch = review_js.split("if (!result.records.length) {", 1)[1].split("return;", 1)[0]
    assert "reviewRecordsByKey.clear();" in empty_branch


def test_the_ai_action_carries_an_ai_icon_and_manual_keeps_its_own():
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "\U0001F916 AI Suggested Fix" in review_js       # robot = AI
    assert "\U0001F6E0️ Manual Review" in review_js     # tools = manual
    assert "\U0001F4A1 AI Suggested Fix" not in review_js    # old lightbulb


def test_fix_counters_ignore_a_payload_with_no_auto_repair_block():
    # `state.auto_repair?.fixed || 0` made ANY response without auto_repair
    # render all four counters as 0, wiping correct durable numbers off the
    # screen and looking like the fixes had been lost.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    body = review_js.split("function renderFixCounters(state) {", 1)[1].split("\nfunction ", 1)[0]
    assert 'const stats = state && typeof state.auto_repair === "object" && state.auto_repair ? state.auto_repair : null;' in body
    assert "if (!stats) return;" in body
    assert "state.auto_repair?.fixed || 0" not in body


def test_stale_quality_cache_is_refetched_instead_of_sitting_outdated():
    # A warm-but-stale cache was served while a background thread recomputed,
    # and nothing ever asked for the result - so the donut and counters stayed
    # on cached numbers indefinitely.
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert "let qualityStaleRefetches = 0;" in tabs_js
    assert "const QUALITY_STALE_REFETCH_LIMIT = 3;" in tabs_js
    assert "if (data.refreshing && qualityStaleRefetches < QUALITY_STALE_REFETCH_LIMIT) {" in tabs_js
    assert "window.setTimeout(() => loadQuality(false), QUALITY_STALE_REFETCH_DELAY_MS);" in tabs_js

    import inspect
    import whitespace_tool.workflow_server as ws
    source = inspect.getsource(ws.reporting_quality_summary)
    assert 'cached_quality["refreshing"] = bool(should_refresh or quality_cache_key in _QUALITY_REFRESH_KEYS)' in source


def test_data_controls_keep_their_warning_sign():
    # The amber .data-danger-panel styling was never removed - only the
    # warning sign had been dropped from the headings.
    assert "&#9888;&#65039; Data Controls" in HTML
    assert "&#9888;&#65039; Confirm Clear" in HTML
    assert ".data-danger-panel {" in HTML
    assert "background: #fff8e6;" in HTML


def test_brand_similarity_uses_a_seventy_five_percent_threshold():
    # Exact-key matching only caught byte-identical normalized names, so
    # "Dominos Pizza" vs "Domino's Pizza Inc" scored nothing and stayed
    # unmerged - which is why duplicates survived in the dropdown.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "const BRAND_SIMILARITY_THRESHOLD = 0.75;" in mapper_js
    assert "function brandNameSimilarity(a = \"\", b = \"\")" in mapper_js
    assert "return (2 * shared) / (first.size + second.size);" in mapper_js
    assert "function duplicateBusinessGroups(brands = [], threshold = BRAND_SIMILARITY_THRESHOLD)" in mapper_js
    # business_id was REMOVED from CONTENT_HASH_FIELDS (user decision), so the
    # hash now answers "is this the same physical place?" independently of
    # which brand filed it - which is what makes a cross-brand duplicate
    # detectable at all. The old client-side helper stays deleted: the signal
    # belongs warehouse-side, where the whole table can be grouped.
    assert "function duplicateContentHashGroups" not in mapper_js

    from whitespace_tool.warehouse_bigquery import (
        CONTENT_HASH_FIELDS, LEGACY_CONTENT_HASH_FIELDS, content_hash, legacy_content_hash)
    assert "business_id" not in CONTENT_HASH_FIELDS
    listing = {"name": "Store 1", "address": "1 Main St", "zip_code": "78701"}
    assert content_hash({**listing, "business_id": "brand-A"}) == content_hash({**listing, "business_id": "brand-B"})
    # The legacy definition is kept verbatim so already-stored rows stay
    # recognisable during the transition - it must still separate brands.
    assert LEGACY_CONTENT_HASH_FIELDS == ("business_id",) + CONTENT_HASH_FIELDS
    assert legacy_content_hash({**listing, "business_id": "brand-A"}) != legacy_content_hash({**listing, "business_id": "brand-B"})


def test_data_model_gets_search_and_scrolling_only_when_the_field_list_is_long():
    # A 71-column source already filled the panel; OSM-style sources run past
    # 100 and made it an unscrollable wall with no way to find a field.
    # Below the threshold a plain list is easier to scan than one wrapped in
    # search chrome, so the affordances are conditional.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "const DATA_MODEL_SEARCH_THRESHOLD = 100;" in mapper_js
    assert "const needsFieldSearch = sourceFields.length >= DATA_MODEL_SEARCH_THRESHOLD;" in mapper_js
    assert 'id="dataModelFieldSearch"' in mapper_js
    assert '${needsFieldSearch ? " entity-map-scrollable" : ""}' in mapper_js

    # Independent vertical scrolling for each side.
    assert ".entity-map-scrollable .entity-fields," in HTML
    assert ".entity-map-scrollable .entity-column {" in HTML
    assert "max-height: 60vh;" in HTML
    assert "overflow-y: auto;" in HTML
    assert ".entity-field-search {" in HTML


def test_data_model_search_matches_source_name_and_mapped_label_on_both_sides():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    # Searchable on the raw column AND its mapped target label, so "zip"
    # finds address.postcode via its "ZIP Code" mapping.
    assert 'const searchKey = `${field} ${targetDefinition?.label || ""}`.toLowerCase();' in mapper_js
    assert 'data-field-search="${escapeHtml(searchKey)}"' in mapper_js
    # Filtering only one column would break the visual pairing.
    assert 'data-entity-search="${escapeHtml(`${item.label} ${source}`.toLowerCase())}"' in mapper_js
    assert '#dataModelSourceFields [data-field-search]' in mapper_js
    assert '#dataModelEntityColumn [data-entity-search]' in mapper_js
    # An empty result must say so rather than looking like an empty panel.
    assert 'id="dataModelNoMatches"' in mapper_js


def test_template_review_locks_the_business_and_keeps_the_template_library_tab():
    # A saved template cannot exist without a business_id, so the brand is a
    # fact of the template, not a choice - changing it here would silently
    # re-point the template at a different business. And the work is still
    # Template Library work, so the top nav must not jump to Mapping.
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    assert 'function setTemplateEditBrandLock(locked, businessId = "", brandLabel = "")' in templates_js
    assert '["brandSelect", "parserBusinessSelect", "preParseBrandSelect"].forEach' in templates_js
    assert "setTemplateEditBrandLock(true, template.business_id," in templates_js
    # A locked picker must SHOW the brand, not the placeholder. The option can
    # be genuinely absent - this select hides duplicate brands and the
    # template may point at a hidden copy - so it is added when missing.
    assert "if (locked && businessId) {" in templates_js
    assert "node.appendChild(option);" in templates_js
    assert "node.value = businessId;" in templates_js

    # Top nav highlight stays on Template Library while in template-edit mode.
    assert 'const highlightViewId = (viewId === "mapperView" && el("mapperView")?.classList.contains("template-edit-mode"))' in common_js
    assert '? "templateLibraryView"' in common_js
    assert 'button.classList.toggle("active", button.dataset.view === highlightViewId)' in common_js

    # The lock is released everywhere template-edit-mode ends, or the mapper
    # stays stuck with an un-selectable brand.
    assert mapper_js.count('setTemplateEditBrandLock(false)') == mapper_js.count('classList.remove("template-edit-mode")')


def test_sample_load_shows_no_progress_readout_at_all():
    # First the percentage was a fabrication (elapsed/estimate capped at 94,
    # so a slow load parked there); then the honest elapsed-time replacement
    # was still a running commentary occupying a whole band. Neither earns
    # the space: the button's busy state says it is working and the
    # completion dialog says what happened.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    code_only = "\n".join(
        line for line in mapper_js.split("\n") if not line.strip().startswith("//"))
    assert "Math.min(94" not in code_only, "the 94% cap must not come back"
    assert "progressLabel" not in code_only, "no running progress label"
    assert "s elapsed - larger batches take longer" not in code_only
    # The status band is emptied and hidden rather than carrying commentary.
    assert 'status.className = "report-status hidden";' in mapper_js


def test_sample_loader_skips_a_failing_brand_instead_of_aborting_the_batch():
    # "whatever is blocking the more data to insert, ignore those rows".
    # Per-brand: the loop continues. Per-row: save_mapper() routes a malformed
    # row to error_listings rather than rejecting the whole submission.
    import inspect
    import whitespace_tool.workflow_server as ws

    loader = inspect.getsource(ws._load_sample_dataset_impl)
    brand_loop = loader.split("for brand in brands_to_load:", 1)[1]
    assert "except Exception as exc:" in brand_loop
    assert "continue" in brand_loop

    save = inspect.getsource(ws.save_mapper)
    assert "if rows and all(not isinstance(row, dict) for row in rows):" in save
    assert 'raise ValueError("Row must be an object with named fields")' in save


def test_extended_coverage_metrics_panel_is_gone():
    # Removed after comparing it to the top row BY VALUE, not by label:
    #   Active Market Locations 33 == Covered Markets 33      (duplicate)
    #   Brands Tracked 11        == Active Brands 11          (duplicate)
    #   Total Stores 10,130      == Total Stores 10,130       (duplicate)
    #   ZIP Codes Covered 41,618 == Market ZIPs 41,618        (mislabelled)
    #   States Covered 57        vs Covered States 11         (universe, wrong)
    #   Cities Covered 21,788    vs Covered Cities 28         (universe, wrong)
    #   Whitespace ZIPs 100      vs Uncovered ZIPs 41,585     (page size!)
    # Only one value was unique and three actively contradicted the correct
    # figures, so the panel was net-negative.
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert "renderExtraMetrics" not in tabs_js
    assert "dqExtraGrid" not in tabs_js
    assert "dqExtraGrid" not in HTML
    assert "Extended Coverage Metrics" not in HTML
    # The Top States chart shared that loader and must survive.
    assert "dqTopStatesBar" in tabs_js
    assert "async function loadExtendedMetrics()" in tabs_js
    assert "renderTopStatesBar(" in tabs_js


def _css_outside_media(css: str) -> str:
    """Strip every @media block (braces matched) so a responsive override is
    not miscounted as a second base declaration of the same selector."""
    out = []
    i = 0
    while True:
        at = css.find("@media", i)
        if at < 0:
            out.append(css[i:])
            return "".join(out)
        out.append(css[i:at])
        open_brace = css.index("{", at)
        depth = 0
        j = open_brace
        while j < len(css):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1


def test_quality_sidebar_matches_tab_one_filter_styling():
    # Reported: the Data Quality sidebar had extra spacing/framing tab 1 does
    # not. Every earlier fix kept a PARALLEL set of .dq-filters/.dq-filter-field
    # rules hand-copied to "match" tab 1's, and the two drifted apart again
    # each time. They are now one component: the rail's CSS is declared once,
    # in integrations.html, and reporting-tabs.js declares none of its own.
    # So this no longer compares two stylesheets - it asserts there is only one.
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()

    # The parallel vocabulary is gone as CSS (the surviving mentions in
    # reporting-tabs.js are the comment explaining why it must stay gone).
    for dead in (".dq-filters{", ".dq-filter-field{", ".dq-sidebar ", ".dq-sidebar{"):
        assert dead not in tabs_js, f"parallel rail CSS is back: {dead}"

    # One BASE definition each, in integrations.html, and no clone in the
    # panel. Anchored to the start of a line so a legitimate compound selector
    # (.report-filter-group > input[type="search"].report-filter-control) is
    # not miscounted as a second base rule. Responsive overrides inside
    # @media blocks are not parallel definitions - the rail unpins itself on
    # narrow screens - so those blocks are cut out before counting, and only
    # top-level declarations are what must be unique.
    html_base = _css_outside_media(HTML)
    for rule in (".report-filter-rail {", ".report-filter-rail-head {",
                 ".report-filter-section {", ".report-filter-section-title {",
                 ".report-filter-group {", ".report-filter-label {",
                 ".report-filter-control {"):
        found = re.findall(r"^\s*" + re.escape(rule), html_base, re.M)
        assert len(found) == 1, f"{rule} declared {len(found)} times outside @media"
        assert rule.replace(" {", "{") not in tabs_js, rule

    # The rail is pinned again, and offset by the REAL header height that
    # common.js publishes (a hardcoded top drifted whenever the header wrapped).
    rail_base = html_base.split(".report-filter-rail {", 1)[1].split("}", 1)[0]
    assert "position: sticky;" in rail_base
    assert "top: calc(var(--app-header-h, 71px) + 12px);" in rail_base
    assert "--app-header-h" in (ROOT / "ui" / "js" / "common.js").read_text()
    assert "function syncAppHeaderOffset()" in (ROOT / "ui" / "js" / "common.js").read_text()

    # ...and the Data Quality markup consumes that one definition.
    assert '<aside class="report-filter-rail">' in tabs_js
    assert '<div class="report-filter-rail-head">' in HTML

    # The framing the report was about: a single padded container whose inner
    # field boxes are 8px, not 12px inside an already-padded card.
    rail_rule = HTML.split(".report-filter-rail {", 1)[1].split("}", 1)[0]
    assert "padding: 16px;" in rail_rule
    group_rule = HTML.split(".report-filter-group {", 1)[1].split("}", 1)[0]
    assert "padding: 8px;" in group_rule
    assert "padding: 12px;" not in group_rule


def test_template_editor_shows_real_saved_records_not_only_column_names():
    # Asked repeatedly: the template editor showed only stored COLUMN NAMES
    # ("no live data rows"), which is not enough to judge a mapping. The rows
    # this template produced live in `listings` keyed by template_id.
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.template_sample_records)
    assert "l.template_id = @template_id" in source
    assert "(@business_id = '' OR l.business_id = @business_id)" in source
    assert "l.is_deleted IS NOT TRUE" in source
    assert 'raise ValueError("template_id is required")' in source

    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    assert "async function loadTemplateSampleRecords()" in templates_js
    assert "/api/templates/sample-records?" in templates_js
    assert 'id="templateSampleRecords"' in templates_js
    # Only columns carrying a value are rendered - a table of empty columns
    # is worse than a narrower honest one.
    assert 'records.some((row) => row[key] !== null && row[key] !== undefined && row[key] !== "")' in templates_js
    # Honest empty state rather than a blank panel.
    assert "No records saved under this template yet." in templates_js


def test_template_sample_route_is_matched_before_the_templates_prefix():
    # /api/templates is a startswith() match, so it swallowed
    # /api/templates/sample-records and returned the template LIST instead.
    import inspect
    import whitespace_tool.workflow_server as ws

    handler = inspect.getsource(ws.make_handler)
    specific = handler.index('startswith("/api/templates/sample-records")')
    general = handler.index('startswith("/api/templates")')
    assert specific < general, "the specific route must be tested first"


def test_duplicate_brands_merge_in_bulk_with_one_radio_per_candidate():
    # Asked for explicitly: "10 brands will have 10 rows, each one having a
    # radio choice, name can be shown once, count, created biz id near the
    # radio". Handling one group at a time cost one round trip per group.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    rail = mapper_js.split("function renderDuplicateBrandRail(", 1)[1].split("\nasync function ", 1)[0]

    # A row per candidate, radio-selected, grouped by name.
    assert 'type="radio" name="dupKeep${groupIndex}"' in rail
    assert 'class="dup-brand-row"' in rail
    # Name once per group, not repeated per row.
    assert 'class="dup-brand-name"' in rail
    # Business id always shows; count and date only when they actually tell
    # the copies apart. Two copies loaded in one batch share a timestamp to
    # the second and often both have 0 listings - printing identical strings
    # on both rows makes the user compare them for nothing.
    assert "dup-brand-id" in rail
    # All four facts always show, so the choice can be made from the row.
    assert "listings &middot; <strong>${age}</strong> &middot;" in rail
    assert '"Newest"' in rail and '"Oldest"' in rail and '"Same age"' in rail
    assert "formatTimestamp(brand.created_at)" in rail
    # Recommendation rule stated and marked: most listings, older on a tie.
    assert 'dup-brand-pick">recommended' in rail
    assert "most listings, or the older record when counts match" in rail
    # ONE submit covering every group.
    assert 'id="duplicateBrandMergeBtn"' in rail
    assert "const plans = groups.map((group, groupIndex)" in rail
    assert "for (const plan of plans) {" in rail
    # A failing group must not discard the ones that succeeded.
    assert "failures.push(" in rail
    # Sensible default: most listings, then oldest.
    assert "Number(b.listing_count || 0) - Number(a.listing_count || 0)" in rail

    assert ".dup-brand-row {" in HTML
    assert ".dup-brand-group {" in HTML


def test_duplicate_brand_panel_still_lives_in_the_forty_percent_rail():
    assert 'class="panel left-rail-persistent hidden" id="duplicateBrandPanel"' in HTML
    assert 'id="duplicateBrandList"' in HTML
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    rail = mapper_js.split("function renderDuplicateBrandRail(", 1)[1].split("\nasync function ", 1)[0]
    # Hidden entirely when there is nothing to merge.
    assert 'panel.classList.add("hidden");' in rail
    # Merging reloads so merged-away ids leave every picker.
    assert "await loadBrands();" in rail


def test_brand_dropdown_keeps_detail_on_hover_only():
    # The hover-only rule applies to the brand DROPDOWN, where inline detail
    # was clutter. The merge picker is a decision and shows it inline.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    # Option markup moved out of loadBrands() into renderBrandOptions() when
    # the fetch and the remembered-list paint were unified onto one path.
    render = mapper_js.split("function renderBrandOptions(brands)", 1)[1].split("\nfunction ", 1)[0]
    assert 'title="${escapeHtml(businessOptionLabel(brand))}"' in render
    assert "${escapeHtml(formatBrandName(brand.name))}</option>" in render


def _all_ui_js():
    parts = [(ROOT / "ui" / "js" / name).read_text()
             for name in ("mapper.js", "review.js", "templates.js", "common.js", "reporting.js", "login.js")]
    parts.append((ROOT / "ui" / "reporting-tabs.js").read_text())
    return "\n".join(parts)


def test_every_button_with_an_id_has_a_handler_somewhere():
    # Blanket guard: a button that renders but does nothing on click is the
    # failure mode that hit "Manual Review" / "AI Suggested Fix" twice. Any
    # new button whose id is never referenced from JS (and carries no inline
    # handler) fails here rather than silently shipping dead.
    import re

    js = _all_ui_js()
    # Only the CONTENTS of <script> blocks. Splitting on the first "<script"
    # and taking the tail swept in the rest of the markup, so a dead button
    # matched its own id attribute and the guard passed - verified by
    # injecting a handler-less button, which this version catches.
    inline_scripts = "\n".join(
        re.findall(r"<script\b[^>]*>(.*?)</script>", HTML, re.S))
    dead = []
    for button_id in sorted(set(re.findall(r'<button[^>]*\bid="([A-Za-z0-9_]+)"', HTML))):
        has_inline = re.search(r'<button[^>]*id="%s"[^>]*onclick=' % re.escape(button_id), HTML)
        referenced = (re.search(r"\b%s\b" % re.escape(button_id), js)
                      or re.search(r"\b%s\b" % re.escape(button_id), inline_scripts))
        if not (has_inline or referenced):
            dead.append(button_id)
    assert dead == [], f"buttons with no handler: {dead}"


def test_delegated_buttons_are_reachable_by_their_selector():
    # Buttons created at render time carry no id, so the id sweep above
    # cannot see them. Each is driven by a delegated listener; assert the
    # selector the listener matches is the one the markup actually emits.
    js = _all_ui_js()
    for markup_class, selector in [
        ("review-fix-suggested", 'button[data-open-edit]'),
        ("review-fix-manual", 'button[data-open-edit]'),
        ("dq-metric-download", ".dq-metric-download, .report-metric-download"),
        ("report-metric-download", ".dq-metric-download, .report-metric-download"),
    ]:
        assert markup_class in js, f"{markup_class} markup missing"
        assert selector in js, f"no delegated listener matching {selector}"
    # Both review action buttons carry the attribute their listener selects on.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    for cls in ("review-fix-suggested", "review-fix-manual"):
        button = review_js.split(f'class="{cls}"', 1)[1][:160]
        assert "data-open-edit=" in button, f"{cls} is not selectable by the delegated listener"


def test_review_action_buttons_open_the_editor_for_the_clicked_record():
    # The behaviour, not just the wiring: the clicked button's identity must
    # resolve to the record the modal opens.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    handler = review_js.split('document.addEventListener("click", (event) => {', 1)[1].split("}, true);", 1)[0]
    assert 'closest?.("button[data-open-edit]")' in handler
    assert "reviewRecordsByKey.get(" in handler
    assert "openEditRecordModal(record)" in handler
    # A click that resolves to no record must say so rather than dying quietly.
    assert "console.warn" in handler
    # The store is keyed by exactly what the button carries.
    assert 'data-open-edit="${escapeHtml(record.row_number)}" data-event="${escapeHtml(record.event_id)}"' in review_js
    assert 'reviewRecordsByKey.set(`${record.event_id}::${record.row_number}`, record)' in review_js


def test_reporting_tables_use_two_row_alternating_bands():
    # Asked for: "any tabular section of reporting should follow 2 row color
    # policy like gradient to better visibility". Banded in PAIRS rather than
    # single-row zebra so the grouping survives rows that wrap to two lines.
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    for css in (HTML, tabs_js):
        assert "nth-child(4n+1)" in css
        assert "nth-child(4n+2)" in css
        assert "nth-child(4n+3)" in css
        assert "nth-child(4n+4)" in css
        assert "linear-gradient(180deg" in css
    # Scoped to reporting so data-entry tables elsewhere keep their plain look.
    assert "#reportingView table tbody tr:nth-child(4n+1)," in HTML
    assert ".dq-table tbody tr:nth-child(4n+1)" in tabs_js
    # Hover stays distinct from both bands.
    assert "#reportingView table tbody tr:hover { background: #e8f1fd; }" in HTML
    assert ".dq-table tbody tr:hover{background:#e8f1fd}" in tabs_js


def test_quality_filters_auto_apply_through_the_shared_toggle():
    # Asked for: "filters should be auto applied, with a choice to stop auto
    # apply button which change from stop to restart auto apply".
    #
    # The behaviour is unchanged; its implementation moved. #autoApplyFiltersBtn
    # was a Data-Quality-only button whose label named what a CLICK would do
    # ("Stop auto apply"), i.e. the opposite of the current state - so reading
    # it told you nothing at a glance. It is now a SWITCH, mounted from the
    # shared attachAutoApplyToggle() in js/reporting.js, at #dqAutoApplyHost on
    # this rail and #reportAutoApplyHost on the Location Intelligence one, so
    # the two tabs cannot end up behaving differently.
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()

    # The per-tab button is gone, not renamed.
    assert 'id="autoApplyFiltersBtn"' not in tabs_js
    assert "let autoApplyFilters = true;" not in tabs_js
    assert "Restart auto apply" not in tabs_js

    # Mounted in both rails, in the actions block.
    assert '<div id="dqAutoApplyHost"></div>' in tabs_js
    assert '<div id="reportAutoApplyHost"></div>' in HTML
    assert "attachAutoApplyToggle('dqAutoApplyHost', {" in tabs_js
    assert 'attachAutoApplyToggle("reportAutoApplyHost", {' in reporting_js

    # Every filter control triggers it, not just one. Membership rather than
    # a literal array - the rail gained cascading County/City/ZIP controls,
    # and pinning the exact text fails on every addition without protecting
    # anything.
    quality_ids = tabs_js.split("const QUALITY_FILTER_IDS = [", 1)[1].split("];", 1)[0]
    for filter_id in ("dqBrandFilter", "dqReasonFilter", "dqStatusFilter", "dqStartDate", "dqEndDate"):
        assert f"'{filter_id}'" in quality_ids, filter_id
    # The geographic ones are in the set but deliberately NOT watched here:
    # changing a state also has to repopulate county/city/ZIP, which must
    # happen whether auto-apply is on or off, so those handlers wire
    # themselves and hand only the reload back via schedule(). Same split the
    # Location rail makes between integrations.html and setupReportAutoApply().
    assert "...QUALITY_GEO_FILTER_IDS" in quality_ids
    assert "watchIds: QUALITY_FILTER_IDS.filter((id) => !QUALITY_GEO_FILTER_IDS.includes(id))," in tabs_js
    assert "watchIds:" in reporting_js.split('attachAutoApplyToggle("reportAutoApplyHost", {', 1)[1].split("});", 1)[0]
    assert "onApply: () => loadQuality()" in tabs_js
    assert "watchIds.forEach((watchId) => el(watchId)?.addEventListener(\"change\", schedule));" in reporting_js

    # A real switch, not a button that renames itself: it keeps keyboard
    # focus, Space to flip, and an announced state.
    assert '<input type="checkbox" role="switch" class="auto-apply-toggle-input" id="${inputId}" checked>' in reporting_js
    assert 'stateText.textContent = input.checked ? "On" : "Off";' in reporting_js

    # Debounced: three quick changes are one query, not three.
    assert "delayMs = 400" in reporting_js
    debounce = reporting_js.split("const schedule = () => {", 1)[1].split("\n  };", 1)[0]
    assert "window.clearTimeout(timer);" in debounce
    assert "}, delayMs);" in debounce

    # Restarting applies whatever changed while it was off, so the view can
    # never sit out of step with the controls.
    restart = reporting_js.split("if (input.checked) {", 1)[1].split("} else {", 1)[0]
    assert "schedule();" in restart

    # Off state is visually distinct - the amber card kept from the button
    # this replaced, so "filters are not applying" stays visible.
    assert ".auto-apply-toggle[data-auto='off'] .auto-apply-toggle-label{" in reporting_js

    # The explicit Apply button survives for a manual re-run, and subsumes a
    # debounce still counting down rather than letting it re-fire after.
    assert "$('applyQualityFiltersBtn')?.addEventListener('click', () => {" in tabs_js
    assert "qualityAutoApply?.cancel();" in tabs_js


def test_reporting_tables_export_their_own_shape_as_a_zip():
    # Asked for: "make each table of reporting downloadable ... with table
    # level relevancy and data, not all tables needed pure listing data like
    # market gap, brand comparison".
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.reporting_table_export)
    # Served from the SAME payload the screen renders, so a downloaded table
    # cannot disagree with what the user is looking at.
    assert "summary = reporting_summary(" in source
    assert 'rows = summary.get(spec["key"]) or []' in source
    # An unknown table is an error, never an empty file passed off as data.
    assert 'raise ValueError(f"unknown table: {table or \'(missing)\'}")' in source
    # Reuses the metric ZIP bundle (workbook + normalized CSVs + README).
    assert "_metric_export_bundle(table, rows" in source
    assert 'f"{table}-{stamp}.zip"' in source

    # Each table maps to its own payload slice, not to listings.
    assert ws.REPORTING_TABLE_EXPORTS["market-gaps"]["key"] == "gaps"
    assert ws.REPORTING_TABLE_EXPORTS["brand-comparison"]["key"] == "brands"
    assert ws.REPORTING_TABLE_EXPORTS["top-states"]["key"] == "top_states"
    assert ws.REPORTING_TABLE_EXPORTS["top-cities"]["key"] == "top_cities"


def test_each_reporting_table_has_a_download_button_wired_to_its_own_slice():
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    for table in ("market-gaps", "brand-comparison", "top-states", "top-cities"):
        assert f'data-table-export="{table}"' in HTML, table
    assert "event.target.closest('[data-table-export]')" in tabs_js
    assert "/api/reporting/table-export?" in tabs_js
    # Same one-request-per-click guard as the metric cards.
    assert "const tableDownloadsInFlight = new Set();" in tabs_js
    assert "if (!table || tableDownloadsInFlight.has(table)) return;" in tabs_js
    # Downloads carry the filters currently on screen.
    assert "window.reportingQueryString()" in tabs_js
    assert ".table-export-btn {" in HTML


def test_no_spinner_message_carries_a_trailing_ellipsis():
    # Standing rule: verb-ing spinner text, no "...". The spinner already
    # communicates that work is in progress; the ellipsis is noise and was
    # inconsistent across the app.
    import re

    offenders = []
    for name in ("reporting.js", "mapper.js", "review.js", "templates.js", "common.js", "login.js"):
        js = (ROOT / "ui" / "js" / name).read_text()
        offenders += [(name, m) for m in re.findall(r'<span class="spinner"></span>[^\'"`]*?\.\.\.', js)]
    tabs = (ROOT / "ui" / "reporting-tabs.js").read_text()
    offenders += [("reporting-tabs.js", m) for m in re.findall(r'<span class="spinner"></span>[^\'"`]*?\.\.\.', tabs)]
    assert offenders == [], f"spinner text with trailing ellipsis: {offenders}"


def test_reporting_skeleton_stays_hidden_until_there_is_data():
    # Reported: a screen of blank space under "Preparing reporting data".
    # #reportContent was revealed BEFORE checking whether any data existed,
    # so every empty section reserved its full height behind the status line.
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    assert "const preparing = Boolean(result.refreshing) && !hasBusinessData;" in reporting_js
    assert 'el("reportContent").classList.toggle("hidden", preparing);' in reporting_js
    # The unconditional reveal must not come back.
    assert 'el("reportContent").classList.remove("hidden");\n        const totals' not in reporting_js
    assert "'<span class=\"spinner\"></span> Preparing reporting data'" in reporting_js


def test_auto_refresh_does_not_blank_the_report_before_fetching():
    # Reported: "how come auto refresh removed all data which was good ...
    # it even made 50 states as 0". renderEmptyReportingStructure() ran
    # unconditionally BEFORE the fetch on every loadReporting(), including
    # the 5-minute auto-refresh, so every count dropped to 0 until the
    # response landed. 50 states is a global constant and can never be 0.
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    # Keyed off a flag that is set ONCE and never reset. reportLoaded is reset
    # on purpose to force a re-fetch (auto-refresh, manual refresh, filter
    # change), so keying the blank off it wiped the numbers on every refresh -
    # which is exactly the bug, just via a different path.
    assert "let reportHasRenderedOnce = false;" in reporting_js
    assert "if (!reportHasRenderedOnce) renderEmptyReportingStructure();" in reporting_js
    assert "if (!reportLoaded) renderEmptyReportingStructure();" not in reporting_js
    # The unconditional call must not come back either.
    assert "\n      renderEmptyReportingStructure();\n      try {" not in reporting_js


def test_review_queue_interleaves_ai_suggested_and_manual_rows():
    # The server orders by event_id/row_number, which clusters a brand's
    # suggested rows together - so a page could be entirely one kind and the
    # other never got looked at.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "const suggested = result.records.filter(recordHasSuggestionAvailable);" in review_js
    assert "const manual = result.records.filter((record) => !recordHasSuggestionAvailable(record));" in review_js
    assert "if (i < suggested.length) interleaved.push(suggested[i]);" in review_js
    assert "if (i < manual.length) interleaved.push(manual[i]);" in review_js
    # Interleaving only when there is no explicit filter, and only when both
    # kinds are present - otherwise it would reorder for no reason.
    assert "if (suggested.length && manual.length) {" in review_js


def test_adopting_an_ai_suggestion_counts_as_an_ai_fix():
    # Reported: "Suggested ZIP + coordinates: this enrichment didn't increase
    # the number for Listings Fixed Automatically". The branch handled only
    # the manual case, so an adopted suggestion skipped the manual increment
    # (correct) but never wrote an AI fix event either - counting toward
    # NEITHER metric.
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.reprocess_rejected)
    assert 'adopted_ai_suggestion = bool(data.get("is_ai_enriched", False))' in source
    assert 'fix_type = "AI" if adopted_ai_suggestion else "MANUAL"' in source
    assert "if not adopted_ai_suggestion:\n                increment_manual_fixed_count(rows_updated)" in source
    # The old manual-only guard must not come back.
    assert "if manual_repair and result[" not in source


def test_fix_state_pivot_can_report_fixed_states_not_just_pending():
    # The pivot chose only between the two PENDING keys, so its ai_fixed and
    # manual_fixed columns were structurally always 0.
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.reporting_quality_summary)
    assert 'state_key = "ai_fixed"' in source
    assert 'state_key = "manual_fixed"' in source
    assert 'state_key = "ai_review_pending"' in source
    assert 'state_key = "manual_review_pending"' in source
    assert 'state_key = "ai_review_pending" if row.get("has_ai_suggestion") else "manual_review_pending"' not in source


def test_quality_tables_scroll_instead_of_overflowing_their_panel():
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert ".dq-section > div:has(> table),.dq-main div:has(> .dq-table){overflow-x:auto" in tabs_js


def test_five_state_fix_counts_are_cumulative_and_mutually_exclusive():
    # A fixed record is soft-deleted, which removed it from every count - so
    # totals reset instead of accumulating. was_ever_invalid/resolution_status
    # make the population cumulative.
    import inspect
    import whitespace_tool.workflow_server as ws
    from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS

    columns = {f["name"] for f in TABLE_SCHEMAS["error_listings"]}
    assert {"was_ever_invalid", "resolution_status"} <= columns

    source = inspect.getsource(ws.fix_state_counts)
    # Exactly the user's truth table.
    assert "COUNTIF(state = 'fixed' AND ai_fixed) AS ai_fixed" in source
    assert "COUNTIF(state = 'fixed' AND NOT ai_fixed AND ai_suggested) AS ai_suggested_fixed" in source
    assert "COUNTIF(state = 'fixed' AND NOT ai_fixed AND NOT ai_suggested) AS manual_fixed" in source
    assert "COUNTIF(state != 'fixed' AND ai_suggested) AS ai_suggested_pending" in source
    assert "COUNTIF(state != 'fixed' AND NOT ai_suggested) AS manual_pending" in source
    # Counted over soft-deleted rows too, or fixed records vanish again.
    assert "is_deleted IS TRUE, 'fixed', 'pending'" in source
    # Historical rows predate the columns and must stay countable.
    assert "COALESCE(was_ever_invalid, TRUE)" in source
    # The five states must sum to the total, or the model has drifted.
    assert 'counts["states_reconcile"]' in source
    # Mirror-backed for instant paint; "not computed" is not "zero".
    assert "set_fix_state_counts(counts)" in source
    assert '{"computed": False, "refreshing": True}' in inspect.getsource(ws._cumulative_fix_states)


def test_error_row_is_marked_invalid_at_write_and_resolved_at_fix():
    import inspect
    import whitespace_tool.workflow_server as ws

    builder = inspect.getsource(ws._row_error_listing)
    assert '"was_ever_invalid": True,' in builder
    assert '"resolution_status": "pending",' in builder
    reprocess = inspect.getsource(ws.reprocess_rejected)
    assert "resolution_status = 'fixed'" in reprocess


def test_listings_is_the_canonical_term_in_the_ui():
    # Decision: "Listings" everywhere - it matches the DB table and every
    # medallion layer. "Stores" and "listings" were previously mixed inside
    # the same tables ("Competitor Stores" beside "Population Per Listing").
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    assert "Total Listings</span>" in HTML
    assert 'data-metric-label="Total Listings"' in HTML
    assert 'label: "Competitor Listings"' in reporting_js
    assert 'label: "Competitor Stores"' not in reporting_js
    assert "Total Stores</span>" not in HTML


def test_total_listings_is_emitted_with_a_backwards_compatible_alias():
    # Renaming an API field outright would break any client still reading the
    # old one mid-deploy, so both are emitted and readers prefer the new name.
    import inspect
    import whitespace_tool.workflow_server as ws

    # Emitted by _mirror_totals(), which builds the totals payload.
    source = inspect.getsource(ws._mirror_totals)
    assert '"total_listings": int(total_stores),' in source
    assert '"total_stores": int(total_stores)' in source
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    assert "(totals.total_listings ?? totals.total_stores)" in reporting_js
    # The renamed card must still resolve to a known export slug.
    assert "total-listings" in ws._LOCATION_VIEW_METRIC_SLUGS
    assert "total-listings" in ws._METRIC_EXPORT_DEFINITIONS


def test_every_reporting_table_paginates():
    # Only market-gaps had a pager; everything else rendered all rows, or a
    # silent .slice(0, 10) that hid the rest with no way to reach them.
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()

    assert "const SIMPLE_TABLE_PAGE_SIZE = 10;" in common_js
    assert 'button[data-simple-page]' in common_js
    # Page state is per target so two tables cannot fight over one counter.
    assert "simpleTablePages.set(targetId, safePage);" in common_js
    # Clamped, so a shrinking dataset cannot strand the user on an empty page.
    assert "const safePage = Math.min(Math.max(page, 0), Math.max(pageCount - 1, 0));" in common_js

    assert "function renderPagedDqTable(targetId, headers, rows, emptyMessage)" in tabs_js
    assert "button[data-dq-page]" in tabs_js
    # The hard truncation must not come back.
    assert "states.slice(0, 10)" not in tabs_js
    assert "cities.slice(0, 10)" not in tabs_js


def test_native_alert_and_confirm_are_replaced_by_themed_dialogs():
    # window.alert/confirm ignore the app theme entirely and cannot be styled.
    # Remaining uses must be fallbacks only (dialog missing / no showModal).
    import re

    for name in ("review.js", "reporting.js"):
        js = (ROOT / "ui" / "js" / name).read_text()
        bare = [m for m in re.findall(r"^\s*(?:window\.)?(?:alert|confirm)\(", js, re.M)]
        assert bare == [], f"{name} still calls a native dialog unconditionally"

    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    assert 'function showAppNotice(message, title = "Done", tone = "ok")' in common_js
    assert 'function showAppConfirm(message, title = "Please confirm")' in common_js
    assert 'id="appNoticeDialog"' in HTML and 'id="appConfirmDialog"' in HTML

    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    # The mapping-move prompt and the reset acknowledgement both went themed.
    assert "const move = await showAppConfirm(" in mapper_js
    assert 'showAppNotice("Workspace reset complete.' in mapper_js
    # Brand save/update now acknowledge in-theme, not just an inline banner.
    # The create path reports one of TWO outcomes since create_brand can hand
    # back an existing brand instead of making a duplicate (BB11), so this
    # pins the themed call and the brand name it carries, not one sentence.
    creator = mapper_js.split("async function createNewBrand(", 1)[1].split("\nfunction ", 1)[0]
    assert "showAppNotice(" in creator, "brand create no longer acknowledges in-theme"
    assert "formatBrandName(selectedBrand.name)" in creator
    assert not re.search(r"^\s*(?:window\.)?(?:alert|confirm)\(", creator, re.M)
    assert 'showAppNotice(`${formatBrandName(selectedBrand.name)} was updated.`' in mapper_js


def test_zip_suggestions_are_deduped_per_zip():
    # The reference union can carry a ZIP more than once, so a single ZIP
    # appeared several times and typing a city returned every duplicate.
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.search_zips)
    assert "GROUP BY zip_code" in source
    assert "ANY_VALUE(city_name) AS city_name" in source


def test_brand_identity_enrichment_is_keyless_and_never_invents_values():
    import inspect
    from whitespace_tool import brand_enrichment

    source = inspect.getsource(brand_enrichment)
    # Keyless sources only - nothing here may require credentials.
    assert "overpass-api.de" in source
    assert "api.duckduckgo.com" in source
    assert "api_key" not in source.lower() and "apikey" not in source.lower()

    # Aggregator hosts are not a brand's own site.
    assert brand_enrichment._clean_website("en.wikipedia.org/wiki/X") == ""
    assert brand_enrichment._clean_website("facebook.com/x") == ""
    assert brand_enrichment._clean_website("dominos.com") == "https://dominos.com"
    # Validation, not acceptance.
    assert brand_enrichment._clean_phone("12") == ""
    assert brand_enrichment._clean_phone("(512) 555-1234") == "5125551234"
    assert brand_enrichment._clean_email("nope") == ""

    # Owner-entered values are never overwritten.
    assert brand_enrichment.enrich_brand_identity("X", existing={
        "website_url": "https://a.com", "phone_number": "5125551234", "email": "a@b.com"}) == {}
    # Every resolved field records its source, and unresolved stays visible.
    assert '"unresolved_fields"' in source or "unresolved_fields" in source
    assert '_source"] = "openstreetmap"' in source


def test_brand_enrichment_endpoint_requires_a_name():
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.brand_identity_enrichment)
    assert 'raise ValueError("name is required")' in source
    handler = inspect.getsource(ws.make_handler)
    assert 'startswith("/api/brands/enrich")' in handler


def test_specific_api_routes_are_matched_before_their_prefix():
    # startswith() routing means a broad prefix swallows a longer sibling.
    # This bit twice: /api/templates ate /api/templates/sample-records, and
    # /api/brands ate /api/brands/enrich (returning the brand LIST instead).
    import inspect
    import whitespace_tool.workflow_server as ws

    handler = inspect.getsource(ws.make_handler)
    for specific, general in (
        ('startswith("/api/templates/sample-records")', 'startswith("/api/templates")'),
        ('startswith("/api/brands/enrich")', 'startswith("/api/brands")'),
        ('startswith("/api/reporting/table-export")', 'startswith("/api/reporting")'),
        ('startswith("/api/reporting/metric-export")', 'startswith("/api/reporting")'),
    ):
        assert handler.index(specific) < handler.index(general), f"{specific} must precede {general}"


def test_historical_quality_lives_on_tab_one_with_a_period_control():
    # Was on tab 2, plotted a single "invalid records" series from the quality
    # snapshot, and had no period control or competitor comparison.
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()

    # Markup now lives in tab 1 after the map and coverage sections: KPI
    # cards first, Location Map, Top States by Coverage, then line charts.
    tab_one = HTML.split('<div id="reportContent" class="hidden">', 1)[1].split("<!-- Top States Section", 1)[0]
    assert tab_one.index('class="report-grid"') < tab_one.index("<!-- Location Map Section -->")
    assert tab_one.index("<!-- Location Map Section -->") < tab_one.index("Top States by Coverage")
    assert tab_one.index("Top States by Coverage") < tab_one.index("Trends Over Time")
    assert tab_one.index("Trends Over Time") < tab_one.index("Historical Quality &amp; Change Tracking")
    assert 'id="dqHistoryChart"' in tab_one
    assert 'data-history-period="1W"' in tab_one
    assert 'data-history-period="1Y"' in tab_one
    # Same toggle markup as Trends, so both controls look identical.
    assert 'class="dq-period-toggle" role="group" aria-label="History period"' in tab_one
    assert '<button type="button" data-period="1H" class="active">1H</button>' in tab_one
    assert '<button type="button" data-history-period="1H" class="active">1H</button>' in tab_one
    assert 'data-period="1M" class="active"' not in tab_one
    assert 'data-history-period="1D" class="active"' not in tab_one
    assert '<div class="dq-trend-head">\n                  <h3>Historical Quality &amp; Change Tracking</h3>' in tab_one
    # Removed from the quality panel.
    assert 'id="dqHistoryChart"' not in tabs_js.split("function buildQualityPanel", 1)[1].split("return panel", 1)[0]

    # Plots LISTINGS over time from the timeseries endpoint, not a single
    # invalid-records series from the quality snapshot.
    assert "async function loadQualityHistory()" in tabs_js
    assert "/api/reporting/timeseries?" in tabs_js
    assert "pick('Locations')" in tabs_js
    assert "let historyPeriod = '1H';" in tabs_js
    assert "let trendState = { period: '1H' };" in tabs_js
    assert ".dq-history-chart{min-height:360px" in tabs_js
    assert ".dq-history-chart svg{width:100%;height:340px" in tabs_js
    assert "height: 340,\n        ariaLabel: 'Listings and errors over time'" in tabs_js
    assert "renderQualityHistory" not in tabs_js
    # Competitor overlay, combined into one line rather than one per brand.
    assert "`Competitors (${competitors.length})`" in tabs_js
    # Loads with tab 1.
    assert "loadQualityHistory();" in tabs_js.split("if (name === 'location') {", 1)[1][:400]


def test_no_sliding_progress_bar_under_status_messages():
    # A second, competing indicator next to the spinner: a long bar whose
    # text "kept going and coming". The verb-ing label plus spinner is the
    # standard; the bar communicated nothing extra.
    assert ".report-status.loading::after" not in HTML
    assert "@keyframes reportProgress" not in HTML
    assert "animation: reportProgress" not in HTML


def test_data_controls_panel_actually_renders_warm():
    # .panel is declared later at the same specificity, so its
    # `background: var(--panel)` was winning and this rendered plain white -
    # losing the warning treatment entirely.
    assert ".panel.data-danger-panel," in HTML
    danger = HTML.split(".panel.data-danger-panel,", 1)[1].split("}", 1)[0]
    assert "linear-gradient(180deg, #fff4d6 0%, #ffe9bf 100%)" in danger
    assert "box-shadow: inset 3px 0 0 #d97706;" in danger


def test_review_edit_dialog_never_shows_object_object_as_a_brand():
    # Reported: the brand field displayed "Object Object" where the real brand
    # was "Casa Verde". String() on an object yields "[object Object]", which
    # formatBrandName then title-cased. The raw record's brand can legitimately
    # be a nested object, so it is unwrapped before stringifying.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "const unwrapBrand = (value) =>" in review_js
    assert 'const nested = value.name ?? value.value ?? value.brand ?? value.label;' in review_js
    # The bare String(...) that produced the placeholder must not come back.
    assert 'String(getNestedRawValue(rawObj, mapperFields.brand || "brand")' not in review_js


def test_opening_a_review_record_does_not_refetch_templates_every_click():
    # Two sequential network round trips ran before the dialog painted, which
    # is the delay felt on "Manual Review" / "AI Suggested Fix".
    # The cache moved out of openEditRecordModal() into the shared
    # reviewTemplatesFor() helper (the row prefetcher uses it too), so this
    # asserts the helper rather than the call site.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "const reviewTemplateCache = new Map();" in review_js
    assert 'async function reviewTemplatesFor(businessId, requiredTemplateId = "")' in review_js
    cache_fn = review_js.split('async function reviewTemplatesFor(businessId, requiredTemplateId = "")', 1)[1].split("\n// ", 1)[0]
    assert "const entry = reviewTemplateCache.get(businessId);" in cache_fn
    assert "reviewTemplateCache.set(businessId, { templates, fetchedAt: Date.now(), checked });" in cache_fn
    # A second click while the first fetch is still in flight joins it rather
    # than starting another - two dialogs opened back to back otherwise paid
    # the round trip twice.
    assert "const inflight = reviewTemplateInflight.get(businessId);" in cache_fn
    assert "if (inflight) return inflight;" in cache_fn
    assert "reviewTemplateInflight.set(businessId, request);" in cache_fn
    assert "reviewTemplateInflight.delete(businessId);" in cache_fn
    # Entries expire, so a template created elsewhere is eventually picked up.
    assert "REVIEW_TEMPLATE_TTL_MS" in cache_fn
    # A record naming a template the cached list does not contain is treated
    # as a stale entry and refetched - ONCE per id, so a genuinely deleted
    # template does not re-pay the fetch on every click. Without this the
    # lookup fell through to templates[0], i.e. a DIFFERENT template's field
    # mapping: wrong labels on the wrong boxes.
    assert "const unknownTemplate = Boolean(requiredTemplateId)" in cache_fn
    assert "!entry.checked.has(requiredTemplateId)" in cache_fn
    # A failed fetch must not poison the cache.
    assert "return entry ? entry.templates : [];" in cache_fn


def test_review_tab_shows_the_same_five_states_as_reporting():
    # The five-state cards went to the reporting tab only; the review queue is
    # where the work actually happens, so it needs them too - and from the
    # same source, or the two tabs would disagree.
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    for element_id in ("reviewStateAiFixed", "reviewStateAiSuggestedFixed", "reviewStateManualFixed",
                       "reviewStateAiPending", "reviewStateManualPending", "reviewStateTotal"):
        assert f'id="{element_id}"' in HTML, element_id
        assert element_id in review_js, element_id
    assert "async function refreshReviewFixStates()" in review_js
    assert '"/api/review/fix-states"' in review_js
    # "Not computed yet" is a dash, never a zero - zero would be a claim that
    # nothing has ever been invalid.
    assert 'node.textContent = computed ? Number(states[key] || 0).toLocaleString() : "-";' in review_js
    # Colour carries meaning on these cards too.
    assert ".review-state-card.state-ai-fixed" in HTML
    assert ".review-state-card.state-manual-pending" in HTML


def test_merging_brands_reports_what_it_actually_moved():
    # "Merged 2 brands" says nothing about impact. Counting the rows moved
    # per table distinguishes a merge that consolidated a real footprint from
    # one that combined two already-empty duplicates.
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.merge_brands)
    # Row counts now come from the shared run_sql_dml() helper, which is the
    # single place SQL leaves this process.
    assert 'moved[table_name] = run_sql_dml(client, f"""' in source
    assert 'label=f"merge_brands:{table_name}"' in source
    for key in ('"listings_moved"', '"templates_moved"', '"review_rows_moved"', '"moved_total"'):
        assert key in source, key
    assert "brands_merged target=%s sources=%d listings=%d templates=%d review_rows=%d" in source

    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "listingsMoved += Number(outcome?.listings_moved || 0);" in mapper_js
    assert "reviewMoved += Number(outcome?.review_rows_moved || 0);" in mapper_js
    # A merge that moved nothing says so, rather than implying it did work.
    assert "The copies held no records, so nothing needed moving." in mapper_js


def test_readme_does_not_advertise_shipped_work_as_a_gap():
    # The audit found it still listed the job-history panel and duplicate
    # messaging as "scoped but not yet built" long after both shipped - a
    # presentation built from it would have been wrong.
    readme = (ROOT / "README.md").read_text()
    assert "a save-job history panel" not in readme
    assert "duplicate-detection messaging on save are scoped but not yet built" not in readme
    # And it now documents the rules that actually govern the data.
    assert "was_ever_invalid" in readme
    assert "custom_fields" in readme
    assert "100km" in readme and "50km" in readme


def test_the_sample_dataset_loads_in_one_statement_not_two_halves():
    """The NTILE(2) split was removed. Measured: a single INSERT over the whole
    22,500-row source runs in ~3s across 17MB, so the split bought nothing -
    while costing a background thread that re-entered load_sample_dataset()
    itself. That re-entrancy is what let the second half's reset soft-delete
    the 11,250 rows and every business the first half had just written."""
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws._load_sample_dataset_impl)
    wrapper = inspect.getsource(ws.load_sample_dataset)
    assert "def load_sample_dataset(reset: bool = False)" in wrapper
    # Assert against the CODE, not the prose - the docstring and comments
    # legitimately name the design they replaced.
    body = re.sub(r'"""(?:.|\n)*?"""', "", source, count=1)
    body = re.sub(r"(#|--)[^\n]*", "", body)
    # No halves anywhere: no parameter, no NTILE, no self-scheduling thread.
    assert "load_half" not in body and "load_half" not in wrapper
    assert "NTILE" not in body
    assert "sample-second-half" not in body
    assert "load_second_half" not in body
    # Still idempotent, so an interrupted load tops up rather than duplicates.
    assert "WHERE NOT EXISTS (" in body
    assert "existing.listing_id = s.listing_id" in body
    # The wrapper still guarantees the in-flight flag is released.
    assert "_SAMPLE_LOAD_RUNNING.clear()" in wrapper


def test_brand_search_is_plain_and_client_side():
    # It filters the select's own options in memory - it never queries the
    # server - so explaining a minimum character count was noise.
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    assert 'search.placeholder = (selectId === "brandSelect" || selectId === "parserBusinessSelect")' in common_js
    assert "Type ${minChars}+ character" not in common_js
    # Still filtering the in-memory list, not fetching.
    assert "const liveOptions = Array.from(select.options)" in common_js


def test_draft_restored_message_is_one_sentence():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert 'setStatus("Draft restored.", "ok");' in mapper_js
    assert "re-parse before saving if you need the full dataset in memory" not in mapper_js


def test_template_loaded_message_omits_the_internal_slug():
    # "Loaded spice_route_csv_csv_sample." exposed an internal identifier that
    # means nothing to the reader; the mapping it refers to is on screen.
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    assert 'setStatus("Edit the field mapping, then click Save Template to update.", "ok");' in templates_js
    assert "Loaded ${template.name}" not in templates_js


def test_clicking_mappings_leaves_template_edit_mode():
    # Template edit reuses the mapper view, and the nav highlight is pinned to
    # Template Library while it is active. Clicking Mappings is a NEW mapping
    # workflow, so it must exit that mode - otherwise the highlight stays on
    # Template Library and the Mappings tab looks disabled.
    nav = HTML.split('document.querySelectorAll("[data-view]").forEach', 1)[1].split("}));", 1)[0]
    assert 'targetView === "mapperView" && el("mapperView")?.classList.contains("template-edit-mode")' in nav
    assert 'if (typeof resetMapping === "function") resetMapping();' in nav
    # resetMapping() is what clears the mode and restores the 40/60 layout.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    reset = mapper_js.split("function resetMapping() {", 1)[1].split("\nfunction ", 1)[0]
    assert 'classList.remove("template-edit-mode")' in reset
    assert "renderMappings();" in reset


def test_every_dialog_uses_the_one_birdeye_shell():
    """Five dialogs used to carry bespoke frames (`connector-editor-dialog`,
    `danger-dialog`) that ignored the app theme. There is exactly one dialog
    shell now - `<dialog class="app-help-dialog"> > .app-help-content >
    .app-help-header > h2` - varied only by size/tone modifier classes."""
    html = (ROOT / "ui" / "integrations.html").read_text()

    # The retired bespoke frames must not come back anywhere, markup or CSS.
    assert "connector-editor-dialog" not in html
    assert "danger-dialog" not in html

    # Anchored to the start of a line so real markup is matched and prose is
    # not - a CSS comment now explains why the modals are native <dialog>s in
    # the top layer, and that sentence is not a dialog off the shell.
    dialogs = re.findall(r"^\s*<dialog\b[^>]*>", html, re.M)
    assert len(dialogs) >= 12, f"expected the full dialog set, found {len(dialogs)}"
    for tag in dialogs:
        assert 'class="app-help-dialog' in tag, f"dialog off the shell: {tag}"
        assert "aria-labelledby=" in tag, f"dialog with no labelled title: {tag}"

    # Each dialog body carries the shell's content wrapper and a titled h2.
    # The notice dialog uses .app-notice-body instead of .app-help-header - an
    # outcome message is an icon and a sentence, not a form header with a rule
    # across an empty box - but it is the same shell and the same <h2 id>.
    for body in re.findall(r"^\s*<dialog\b[^>]*>(.*?)</dialog>", html, re.S | re.M):
        assert '<div class="app-help-content">' in body
        assert ('<div class="app-help-header">' in body
                or '<div class="app-notice-body">' in body), body[:200]
        assert re.search(r'<h2 id="[^"]+"', body), body[:200]

    # Destructive dialogs stay visibly destructive while on the shell.
    for dialog_id in ("dangerDialog", "masterDeleteCredentialsDialog", "masterDeleteConfirmDialog"):
        tag = next(t for t in dialogs if f'id="{dialog_id}"' in t)
        assert "app-help-dialog--danger" in tag, tag
    assert ".app-help-dialog--danger .app-help-header h2 { color: var(--error); }" in html


def test_a_failed_save_is_recorded_and_announced_like_a_successful_one():
    """O1: hiding the progress panel sends the save to the background. The
    success path pops a dialog and refreshes Job History; the failure path
    used to write only to an inline status line the user is no longer looking
    at - and recorded no job at all, so the attempt left no trace anywhere."""
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.save_mapper)
    # The push is what can fail after the job genuinely started; an
    # argument-validation raise above it never became a job.
    push, _, after = source.partition("push_to_bigquery(project_id, dataset_id, rows_by_table")
    assert "try:" in push.rsplit("\n", 3)[-3:][0] or "try:" in push[-200:]
    assert "record_save_event(" in after.split("_maybe_refresh_after_save", 1)[0]
    # mapped_rows=0 with rows present is what record_save_event derives
    # FAILED from - no new status vocabulary.
    assert "mapped_rows=0, error_listings=0, duplicate_listings_skipped=0," in after
    assert "raise" in after.split("_maybe_refresh_after_save", 1)[0]

    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    save_catch = mapper_js.split('const wasBackgrounded', 1)[1].split("\n        }", 1)[0]
    assert "showAppNotice(" in save_catch
    assert "loadJobHistory();" in save_catch
    # hideProgress() resets saveProgressHiddenByUser, so the flag has to be
    # captured before it is called - reading it afterwards is always false.
    assert save_catch.index("hideProgress();") < save_catch.index("showAppNotice(")
    assert save_catch.lstrip().startswith("= typeof saveProgressHiddenByUser")


def test_the_merge_confirmation_states_the_decision_not_the_statistics():
    """User: "stats on merge etc not need to be shown in confirmation dialog
    box". The counts were accurate but they are not the decision - the user
    already picked which record to keep. They also forced the box wider than
    the text needed. They still appear in the result message after the merge
    actually runs."""
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    summary = mapper_js.split("function describeMergeImpact(plans)", 1)[1].split("\n    }", 1)[0]
    for stat in ("listings_moved", "templates_moved", "review_rows_moved", "preview: true"):
        assert stat not in summary, stat
    assert "Nothing is deleted." in summary
    # No preview round trip just to render a dialog.
    assert "await describeMergeImpact" not in mapper_js
    # The post-merge message still reports what actually moved.
    assert "listingsMoved += Number(outcome?.listings_moved || 0);" in mapper_js


def test_small_dialogs_are_sized_by_their_content():
    html = (ROOT / "ui" / "integrations.html").read_text()
    rule = html.split("#appNoticeDialog, #appConfirmDialog, #saveCompletionDialog, #sampleLoadedDialog {", 1)[1].split("}", 1)[0]
    assert "width: auto;" in rule
    assert "max-width: min(460px" in rule
    # Long unbroken text must wrap rather than widen the box.
    assert "#appConfirmMessage, #appNoticeMessage { white-space: pre-line; overflow-wrap: anywhere; }" in html


def test_the_brand_form_submit_button_cannot_create_a_duplicate_while_editing():
    """User-reported: "some clicks lose create brand form, call the unexpected
    one". Three flags decide what the single #createBrandBtn means, each set by
    a different path that opens the form - and the click handler consulted only
    one of them, so the preset panel's "Edit Brand Details" left the button on
    its CREATE branch and saving filed a second copy of the brand on screen."""
    html = (ROOT / "ui" / "integrations.html").read_text()

    handler = html.split('el("createBrandBtn").addEventListener("click"', 1)[1].split("});", 1)[0]
    assert "brandEditMode || presetBrandEditMode" in handler
    # The business_id check is what stops a stale preset flag turning a
    # genuine create into an update of nothing.
    assert "Boolean(selectedBrand?.business_id)" in handler
    assert "if (editingExistingBrand) return updateExistingBrand();" in handler

    # Every path that ends an edit must clear ALL three flags, or the next
    # click inherits a mode the form is no longer in.
    select_handler = html.split('el("brandSelect").addEventListener("change"', 1)[1].split("\n    el(", 1)[0]
    create_branch, _, existing_branch = select_handler.partition('const brands = JSON.parse(')
    for branch, label in ((create_branch, "create"), (existing_branch, "existing")):
        assert "brandEditMode = false;" in branch, label
        assert "presetCreateMode = false;" in branch, label
        assert "presetBrandEditMode = false;" in branch, label

    cancel = html.split('el("cancelBrandEditBtn").addEventListener("click"', 1)[1].split("});", 1)[0]
    for flag in ("brandEditMode = false;", "presetCreateMode = false;", "presetBrandEditMode = false;"):
        assert flag in cancel, flag


def test_competitor_diffs_are_coloured_from_the_primary_brands_point_of_view():
    """User-reported: "+ count is red for business, - count is green". Every
    row of Head-to-Head is a COMPETITOR measured against the primary brand, so
    a competitor with MORE locations is bad news for the primary brand. The
    table coloured diff > 0 green, reading "+278 competitor locations" as an
    achievement."""
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    cell = reporting_js.split("const competitorDiffCell =", 1)[1].split("};", 1)[0]
    assert "const ahead = diff > 0;" in cell
    # Ahead = the competitor is ahead = bad for us.
    assert 'const color = ahead ? "var(--error)" : "var(--ok)";' in cell
    assert "is behind by" in cell and "is ahead by" in cell
    # One helper drives every column, so two columns cannot disagree again.
    assert reporting_js.count("const color = diff > 0 ? \"var(--ok)\"") == 0
    for column in ("locations", "states", "counties", "cities", "zips"):
        assert f'competitorColumn("{column}"' in reporting_js, column


def test_benchmark_brand_and_competitor_share_one_line():
    html = (ROOT / "ui" / "integrations.html").read_text()
    cell = html.split(".comp-bench-brand-cell {", 1)[1].split("}", 1)[0]
    assert "flex-direction: row;" in cell
    assert "flex-wrap: nowrap;" in cell
    # Width comes from the metric columns, which were mostly whitespace.
    assert "width: 46%;" in html.split("th.brand-col {", 1)[1].split("}", 1)[0]
    # The wrapping properties that forced the second line must be gone from
    # both name styles, replaced by truncation with a tooltip.
    for selector in (".comp-primary-name {", ".comp-link-name {"):
        rule = html.split(selector, 1)[1].split("}", 1)[0]
        assert "word-break:" not in rule, selector
        assert "white-space: nowrap;" in rule, selector
        assert "text-overflow: ellipsis;" in rule, selector


def test_review_fix_state_cards_do_not_depend_on_the_heavy_quality_endpoint():
    """The six cumulative cards rendered "-" while the correct values sat in
    the SQLite mirror, because they were read off /api/reporting/quality - a
    heavy aggregation they had to wait on, and fail with."""
    import whitespace_tool.workflow_server as ws

    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    fetcher = review_js.split("async function refreshReviewFixStates()", 1)[1].split("\nfunction ", 1)[0]
    assert '"/api/review/fix-states"' in fetcher
    assert 'fetch("/api/reporting/quality' not in fetcher
    # Not computed yet must be retried, not left as dashes for the session.
    assert "data.refreshing && reviewFixStateRetries < REVIEW_FIX_STATE_RETRY_LIMIT" in fetcher

    handler = inspect.getsource(ws.make_handler)
    assert '/api/review/fix-states' in handler
    # A cold mirror has to say a recount is running, or the page cannot know
    # to come back for it.
    assert '{"computed": False, "refreshing": True}' in inspect.getsource(ws._cumulative_fix_states)


def test_ai_fixed_share_uses_cumulative_counts_not_the_current_batch():
    """It read the live auto-repair batch (fixed / fixed+manual+remaining),
    which resets to 0 when a batch starts - so it showed "0.00%" beside cards
    reporting 110 AI fixes. Verified against the live mirror at the time:
    ai_fixed=110, total_ever_invalid=395, i.e. 27.85%, not 0.00%."""
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    share = review_js.split("function renderAiFixedShare()", 1)[1].split("\nfunction ", 1)[0]
    assert "states.total_ever_invalid" in share
    assert "states.ai_fixed" in share
    assert "stats.fixed" not in share and "stats.remaining" not in share
    # Unmeasured is a dash; "0.00%" would be a claim that AI fixed nothing.
    assert 'aiPercent.textContent = "-";' in share


def test_the_reporting_warmup_poll_has_an_attempt_budget():
    """It was the only poll in the file with none: each poll that came back
    still refreshing scheduled another, forever - so the "Preparing reporting
    data" spinner reappeared every few seconds for the rest of the session."""
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    assert "const REPORTING_WARMUP_POLL_LIMIT = 20;" in reporting_js
    scheduler = reporting_js.split("function scheduleReportingWarmupPoll(", 1)[1].split("\nfunction ", 1)[0]
    assert "if (reportingWarmupPolls >= REPORTING_WARMUP_POLL_LIMIT) return;" in scheduler
    assert "reportingWarmupPolls += 1;" in scheduler
    # Exhausted says so once instead of spinning; an explicit click resets it.
    assert "Reporting data is taking longer than usual to prepare." in reporting_js
    assert "resetReportingWarmupPolls();" in reporting_js.split("async function refreshReportingNow()", 1)[1][:600]


def test_the_error_donut_says_what_its_centre_number_counts():
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert ">total</text>" not in review_js
    assert review_js.count(">error listings</text>") == 2


def test_the_sample_ingest_only_selects_columns_the_source_actually_has():
    """The real sample dataset never loaded ONCE. The INSERT selected
    `COALESCE(s.validated, FALSE)`, but `sample_locations.listings` has no
    `validated` column, so BigQuery rejected the whole statement with
    "Name validated not found inside s" - and the except around it fell
    through to the in-memory generator and reported success. What looked like
    a half-loaded 22,500-row sample was a different 9,295-row generated set
    standing in for it, with zero listing_ids in common.
    """
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws._load_sample_dataset_impl)
    insert = source.split("INSERT INTO `{project_id}.{dataset_id}.listings`", 1)[1].split('"""', 1)[0]

    # The column that broke it must not come back. Strip SQL comments first -
    # the explanation of the bug legitimately names it.
    statement = re.sub(r"--[^\n]*", "", insert)
    assert "s.validated" not in statement
    assert "FALSE AS validated" in statement

    # Every `s.<column>` the statement selects must exist on the source
    # table's real schema, otherwise the whole INSERT fails the same way.
    referenced = set(re.findall(r"\bs\.([a-z_]+)\b", statement))
    # load_half is produced by the NTILE subquery, not the source table.
    referenced.discard("load_half")
    source_columns = {
        "listing_id", "business_id", "source_type_id", "location_key", "name", "address",
        "city_name", "town", "state_code", "province", "zip_code", "country", "latitude",
        "longitude", "template_id", "ingestion_id", "mapping_id", "validation_status",
        "franchise_name", "concept_type", "cuisine_type", "neighborhood", "district",
        "phone_number", "website_url", "google_maps_link", "social_media_handles",
        "operating_hours", "seating_capacity", "service_types", "opening_date", "status",
        "annual_revenue", "average_ticket_size", "daily_footfall", "monthly_footfall",
        "rental_cost", "lease_cost", "population_density", "average_household_income",
        "competitor_count", "foot_traffic_score", "parking_availability", "ratings",
        "content_hash", "deleted_on",
    }
    missing = referenced - source_columns
    assert not missing, f"INSERT references columns the source lacks: {sorted(missing)}"


def test_a_failed_sample_ingest_is_logged_as_an_error_not_a_warning():
    """A silent fallback that substitutes different data is indistinguishable
    from the real thing on screen - which is exactly how this went unnoticed."""
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws._load_sample_dataset_impl)
    assert 'LOGGER.error("sample_locations_ingestion_failed falling_back_to_generator error=%s", exc)' in source
    assert "sample_ingestion_error = str(exc)" in source


def test_a_load_clears_the_previous_sample_before_reingesting():
    """This used to be guarded to "half 1 only" because the second half would
    otherwise wipe the first - it did exactly that once, soft-deleting the
    11,250 rows and every business half 1 had written, leaving businesses at
    0 live. With the split gone there is no second pass, so the clean slate is
    unconditional again."""
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws._load_sample_dataset_impl)
    assert "load_half" not in source
    delete_block = source.split("One load, one clean slate", 1)[1]
    assert "DELETE FROM `{project_id}.{dataset_id}.listings` WHERE is_sample_data IS TRUE" in delete_block
    assert "DELETE FROM `{project_id}.{dataset_id}.businesses` WHERE is_sample_data IS TRUE" in delete_block


def test_chart_tooltips_anchor_to_their_own_container():
    """User-reported: hovering a point in Trends Over Time showed the tooltip
    at the TOP OF THE PAGE, over the nav. The tooltip is position:absolute, so
    its top/left resolve against the nearest POSITIONED ancestor - and these
    chart containers had none, so an offset meant for the chart was applied
    against the page. Fixed in chartTooltip() itself so a new chart cannot
    reintroduce it (the review tab's donut never had the bug because
    #reviewBrandChart already carries position: relative)."""
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    helper = tabs_js.split("function chartTooltip(container)", 1)[1].split("\n  function ", 1)[0]
    assert "window.getComputedStyle(container).position === 'static'" in helper
    assert "container.style.position = 'relative';" in helper
    # The absolute offsets it sets are only correct with that guard in place.
    assert "container.getBoundingClientRect()" in helper

    html = (ROOT / "ui" / "integrations.html").read_text()
    assert "#reviewBrandChart { min-height: 340px;" in html
    review_container = html.split("#reviewBrandChart { min-height: 340px;", 1)[1].split("}", 1)[0]
    assert "position: relative;" in review_container


def test_trend_points_are_big_enough_to_see_and_hit():
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert "const TREND_POINT_RADIUS = 7;" in tabs_js
    assert "const TREND_POINT_HOVER_RADIUS = 10;" in tabs_js
    # No stray hardcoded radius left behind to drift from the constants.
    trend = tabs_js.split("class', 'dq-chart-point'", 1)[1].split("});", 1)[0]
    assert "attr('r', TREND_POINT_RADIUS)" in trend
    assert "attr('r', 4)" not in trend and "attr('r', 6)" not in trend


def test_the_trend_chart_is_not_torn_down_on_every_load():
    """User-reported: "why is loading trend data running each time". The data
    IS cached - measured live, reporting_timeseries:v2:1M and :1Q were both
    sitting in query_cache - but loadTrendChart() blanked the panel and put
    "Loading trend data" up on EVERY call, including the ones answered from
    SQLite in milliseconds. Same rule as the location report's
    reportHasRenderedOnce: only blank when there is nothing to keep."""
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    assert "let trendHasRenderedOnce = false;" in tabs_js
    loader = tabs_js.split("async function loadTrendChart()", 1)[1].split("\n  //", 1)[0]
    assert "if (chart && !trendHasRenderedOnce) {" in loader
    assert "trendHasRenderedOnce = true;" in loader
    # A transient failure must not wipe a good chart either.
    assert loader.count("!trendHasRenderedOnce") >= 2
    # And it is set only after a successful render, never before the fetch.
    assert loader.index("renderTrendChart(") < loader.index("trendHasRenderedOnce = true;")


def test_the_sample_dataset_only_ever_loads_when_a_user_asks():
    """Explicit ask: "load once ... no rerun from anywhere unless asked,
    refresh reports doesnt have any link to reload of sample dataset"."""
    html = (ROOT / "ui" / "integrations.html").read_text()
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()

    # Exactly three entry points, every one of them a click the user made.
    triggers = re.findall(r'el\("(\w+)"\)\??\.addEventListener\("click", \(\) => loadSampleDataset\(', html)
    assert sorted(triggers) == ["loadSampleDatasetBtn", "loadSampleDatasetHeaderBtn", "reloadSampleDatasetLink"]

    # Nothing on a reporting path may reach the loader or its endpoint.
    for name, source in (("reporting.js", reporting_js), ("reporting-tabs.js", tabs_js)):
        assert "/api/sample/load" not in source, name
        assert "loadSampleDataset(" not in source, name

    # And no timer/interval anywhere schedules one.
    for name, source in (("mapper.js", mapper_js), ("integrations.html", html)):
        for scheduler in ("setInterval(loadSampleDataset", "setTimeout(loadSampleDataset"):
            assert scheduler not in source, f"{name}: {scheduler}"


def test_no_half_split_logic_survives_in_the_sample_loader():
    """The NTILE(2) split is gone; only comments explaining WHY may mention
    it. A stale comment describing it as current behaviour is its own bug -
    it is what made the split look like it was still there."""
    import whitespace_tool.workflow_server as ws

    body = re.sub(r'"""(?:.|\n)*?"""', "", inspect.getsource(ws._load_sample_dataset_impl), count=1)
    body = re.sub(r"(#|--)[^\n]*", "", body)
    for token in ("load_half", "NTILE", "load_second_half", "sample-second-half"):
        assert token not in body, token

    # The UI must not describe a second half as something still landing.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "fills half 2 in behind the" not in mapper_js
    assert "The rest is still loading." not in mapper_js


def test_similar_names_alone_do_not_make_two_brands_a_duplicate():
    """User-reported: already-merged duplicates "came again". They were never
    duplicates. Dice bigram overlap is dominated by a shared generic suffix,
    so "Thornton Steakhouse" and "Clayton Steakhouse" scored over 0.75 on the
    strength of "steakhouse" alone.

    MEASURED against the 1,000 real sample brands (which draw names randomly
    from a shared list, so near-collisions are guaranteed): the old rule swept
    **315 brands into 125 "duplicate" groups**, only **15** of which were
    genuinely the same name - and the panel offered to irreversibly merge each
    group. The new rule reports 52 groups over 108 brands, all real.
    """
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "function sameBrandRecord(" in mapper_js
    assert "function brandFirstToken(" in mapper_js

    # Grouping must go through the stricter predicate, not raw similarity.
    grouping = mapper_js.split("function duplicateBusinessGroups(", 1)[1].split("\n    }", 1)[0]
    assert "sameBrandRecord(member.name" in grouping
    assert "brandNameSimilarity(member.name" not in grouping

    # Equal keys, containment, or similar-AND-same-first-word. Nothing else.
    predicate = mapper_js.split("function sameBrandRecord(", 1)[1].split("\n    }", 1)[0]
    assert "if (left === right) return true;" in predicate
    # Containment must be a PREFIX, never a substring anywhere.
    #
    # Measured against the live 999 brands: substring-anywhere
    # containment flagged 49 groups covering 100 brands, of which only
    # 19 were the same name. It matched "Perry Bistro" inside
    # "Daniels-Perry Bistro" and "Davis Steakhouse" inside
    # "Mcguire-Davis Steakhouse" - partnership names, i.e. different
    # businesses - and offered to merge them irreversibly. Prefix-only
    # keeps the case the rule exists for ("Domino's" / "Domino's
    # Pizza"). After the change: 20 groups / 40 brands, all genuine.
    assert "left.startsWith(right) || right.startsWith(left)" in predicate
    assert "left.includes(right) || right.includes(left)" not in predicate, \
        "substring-anywhere containment merges distinct partnership brands"
    # A shared first token plus a high bigram score is still not enough:
    # "Davis, Grill" and "Davis-Lewis Grill" clear both. The identity
    # words - those NOT used by many other brands - must match too.
    assert "sameIdentityTokenSet(" in predicate
    assert "brandFirstToken(a) !== brandFirstToken(b)) return false;" in predicate


def test_the_duplicate_rule_still_catches_what_it_was_built_for():
    """The rule exists for "Dominos Pizza" vs "Domino's Pizza Inc". Tightening
    it must not lose those - so the behaviour is asserted here, in Python,
    against the same normalization the UI applies."""
    import re as _re

    def key(n):
        n = _re.sub(r"[^a-z0-9]", "", str(n).lower())
        return _re.sub(r"\b(inc|llc|ltd|usa|us|global|stores|locations)\b", "", n)

    def first_token(n):
        toks = [t for t in _re.split(r"[^a-z0-9]+", str(n).lower()) if t]
        return toks[0] if toks else ""

    def dice(a, b):
        l, r = key(a), key(b)
        if not l or not r:
            return 0.0
        if l == r:
            return 1.0
        f = {l[i:i + 2] for i in range(len(l) - 1)}
        s = {r[i:i + 2] for i in range(len(r) - 1)}
        return 2 * len(f & s) / (len(f) + len(s)) if f and s else 0.0

    def same_brand(a, b):
        ka, kb = key(a), key(b)
        if not ka or not kb:
            return False
        if ka == kb or ka in kb or kb in ka:
            return True
        return dice(a, b) >= 0.75 and first_token(a) == first_token(b)

    # Still merged - the cases the feature was built for.
    assert same_brand("Dominos Pizza", "Domino's Pizza Inc")
    assert same_brand("Little Caesars", "Little Caesar's LLC")
    assert same_brand("Washington Roastery", "Washington-Harris Roastery")
    # Never merged - distinct brands sharing only a cuisine word.
    assert not same_brand("Thornton Steakhouse", "Clayton Steakhouse")
    assert not same_brand("Harper Steakhouse", "Johnson Steakhouse")
    assert not same_brand("Long, Burgers", "Young, Burgers")
    assert not same_brand("Pizza Hut", "Domino's Pizza")


def test_an_empty_review_queue_reads_as_success_not_as_a_broken_screen():
    """BB4: with no error listings the tab showed a bare grey line on an
    otherwise blank screen, reported as "completely disconnected". A clean
    queue is good news and should look like it."""
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert 'target.textContent = "No error listings found.";' not in review_js
    assert 'class="review-empty-ok"' in review_js
    assert "No Error Listings found" in review_js

    html = (ROOT / "ui" / "integrations.html").read_text()
    rule = html.split(".review-empty-ok {", 1)[1].split("}", 1)[0]
    assert "background: #ecfdf5;" in rule          # green, not grey
    strong = html.split(".review-empty-ok strong {", 1)[1].split("}", 1)[0]
    assert "font-size: 24px;" in strong            # big, not a caption
    assert "color: #047857;" in strong


def test_continue_without_saving_discards_the_parse():
    """BB2: it only navigated away, so the abandoned parse, its mappings and
    the selected brand survived and followed the user between tabs."""
    html = (ROOT / "ui" / "integrations.html").read_text()
    handler = html.split('el("unsavedChangesContinueBtn")?.addEventListener("click"', 1)[1].split("});", 1)[0]
    assert "resetMapping();" in handler
    assert handler.index("resetMapping();") < handler.index("switchView(pendingUnsavedNavTarget)")


def test_resetting_the_workspace_clears_the_brand_too():
    """U1: after hiding a save the 40/60 layout came back with the previous
    business still selected, and a brand was then created unasked."""
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    reset = mapper_js.split("function resetMapping()", 1)[1].split("\nfunction ", 1)[0]
    assert "selectedBrand = null;" in reset
    assert "presetBrandEditMode = false;" in reset
    assert 'brandFields.classList.remove("is-open", "editing-brand");' in reset

    # A save must never invent a brand from leftover form state.
    guard = mapper_js.split("if (!mapper.business_id) {", 1)[1].split("createNewBrand(mapper.brand)", 1)[0]
    assert "!sourceParsed" in guard
    assert 'setStatus("Select or create the brand before saving.", "warn");' in guard


def test_viewing_a_template_is_not_unsaved_work():
    """BB6: open Template Library, click Review, change nothing, navigate away
    -> "Save before you leave?". loadTemplateIntoEditor() never cleared
    pendingUnsavedParse, so a stale true from ANY earlier parse in the session
    survived and fired the prompt over a template the user had not touched."""
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    editor = templates_js.split("function loadTemplateIntoEditor(template)", 1)[1].split("\nfunction ", 1)[0]
    assert "pendingUnsavedParse = false;" in editor
    assert editor.index("templateEditMode = true;") < editor.index("pendingUnsavedParse = false;")

    # ...but changing a mapping IS unsaved work and must re-arm the prompt.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "if (templateEditMode) pendingUnsavedParse = true;" in mapper_js


def test_the_template_preview_falls_back_to_the_brands_rows():
    """BB6 part 2. Matching on template_id alone returned nothing for every
    template on a sample-loaded warehouse: listings carry the source's own
    template ids (`tmpl_john_standard`) while workflow_templates holds its
    UUIDs, so the join key never met and the editor showed an empty preview.
    Verified live: 3 records now come back, matched_by="business"."""
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.template_sample_records)
    assert "l.template_id = @template_id" in source
    assert '(@business_id != \'\' AND l.business_id = @business_id)' in source
    # Exact template matches must still sort first.
    assert "IF(l.template_id = @template_id, 0, 1) AS match_rank" in source
    assert "ORDER BY match_rank, l.last_observed_at DESC" in source
    # Ordering machinery is not data.
    assert 'if k not in ("match_rank", "custom_fields")' in source
    # Bronze directly - the editor's ground truth, no mirror.
    assert "get_cached_query" not in source
    assert '"matched_by"' in source

    # And the UI must not claim the template produced rows it did not.
    templates_js = (ROOT / "ui" / "js" / "templates.js").read_text()
    assert 'result.matched_by === "business"' in templates_js
    assert "saved for this brand" in templates_js


def test_brand_search_exists_on_both_brand_pickers_and_travels_with_its_select():
    """BB7: brand search "isn't working on UI and in 40/60 window".

    Two faults. attachSearchableSelect() inserts the search input as a SIBLING
    of #brandSelect, so it is a child of the same panel - and
    syncPreParseWorkspace() relocates that panel's children by id, sending
    everything not in `brandIds` to the parser host. The search box therefore
    ended up in a different panel from the list it filters. And the pre-parse
    picker never had a search at all."""
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    brand_ids = mapper_js.split("const brandIds = new Set(", 1)[1].split(");", 1)[0]
    assert '"brandSelectSearch"' in brand_ids, "the search box must move with its select"
    assert '"brandSelect"' in brand_ids

    sync = mapper_js.split("function syncParserBusinessSelect()", 1)[1].split("\nfunction ", 1)[0]
    assert 'attachSearchableSelect("parserBusinessSelect"' in sync
    # It must copy the FULL list, not a filtered #brandSelect.
    assert 'el("brandSelectSearch")?.dataset.allOptions' in sync

    # Both pickers still exist to attach to.
    html = (ROOT / "ui" / "integrations.html").read_text()
    assert 'id="brandSelect"' in html and 'id="parserBusinessSelect"' in html


def test_rule_r0_every_listing_names_its_business_and_its_template():
    """RULE R0 (user): template_id and business_id are FOREIGN KEYS on every
    listing - the business it belongs to, and the template whose mapping
    produced it.

    Measured before the fix: of 28,119 live listings, **0** had a template_id
    that resolved to a real workflow_template - 22,500 dangling (sample rows
    carrying the source's own ids with no template ever created for them) and
    5,619 missing entirely (every real user upload, because __meta was stamped
    only for sample rows)."""
    import whitespace_tool.workflow_server as ws
    from whitespace_tool.warehouse_bigquery import TABLE_SCHEMAS

    modes = {field["name"]: field["mode"] for field in TABLE_SCHEMAS["listings"]}
    assert modes["business_id"] == "REQUIRED"
    assert modes["template_id"] == "REQUIRED"

    # Every save stamps both ids, not just sample loads.
    save = inspect.getsource(ws.save_mapper)
    stamp = save.split("RULE R0", 1)[1].split("observed_at = utc_now_iso()", 1)[0]
    assert 'meta.setdefault("template_id", template_id)' in stamp
    assert "if sample_meta.get(\"is_sample_data\"):" in stamp, "sample-only extras stay conditional"
    # The condition must be on the ROW being a dict, not on it being sample data.
    assert "if isinstance(row, dict):" in save.split("RULE R0", 1)[0][-400:]

    # The sample loader creates the templates its listings point at, so the
    # foreign key resolves instead of dangling.
    loader = inspect.getsource(ws._load_sample_dataset_impl)
    assert "INSERT INTO `{project_id}.{dataset_id}.workflow_templates`" in loader
    assert "WHERE t.workflow_template_id = l.template_id" in loader


def test_the_template_stores_mapped_and_unmapped_structure():
    """User: "first template should get save with mapped and unmapped json
    structure and then same should be utilised in saving listing data by
    template id". A definition listing only the mapped columns is not the
    structure - and the editor cannot offer what it does not know about."""
    import whitespace_tool.workflow_server as ws

    save = inspect.getsource(ws.save_mapper)
    assert "mapped_source_fields = [value for value in (mapper.get(\"fields\") or {}).values() if value]" in save
    assert "unmapped_source_fields = [field for field in all_source_fields if field not in set(mapped_source_fields)]" in save
    components = save.split('"components": json.dumps({', 1)[1].split("}, sort_keys=True)", 1)[0]
    assert '"source_fields": all_source_fields,' in components
    assert '"unmapped_fields": unmapped_source_fields,' in components

    # And the preview surfaces the unmapped values, not just the column names.
    preview = inspect.getsource(ws.template_sample_records)
    assert '"unmapped_columns": sorted(unmapped_columns),' in preview
    assert "if key in record:" in preview, "a typed column must win over a raw extra"


def test_auto_map_button_reuses_the_parse_time_suggestion_pass():
    """U2: with parsed columns but nothing mapped there was no way back to the
    suggestions - renderMappings() only suggests for target keys ABSENT from
    mappingSelections, and a cleared field leaves an empty-string key behind.
    The button deletes those, handing the existing pass its own precondition
    back, rather than adding a second matching implementation."""
    html = (ROOT / "ui" / "integrations.html").read_text()
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    assert 'id="autoMapFieldsBtn"' in html
    assert 'el("autoMapFieldsBtn")?.addEventListener("click", () => autoMapUnmappedFields());' in html

    action = mapper_js.split("function autoMapUnmappedFields()", 1)[1].split("\nfunction ", 1)[0]
    assert "if (!mappingSelections[key]) delete mappingSelections[key];" in action
    assert "forceAutoMapOnce = true;" in action
    assert "renderMappings();" in action
    # It must NOT contain its own matching logic.
    assert "suggestField(" not in action

    # One shot only - it must not keep re-suggesting over later edits.
    assert "if (sourceParsed || forceAutoMapOnce) {" in mapper_js
    assert "forceAutoMapOnce = false;" in mapper_js

    # Offered only when it can help: parsed columns and nothing mapped.
    visibility = mapper_js.split("function updateAutoMapButton()", 1)[1].split("\nfunction ", 1)[0]
    assert 'button.classList.toggle("hidden", !(sourceFields.length && mappedCount === 0));' in visibility
    assert "updateAutoMapButton();" in mapper_js.split("function renderMappings", 1)[1][:6000]


def test_brand_search_survives_the_panel_relocation():
    """BB7 follow-up: the search box "doesn't pop up". syncPreParseWorkspace()
    moves nodes using a snapshot of the panel's children taken once - an input
    created after that snapshot is not in the list that moves back, so it was
    stranded in the hidden panel. The component now re-homes itself."""
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    assert "if (search && search.parentNode !== select.parentNode) {" in common_js
    assert "select.parentNode.insertBefore(search, select);" in common_js

    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    restore = mapper_js.split("        preParseRelocatedNodes = null;", 1)[1][:700]
    assert 'attachSearchableSelect("brandSelect"' in restore
    assert 'attachSearchableSelect("parserBusinessSelect"' in restore

    # Case- and whitespace-insensitive matching on both sides.
    assert 'search.value.trim().toLowerCase().replace(/\\s+/g, " ")' in common_js
    assert 'String(option.text || "").toLowerCase().replace(/\\s+/g, " ").includes(query)' in common_js


def test_one_source_column_can_only_fill_one_target_field():
    """BB1: XML mapping "force assigns", one column filling several fields.
    applyMappingSelection() enforced this for a user's dropdown pick, but
    nothing enforced it for mappings written in BULK - presets, restored
    drafts, templates. setPizzaHutMappings() shipped with the column "address"
    mapped to BOTH `name` and `address`."""
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    dedupe = mapper_js.split("function dedupeMappingSelections(orderedTargets)", 1)[1].split("\nfunction ", 1)[0]
    assert 'mappingSelections[target.key] = "";' in dedupe
    assert "autoMappedKeys.delete(target.key);" in dedupe

    # Runs from renderMappings, so every bulk path passes through it, with
    # required targets keeping the column.
    render = mapper_js.split("function renderMappings()", 1)[1]
    assert "const droppedDuplicates = dedupeMappingSelections(dedupeOrder);" in render
    assert "...visibleTargets.filter((target) => target.required)," in render
    # And it says what it did rather than silently dropping a mapping.
    assert "can only fill one field" in render

    # The preset that shipped the duplicate is fixed at source too.
    preset = mapper_js.split("function setPizzaHutMappings()", 1)[1].split("\nfunction ", 1)[0]
    # Strip comments first - the one explaining the removed duplicate
    # legitimately quotes it.
    body = re.sub(r"//[^\n]*", "", preset.split("};", 1)[0])
    columns = re.findall(r"\w+:\s*\"([^\"]+)\"", body)
    assert len(columns) == len(set(columns)), f"preset still maps a column twice: {columns}"


def test_a_demo_preset_does_not_lock_you_to_its_own_brand():
    """BB3: the preset panel disabled #brandSelect once its brand existed, so
    a demo source could only ever be tested against that one business."""
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    panel = mapper_js.split("function updatePresetBrandPanel", 1)[1].split("\nfunction ", 1)[0]
    assert 'el("brandSelect").disabled = false;' in panel
    assert 'el("brandSelect").disabled = Boolean(exists);' not in panel
    # The brand FORM stays locked - only the choice of business is freed.
    assert "lockBrandFields(Boolean(exists && !presetBrandEditMode));" in panel
    assert "Pick a different one above" in panel


def test_the_notice_dialog_carries_tone_rather_than_being_a_bare_paragraph():
    """User: "this is too plain, you have other alert boxes better". The
    notice was a heading, a rule, and a sentence in a mostly empty box. It now
    carries an icon whose colour states the outcome, and each caller passes
    the tone it actually is."""
    html = (ROOT / "ui" / "integrations.html").read_text()
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()

    assert 'id="appNoticeIcon"' in html
    assert '<div class="app-notice-body">' in html
    for tone in ("tone-warn", "tone-error", "tone-info"):
        assert f".app-notice.{tone} .app-notice-icon" in html

    # Default success, and only the icon changes - the shell stays shared.
    assert 'dialog.classList.remove("tone-warn", "tone-error", "tone-info");' in common_js
    assert 'if (tone && tone !== "ok") dialog.classList.add(`tone-${tone}`);' in common_js

    # Failures must not be announced with a success tick.
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert '"Export failed", "error");' in reporting_js
    assert '"Save did not finish", "error");' in mapper_js


def test_the_brand_list_survives_unrelated_cache_invalidation():
    """User: "aren't you using local db for faster brand search?". The list is
    BigQuery-backed and cached in SQLite - measured 6.0s cold vs 6ms warm for
    1,000 brands - but the blanket invalidate_cache() threw it away on any
    save or background pass, so the next dropdown open paid the full 6s."""
    from whitespace_tool import sqlite_cache
    import whitespace_tool.workflow_server as ws

    invalidate = inspect.getsource(sqlite_cache.invalidate_cache)
    assert "cache_key NOT LIKE 'list_brands:%'" in invalidate
    assert "invalidate_brand_cache" in inspect.getsource(sqlite_cache)

    # Every path that genuinely changes the brand list clears it explicitly.
    for function in (ws.create_brand, ws.update_brand, ws.merge_brands,
                     ws.clear_saved_data, ws.master_delete_data, ws.clear_sample_dataset):
        assert "invalidate_brand_cache()" in inspect.getsource(function), function.__name__


def test_the_searchable_select_shows_a_real_suggestion_list():
    """User: "why is that suggestion not showing as an outside display like
    standard suggestion lists". Filtering the <select>'s own options only
    helps once its dropdown is already open - typing appeared to do nothing."""
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    assert 'panel.className = "select-suggestions hidden";' in common_js
    assert 'panel.setAttribute("role", "listbox");' in common_js
    assert "data-suggestion-value" in common_js
    # Clicking a suggestion selects it and tells the app.
    assert 'select.dispatchEvent(new Event("change"));' in common_js
    # The panel used to be position:absolute inside whatever card held the
    # control, which clipped it against the sticky, internally-scrolling filter
    # rail. It is position:fixed now, so it takes its coordinates from the
    # input's own live rect instead of an offset parent - and must therefore be
    # repositioned whenever the viewport or any ancestor scroller moves.
    assert 'search.parentNode.style.position = "relative";' not in common_js, \
        "the panel no longer relies on an offsetParent - do not reinstate it"
    assert 'panel.style.position = "fixed";' in common_js
    assert "const rect = search.getBoundingClientRect();" in common_js
    # capture:true - scroll does not bubble, so a nested scroller (the rail)
    # would otherwise leave the panel stranded where it was opened.
    assert 'window.addEventListener("scroll", onViewportChange, true);' in common_js
    assert 'window.addEventListener("resize", onViewportChange);' in common_js
    # The "create new" row is pinned to the top of the list, and the empty
    # text is generic (this select is not brand-only any more).
    assert '__create_new__' in common_js
    assert '" is-create"' in common_js
    assert '<div class="select-suggestion-empty">No matches</div>' in common_js
    assert "No matching brand" not in common_js

    # BB8: no item cap - a fixed height with scrolling instead, so a broad
    # query still reaches every match rather than stopping at an arbitrary N.
    assert ".slice(0, 12)" not in common_js
    # renderSuggestions grew a showAll parameter when the native <select>
    # popup was suppressed (see
    # test_the_searchable_select_suppresses_the_native_dropdown_popup); the
    # no-item-cap contract it guards is unchanged.
    panel = common_js.split("const renderSuggestions = (query, showAll = false) => {", 1)[1].split("\n      };", 1)[0]
    assert ".slice(" not in panel

    html = (ROOT / "ui" / "integrations.html").read_text()
    rule = html.split(".select-suggestions {", 1)[1].split("}", 1)[0]
    assert "overflow-y: auto;" in rule
    assert "max-height:" in rule
    assert ".select-suggestion:hover" in html


def test_the_searchable_select_suppresses_the_native_dropdown_popup():
    """User-reported: with ~1,000 brands the brand dropdown opened as a
    full-screen list with no usable scroll.

    A native <select> popup is drawn by the OS, not the page: max-height,
    overflow and size on the <select> or its <option>s are simply ignored, so
    no amount of CSS shortens it. Styling the typeahead panel never helped
    because the panel was not what opened. The only fix is to not open the
    native popup at all - preventDefault() on mousedown - and hand the click
    to the panel, which does have a fixed max-height and its own scroll.
    """
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    attach = common_js.split("function attachSearchableSelect(", 1)[1].split("\nfunction ", 1)[0]

    assert "select.onmousedown = (event) => {" in attach, "the native popup is no longer suppressed"
    mousedown = attach.split("select.onmousedown = (event) => {", 1)[1].split("\n      };", 1)[0]
    # The suppression itself - without this the OS popup opens regardless.
    assert "event.preventDefault();" in mousedown
    # ...but NOT for a locked select: template review pins the brand to the
    # template's own business_id, and a disabled control must not offer a
    # list to pick from. Right-click is left alone too.
    assert "if (event.button !== 0 || select.disabled) return;" in mousedown
    bail_at = mousedown.index("select.disabled")
    prevent_at = mousedown.index("event.preventDefault();")
    assert bail_at < prevent_at, "a disabled select must bail out BEFORE preventDefault"
    # The bounded panel opens in the native popup's place, showing everything
    # (showAll=true) - clicking the control is how you browse the full list.
    assert "search.focus();" in mousedown
    assert "renderSuggestions(search.value.trim().toLowerCase().replace(/\\s+/g, \" \"), true);" in mousedown

    # Keyboard use of the select is deliberately untouched - only mousedown
    # is intercepted, so no onkeydown/onclick handler may be added here.
    assert "select.onclick" not in attach
    assert "select.onkeydown" not in attach

    # The panel it opens instead is the one CSS can actually bound.
    rule = HTML.split(".select-suggestions {", 1)[1].split("}", 1)[0]
    assert "max-height:" in rule
    assert "overflow-y: auto;" in rule


def test_focusing_the_search_box_shows_nothing_until_something_is_typed():
    """Explicit instruction: "on click on search icon should not show any
    suggestion, unless something is inputted".

    Focus must NOT open the full list. Dumping 1,000 names under the cursor
    the moment the box is clicked is the same wall of text the native popup
    gave, just in a different container - the panel is for narrowing.
    """
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    attach = common_js.split("function attachSearchableSelect(", 1)[1].split("\nfunction ", 1)[0]

    focus = attach.split("search.onfocus = () => {", 1)[1].split("\n      };", 1)[0]
    assert "if (query) renderSuggestions(query);" in focus
    assert "else hideSuggestions();" in focus
    # showAll is reserved for the click that replaced the native popup; focus
    # must never pass it, or the "nothing until typed" rule is gone.
    assert ", true)" not in focus, "focus opens the full list again"

    # And the renderer backs that up: an empty query without showAll closes
    # the panel rather than listing everything.
    render = attach.split("const renderSuggestions = (query, showAll = false) => {", 1)[1].split("\n      };", 1)[0]
    assert "if (!query && !showAll) return hideSuggestions();" in render


def test_create_new_brand_stays_reachable_from_the_suggestion_panel():
    """Now that the native popup never opens, the panel is the ONLY route to
    the "__create_new__" option - if a query could filter it out, brand
    creation would be stranded with no other entry point. So it is pinned:
    collected separately from the matches, never passed through the query
    filter, and rendered first."""
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    attach = common_js.split("function attachSearchableSelect(", 1)[1].split("\nfunction ", 1)[0]
    render = attach.split("const renderSuggestions = (query, showAll = false) => {", 1)[1].split("\n      };", 1)[0]

    assert 'const pinned = all.filter((option) => option.value === "__create_new__");' in render
    # Excluded from the matches, so it can never be listed twice...
    assert 'option.value !== "__create_new__"' in render
    # ...and rendered ahead of them, flagged for the sticky styling.
    assert 'panel.innerHTML = pinned.map((option) => renderRow(option, " is-create")).join("")' in render
    # A query that matches no brand still renders the pinned row - the panel
    # only collapses to the empty state when there is nothing at all to show.
    # (Typing a name that does not exist yet is exactly who needs Create New.)
    assert "if (!matches.length && !pinned.length) {" in render
    # It is a normal suggestion row, so the existing click path selects it.
    assert "data-suggestion-value" in render

    # Sticky to the top, so it survives scrolling a thousand brands.
    create_rule = HTML.split(".select-suggestion.is-create {", 1)[1].split("}", 1)[0]
    assert "position: sticky;" in create_rule
    assert "top: 0;" in create_rule

    # The option really is on the brand pickers this pins for.
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "__create_new__" in mapper_js


def test_suggestion_empty_text_is_generic_not_brand_specific():
    """The panel now backs the County/City/State/Issue Type filters as well as
    the brand pickers (REPORT_SEARCHABLE_FILTERS in js/reporting.js,
    QUALITY_SEARCHABLE_FILTERS in reporting-tabs.js), so "No matching brand"
    was wrong on most of the controls that can show it."""
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    assert '<div class="select-suggestion-empty">No matches</div>' in common_js
    assert "No matching brand" not in common_js
    # The placeholder is generic for the same reason - only the two brand
    # pickers name what they search.
    assert 'search.placeholder = (selectId === "brandSelect" || selectId === "parserBusinessSelect")' in common_js
    assert '? "Search brand" : "Search";' in common_js


def test_brand_suggest_threshold_is_declared_not_just_referenced():
    """A previous refactor deleted the declaration and left the use behind -
    a latent ReferenceError that only fires on the brand-suggestion path, so
    nothing catches it until a user hits that screen."""
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert re.search(r"^const BRAND_SUGGEST_THRESHOLD\s*=", mapper_js, re.M), \
        "BRAND_SUGGEST_THRESHOLD is referenced but never declared"
    assert "entry.score >= BRAND_SUGGEST_THRESHOLD" in mapper_js


def test_saving_a_brand_leaves_it_selectable_and_searchable():
    """BB9/BB10: after saving, the brand was not the dropdown's selection and
    the suggestion list could not offer it.

    Backend was fine - verified live, create-then-search returns the new brand
    immediately. Two client-side causes:
      1. createNewBrand()/updateExistingBrand() reloaded with the brand's NAME
         as a search term, so the dropdown held only the matches.
      2. attachSearchableSelect() returned early when the (now short) option
         list was under threshold - WITHOUT refreshing its cache - so the
         cache kept a list that predated the new brand. The next keystroke
         rebuilt the select from that stale cache and the brand vanished.
    """
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()

    # Neither save path may reload a name-filtered list.
    assert "await loadBrands(selectedBrand.name);" not in mapper_js
    for path in ("createNewBrand", "updateExistingBrand"):
        body = mapper_js.split(f"async function {path}(", 1)[1].split("\nfunction ", 1)[0]
        assert "await loadBrands();" in body, path
        assert 'el("brandSelect").value = selectedBrand.business_id;' in body, path

    # The cache is refreshed before the threshold bail-out, never after.
    attach = common_js.split("function attachSearchableSelect(", 1)[1].split("\nfunction ", 1)[0]
    refresh_at = attach.index("existing.dataset.allOptions = JSON.stringify(liveOptions)")
    bail_at = attach.index("if (liveOptions.length <= threshold) return;")
    assert refresh_at < bail_at, "a short list must still refresh the cache"


def test_a_duplicate_brand_name_is_refused_not_created():
    """BB11: the same name, case-insensitively, must not become a second
    brand. The cheapest duplicate to resolve is the one never made - creating
    it and offering a merge afterwards is the expensive path."""
    import whitespace_tool.workflow_server as ws

    # Server side is the real gate: the UI prompt can be skipped by a retry,
    # a second tab, or any other caller.
    create = inspect.getsource(ws.create_brand)
    # The guard no longer runs as its own SELECT - it is folded INTO the write
    # as INSERT ... SELECT ... WHERE NOT EXISTS, because a separate single-row
    # SELECT costs 1.59s on this warehouse (see
    # test_creating_a_brand_costs_one_statement_not_two, which pins the
    # absence of the old standalone check). The gate itself is unchanged:
    # case- and whitespace-insensitive, server side, so a duplicate arriving
    # from a retry or a second tab is still refused.
    assert "INSERT INTO `{project_id}.{dataset_id}.businesses`" in create
    assert "WHERE NOT EXISTS (" in create
    assert "LOWER(TRIM(REGEXP_REPLACE(name, r'\\\\s+', ' '))) = @normalized_name" in create
    assert '" ".join(name.lower().split())' in create
    # Living inside the INSERT is what makes it unraceable - it must be part
    # of that statement, not a check that happens to precede it.
    assert create.index("INSERT INTO") < create.index("WHERE NOT EXISTS (")
    # A refused duplicate must be reported as such, not silently passed off as
    # a fresh create: 0 affected rows means the guard matched.
    assert 'created = int(getattr(insert_job, "num_dml_affected_rows", 0) or 0) > 0' in create
    assert 'return {"brand": brand, "created": created}' in create

    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    resolver = mapper_js.split("async function resolveExistingBrandForName(name)", 1)[1].split("\nasync function ", 1)[0]
    # Exact match (case- and whitespace-insensitive) is refused outright.
    assert '.toLowerCase().replace(/\\s+/g, " ")' in resolver
    assert '"Brand already exists", "info");' in resolver
    # A close name is a QUESTION, not a decision - two similar names can be
    # two real businesses.
    assert "const BRAND_SUGGEST_THRESHOLD = 0.8;" in mapper_js
    assert "brandNameSimilarity(brand.name || \"\", wanted)" in resolver
    assert "showAppConfirm(" in resolver
    assert "return useExisting ? close.brand : null;" in resolver

    # And creation actually consults it, selecting the existing brand instead.
    creator = mapper_js.split("async function createNewBrand(", 1)[1].split("\nfunction ", 1)[0]
    assert "const existing = await resolveExistingBrandForName(name);" in creator
    assert creator.index("resolveExistingBrandForName") < creator.index('fetch("/api/brands"')
    assert "Using existing brand" in creator


def test_the_review_tab_endpoints_are_all_wired():
    """The Review tab was reported as "entirely disconnected". Verified live:
    every endpoint it calls answers 200 and the queue is genuinely empty
    (error_listings held 396 rows, all soft-deleted, 0 live). This pins the
    endpoint names so a rename cannot silently break the tab again - the
    queue is /api/rejected, NOT /api/error-listings."""
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    for endpoint in ("/api/rejected?", "/api/error-listings/count",
                     "/api/error-listings/by-brand", "/api/review/fix-states",
                     "/api/enrichment/status", "/api/reprocess"):
        assert endpoint in review_js, endpoint

    import whitespace_tool.workflow_server as ws
    handler = inspect.getsource(ws.make_handler)
    for route in ("/api/rejected", "/api/error-listings/count",
                  "/api/error-listings/by-brand", "/api/review/fix-states"):
        assert route in handler, route


def test_creating_a_brand_costs_one_statement_not_two():
    """BB12: single-row DB operations are slow. MEASURED on this warehouse -
    INSERT 2.36s, SELECT by key 1.59s, UPDATE 2.60s, DELETE 2.93s, versus
    0.01s for a SQLite mirror read. BigQuery schedules every statement as a
    query job, so the cost is per STATEMENT, not per row.

    The BB11 duplicate check was therefore folded INTO the insert rather than
    run as its own SELECT: a separate check would have made every brand create
    ~4s instead of ~2.4s, for no added safety - a guard in the same statement
    as the write cannot race it."""
    import whitespace_tool.workflow_server as ws

    create = inspect.getsource(ws.create_brand)
    # One write statement, carrying its own guard.
    assert "INSERT INTO `{project_id}.{dataset_id}.businesses`" in create
    assert "WHERE NOT EXISTS (" in create
    assert "= @normalized_name" in create
    # No standalone pre-check SELECT on the hot path.
    assert "create_brand:duplicate_check" not in create
    # And the caller is told which happened.
    assert 'created = int(getattr(insert_job, "num_dml_affected_rows", 0) or 0) > 0' in create
    assert 'return {"brand": brand, "created": created}' in create

    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    assert "const wasCreated = result.created !== false;" in mapper_js
    assert "already existed, so it has been selected instead of creating a second copy." in mapper_js


def test_the_pre_parse_layout_says_brand_on_both_sides_not_business():
    """BB13: OBSERVED on the 40/60 pre-parse screen - the left pane's picker
    was labelled "Brand" and the right pane's, visible at the same moment,
    was labelled "Business". Two names on one screen for the one thing the
    user chooses. "Business" is the BACKEND's word (business_id, the
    businesses table); the user was never supposed to meet it.

    The element IDs still contain "Business" ON PURPOSE - they are backend
    identifiers and renaming them is a refactor, not a copy fix - so this
    test reads VISIBLE TEXT only."""
    html = (ROOT / "ui" / "integrations.html").read_text()

    # The label that carried the wrong word, and its screen-reader twin.
    assert '<label for="parserBusinessSelect">Brand</label>' in html
    assert '<label for="parserBusinessSelect">Business</label>' not in html
    assert '<label id="brandSelectLabel" for="brandSelect">Brand</label>' in html
    assert 'aria-label="Select brand before parsing"' in html

    # Attribute VALUES are stripped before the text is read, so an id or a
    # data-* attribute containing "Business" cannot fail this on its own -
    # the two assertions below prove that both ways round: the id is still
    # present in the markup, and absent from the visible text.
    def visible_text(markup):
        without_attribute_values = re.sub(r"""=\s*(?:"[^"]*"|'[^']*')""", "", markup)
        return re.sub(r"<[^>]*>", " ", without_attribute_values)

    assert 'id="parserBusinessSelect"' in html
    left_pane = html.split('<div id="mapperView" class="pre-parse-active">', 1)[1].split("</aside>", 1)[0]
    text = visible_text(left_pane)
    assert "parserBusinessSelect" not in text
    assert "Brand" in text, "the pre-parse pane markup was not found"
    assert "business" not in text.lower(), "the pre-parse pane still shows the backend's word"

    # The same rename in the two sentences users actually read.
    assert "belongs to this business" not in (ROOT / "ui" / "js" / "templates.js").read_text()
    assert "Could not update business." not in (ROOT / "ui" / "js" / "mapper.js").read_text()


def test_the_map_never_swaps_to_an_empty_layer_when_zooming_in():
    """BB14: OBSERVED - markers disappeared on zoom in. The zoom handler used
    to show exactly ONE of three groups, which is how crossing a threshold
    could reveal a layer holding nothing: a blank map, no error.

    Two things fix that, and both are asserted here. (1) The two AGGREGATE
    layers (state / city bubbles) are the only zoom-gated ones, and the tier
    falls back when the tier it picked has nothing IN THE CURRENT VIEW.
    (2) The real-row layers - listing markers and whitespace gap ZIPs - are
    shown unconditionally at every tier, so there is always something drawn.

    The two marker groups also used to be cross-named: the store loop filled
    `gapMarkersLayerGroup` and the gap loop filled `pinMarkersLayerGroup`, so
    the handler did the inverse of its own comment. The store group is
    `storeMarkersLayerGroup` now, and the old name must not come back."""
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()

    # The cross-named group is gone for good.
    assert "pinMarkersLayerGroup" not in reporting_js, "the cross-named marker group is back"
    # The store loop fills the STORE group and the gap loop the GAP group.
    assert "storeMarkersLayerGroup" in reporting_js

    # An absent group counts as empty - the groups are null until first render.
    assert "function layerHasContent(group)" in reporting_js
    helper = reporting_js.split("function layerHasContent(group)", 1)[1].split("\nfunction ", 1)[0]
    assert "if (!group) return false;" in helper
    assert "getLayers().length > 0" in helper

    # ...and a layer whose content is all off-screen is no better: clicking a
    # state bubble flies to a city tier whose bubbles may be 2000 miles away.
    assert "function layerHasContentInView(group)" in reporting_js
    in_view = reporting_js.split("function layerHasContentInView(group)", 1)[1].split("\nfunction ", 1)[0]
    assert "reportingMap.getBounds()" in in_view
    assert "view.contains(position)" in in_view
    assert "return layerHasContent(group);" in in_view, "must degrade to the plain check, not to false"

    sync = reporting_js.split("function syncMapLayersByZoom()", 1)[1].split("\nlet mapZoomListenerAttached", 1)[0]

    # The tier must stay reassignable - a const could not fall back at all.
    assert "let tier =" in sync
    assert "const tier =" not in sync

    # The thresholds themselves are unchanged; only emptiness overrides them.
    assert "currentZoom >= 9.5" in sync
    assert 'currentZoom >= 6.0 ? "city" : "state"' in sync
    assert "Boolean(activeCityFilter || activeZipFilter) ||" in sync

    # BOTH aggregate tiers are guarded, not just the one that was reported.
    assert 'if (tier === "listing" && !layerHasContentInView(storeMarkersLayerGroup)) {' in sync
    assert 'if (tier === "city" && !layerHasContentInView(cityCirclesLayerGroup)) {' in sync
    assert 'tier = "state";' in sync

    # And the guards resolve the tier BEFORE anything is added or removed -
    # deciding after the swap would still show the blank frame first.
    assert sync.index("layerHasContentInView") < sync.index("toggleMapLayer(")

    # Listing markers and gap ZIPs are not zoom levels: shown at every tier,
    # unconditionally, and never gated on the tier value.
    assert "toggleMapLayer(storeMarkersLayerGroup, true);" in sync
    assert "toggleMapLayer(gapMarkersLayerGroup, true);" in sync
    # Only the aggregates are tier-gated.
    assert 'toggleMapLayer(stateCirclesLayerGroup, tier === "state");' in sync
    assert 'toggleMapLayer(cityCirclesLayerGroup, tier === "city");' in sync
    # No hand-rolled add/removeLayer pairs in here - that inconsistency is
    # exactly what cross-named the groups; everything goes through the helper.
    assert "addLayer(" not in sync
    assert "removeLayer(" not in sync

    # Wired to the events that expose the bug, and run once after each render.
    assert 'reportingMap.on("zoomend", syncMapLayersByZoom);' in reporting_js
    # Which tier is worth showing depends on the current view, so panning has
    # to re-decide it too.
    assert 'reportingMap.on("moveend", syncMapLayersByZoom);' in reporting_js
    assert "syncMapLayersByZoom();" in reporting_js


def test_both_reporting_tabs_apply_their_filters_automatically():
    """BB15: OBSERVED - the Data Quality tab applied its filters as they were
    changed; the Location Intelligence tab beside it did not. The same gesture
    on two same-looking sidebars updated one tab and silently did nothing on
    the other until "Apply All Filters" was pressed.

    Fixed by giving BOTH rails the same switch - attachAutoApplyToggle() in
    js/reporting.js, mounted into a host element in each. ONE implementation
    is the point: two would drift apart again, which is the bug. So this
    asserts the component, its two mount points and its behaviour, and stays
    off the rails' own markup and CSS, which are still being unified."""
    html = (ROOT / "ui" / "integrations.html").read_text()
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()

    # One shared implementation, not one per tab.
    assert reporting_js.count("function attachAutoApplyToggle(") == 1
    component = reporting_js.split("function attachAutoApplyToggle(", 1)[1].split("\nfunction ", 1)[0]

    # Both rails mount it, each into its own host, each with its own switch id.
    assert 'id="reportAutoApplyHost"' in html
    assert 'id="dqAutoApplyHost"' in reporting_tabs_js
    assert "reportAutoApplyToggle" in reporting_js
    assert "dqAutoApplyToggle" in reporting_tabs_js

    def mount_call(source, host_id):
        # Quote-agnostic: reporting.js writes double quotes, reporting-tabs.js
        # single, and neither spelling is the contract.
        match = re.search(r"attachAutoApplyToggle\(\s*[\"']%s[\"']" % re.escape(host_id), source)
        assert match, f"{host_id} is never mounted"
        return source[match.start(): match.start() + 1500]

    # Each rail reloads ITS OWN view - a shared switch that reloaded only one
    # of them would reproduce the bug in the other direction.
    assert "loadReporting(" in mount_call(reporting_js, "reportAutoApplyHost")
    assert "loadQuality(" in mount_call(reporting_tabs_js, "dqAutoApplyHost")

    # A real switch, not a button that renames itself: a checkbox with
    # role="switch", hidden by size/opacity rather than display:none, so it
    # keeps keyboard focus and Space to flip it.
    assert 'type="checkbox" role="switch"' in component
    input_rule = reporting_js.split(".auto-apply-toggle .auto-apply-toggle-input{", 1)[1].split("}", 1)[0]
    assert "opacity:0" in input_rule
    assert "display:none" not in input_rule

    # Default ON, with the state on the wrapper (both rails style off it).
    assert "checked>" in component
    assert 'wrapper.dataset.auto = "on";' in component
    assert 'wrapper.dataset.auto = input.checked ? "on" : "off";' in component

    # 400ms debounce, so three changes in a row are one query and not three.
    assert "delayMs = 400" in reporting_js
    assert "window.clearTimeout(timer);" in component
    assert "timer = window.setTimeout(" in component
    assert ", delayMs);" in component
    # More than one clearTimeout: the reschedule cancels the pending run, and
    # cancel() exists separately for an explicit Apply/Reset.
    assert component.count("clearTimeout") >= 2

    # Switched off, nothing is scheduled and anything pending is dropped;
    # switched back on, an apply is scheduled at once so the view can never
    # sit out of step with the controls it is showing.
    assert "if (!input.checked) return;" in component
    change_handler = component.split('input.addEventListener("change"', 1)[1].split("});", 1)[0]
    assert "input.checked" in change_handler
    assert "schedule();" in change_handler
    assert "cancel();" in change_handler

    # Auto-apply supplements each rail's explicit buttons rather than
    # replacing them, and Apply/Reset subsume a debounce still counting down
    # instead of letting it fire the same query again a moment later.
    for source, button in (
        (html, "applyReportFiltersBtn"),
        (html, "resetReportFiltersBtn"),
        (reporting_tabs_js, "applyQualityFiltersBtn"),
        (reporting_tabs_js, "resetQualityFiltersBtn"),
    ):
        assert f'id="{button}"' in source, button
        handler = re.search(r"%s[^\n]*addEventListener" % re.escape(button), source)
        assert handler, f"{button} has no click handler"
        assert "cancel" in source[handler.start(): handler.start() + 2000], \
            f"{button} does not cancel a pending auto-apply"


def test_the_create_brand_form_stays_out_of_the_parsed_workspace():
    """OBSERVED: right after a parse, the "Create Brand" form popped open on
    top of the freshly parsed mapping workspace. renderMappings() still routes
    through updatePreParseBrandMode(), and that function is what opens the
    form - but the form belongs to the PRE-PARSE layout only. Parsing is
    exactly what drops the pre-parse-active class, so the class is the test:
    no class, no form."""
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    mode = mapper_js.split("function updatePreParseBrandMode()", 1)[1].split("\nfunction ", 1)[0]

    # Two separate guards, for two separate ways in. The first keeps the form
    # off every OTHER view (loadAppData -> renderMappings runs on all of
    # them); the second keeps it out of the mapper's own post-parse layout.
    assert 'if (el("mapperView")?.classList.contains("hidden")) return;' in mode
    assert 'if (!el("mapperView")?.classList.contains("pre-parse-active")) return;' in mode

    # Both must sit BEFORE the only line that opens the form - a guard after
    # it would run too late to stop anything.
    opens_at = mode.index('openBrandEditorForm("create")')
    assert mode.index('classList.contains("hidden")) return;') < opens_at
    assert mode.index('classList.contains("pre-parse-active")) return;') < opens_at

    # And the class really is the parsed/not-parsed signal the guard reads:
    # renderMappings drops it as soon as there is mapping content, then calls
    # straight into this function.
    assert 'mapperView?.classList.toggle("pre-parse-active", !hasMappingContent);' in mapper_js
    assert "if (!hasMappingContent) updatePreParseBrandMode();" in mapper_js


def test_the_brand_helpers_are_declared_and_not_merely_referenced():
    """A refactor deleted `const BRAND_SUGGEST_THRESHOLD = 0.8;` while the
    duplicate-name check that USES it survived - a latent ReferenceError that
    only fires when someone happens to type a name close to an existing brand.
    Nothing catches that: an undeclared identifier is valid JavaScript, so
    `node --check` passes it, and the page loads fine until that one path runs.

    So every helper the brand controls stand on must be DECLARED in mapper.js,
    not merely mentioned there."""
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    all_ui_js = _all_ui_js()

    for symbol in (
        "renderBrandOptions",     # the one render path for the dropdown
        "rememberedBrands",       # localStorage read
        "rememberBrands",         # localStorage write
        "paintRememberedBrands",  # cold-start paint, called from common.js
        "BRAND_MEMORY_KEY",
        "BRAND_SUGGEST_THRESHOLD",
        "duplicateBusinessGroups",
        "businessOptionLabel",
        "loadBrands",
    ):
        declared = re.search(
            r"(?:^|\n)[ \t]*(?:async[ \t]+)?(?:function|const|let|var)[ \t]+%s\b" % re.escape(symbol),
            mapper_js,
        )
        assert declared, f"{symbol} is referenced but never declared in mapper.js"
        # ...and genuinely used somewhere, so a helper nothing calls any more
        # is not what keeps this test green. Counted across all the UI scripts
        # because several of these are called from common.js, not mapper.js.
        uses = len(re.findall(r"\b%s\b" % re.escape(symbol), all_ui_js))
        assert uses > 1, f"{symbol} is declared but never used"
