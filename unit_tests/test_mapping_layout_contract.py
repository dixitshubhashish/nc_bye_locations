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

    assert 'src="reporting-tabs.js?v=quality-layout-v2"' in HTML
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
    assert "report-filter-category-title" in HTML
    assert "white-space: nowrap;" in HTML
    assert '<div class="report-filter-category-title">\n                📍 Geographic Filters' in HTML
    assert '<div class="report-filter-category-title">\n                👥 Demographic Filters' in HTML


def test_reporting_zip_filter_has_debounced_scoped_typeahead():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    typeahead = reporting_js.split("function setupZipTypeahead()", 1)[1].split("function reportingQueryString()", 1)[0]

    assert 'id="reportZipFilter" list="zipSuggestions"' in HTML
    assert 'id="zipSuggestions"' in HTML
    assert "let zipTypeaheadRequestId = 0;" in reporting_js
    assert 'zipInput.addEventListener("input"' in typeahead
    assert "if (!query)" in typeahead
    assert "query.length < 2" not in typeahead
    assert 'datalist.innerHTML = "";' in typeahead
    assert "setTimeout(async () =>" in typeahead
    assert "}, 250);" in typeahead
    assert 'el("reportStateFilter")?.value' in typeahead
    assert 'el("reportCountyFilter")?.value' in typeahead
    assert 'el("reportCityFilter")?.value' in typeahead
    assert "fetch(`/api/zips/search?q=${encodeURIComponent(query)}&state=${encodeURIComponent(state)}&county=${encodeURIComponent(county)}&city=${encodeURIComponent(city)}`)" in typeahead
    assert "if (requestId !== zipTypeaheadRequestId) return;" in typeahead


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
    assert '<div id="mapperView" class="pre-parse-active">' in HTML
    assert 'id="preParseBrandPanel"' in HTML
    assert 'id="preParseBrandHost"' in HTML
    assert 'id="preParseParserHost"' in HTML
    assert 'id="parserBusinessSelect"' in HTML
    assert 'id="parserBusinessValidation"' in HTML
    assert 'js/mapper.js?v=preparse-layout-v5' in HTML


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
    assert 'sampleButton.title = loaded ? "Sample data already in place." : "";' in mapper_js
    assert 'sampleButton.textContent = loaded ? "Sample Dataset Already Loaded" : "Load Sample Dataset";' in mapper_js


def test_enrichment_status_polling_stops_after_terminal_state():
    # startEnrichmentStatusPolling's setInterval used to run forever with no
    # stop condition - once it ever saw the job running, it must clear
    # itself the next time the job is no longer running (idle/stopped/failed).
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    assert "function stopEnrichmentStatusPolling()" in reporting_js
    assert "window.clearInterval(enrichmentStatusTimer);" in reporting_js
    poll_fn = reporting_js.split("function startEnrichmentStatusPolling()", 1)[1].split("\nasync function refreshReportingData", 1)[0]
    assert "let sawRunning = false;" in poll_fn
    assert "if (sawRunning && !running) stopEnrichmentStatusPolling();" in poll_fn


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
    assert ".report-filter-label {" in html
    assert ".report-filter-control {" in html
    sidebar = html.split('<aside class="reporting-sidebar-pane"', 1)[1].split("</aside>", 1)[0]
    # Every sidebar filter label/control must use the shared classes - inline
    # font-size/font-weight is what let the three groups drift out of sync.
    assert 'class="report-filter-label"' in sidebar
    assert sidebar.count('class="report-filter-control"') >= 8
    assert "font-size: 11px; font-weight: 600; color: var(--ink); margin-bottom" not in sidebar
    # All three category headings use the class, not a hand-copied inline clone.
    assert sidebar.count('class="report-filter-category-title"') == 3


def test_geo_and_competitor_filters_search_only_after_two_characters():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    assert "function setupGeoFilterSearch()" in reporting_js
    assert "function applyGeoOptionSearch(selectId)" in reporting_js
    assert "query.length < 2" in reporting_js
    # The active selection and the blank "All X" option always survive the filter.
    assert "!option.value || option.value === selected" in reporting_js
    assert 'class="competitor-brand-search"' in reporting_js
    assert "setupGeoFilterSearch();" in (ROOT / "ui" / "integrations.html").read_text()
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
    assert "if (record.business_id) {" in modal_fn
    assert "fetch(`/api/templates?business_id=${encodeURIComponent(record.business_id" in modal_fn
    assert "templates.find((t) => t.workflow_template_id === record.template_id)) || templates[0]" in modal_fn
    assert "const sourceKeyToTargetKey = {};" in modal_fn
    assert "formatFieldLabel(mappedTargetKey)" in modal_fn
    # Falls back to the live Mapper UI state only when no saved mapping
    # was found (e.g. a legacy row with no template_id) - never silently
    # skips populating fields altogether.
    assert 'const activeMapper = typeof getMapper === "function" ? getMapper() : { fields: {} };' in modal_fn


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
    assert "<p>Where your brand stands versus competitors" in HTML


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
    load = mapper_js.split("async function loadBrands(", 1)[1].split("\nasync function ", 1)[0]

    assert "const duplicateGroups = duplicateBusinessGroups(brands);" in load
    assert "hiddenDuplicateIds" in load
    # The dropdown is built from the FILTERED list, never the raw one.
    assert "const selectableBrands = brands.filter((brand) => !hiddenDuplicateIds.has(brand.business_id));" in load
    assert "selectableBrands.map((brand) =>" in load
    # A currently-selected duplicate stays visible, or the dropdown would
    # silently blank out the user's own selection.
    assert "if (selectedBrand?.business_id) hiddenDuplicateIds.delete(selectedBrand.business_id);" in load
    # dataset.brands keeps the FULL list so the rail can still see duplicates.
    assert "el(\"brandSelect\").dataset.brands = JSON.stringify(brands);" in load
    assert "renderDuplicateBrandRail(duplicateGroups);" in load


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

    loader = inspect.getsource(ws.load_sample_dataset)
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


def test_quality_sidebar_matches_tab_one_filter_styling():
    # Reported: the Data Quality sidebar had extra spacing/framing tab 1 does
    # not. Concretely it was a white card WITH a shadow whose inner fields
    # carried 12px padding inside an already-16px-padded container - doubled
    # framing - while tab 1 uses a tinted container with 8px inner boxes.
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()

    # Same container treatment as .report-filters in integrations.html.
    assert "background: var(--accent-tint);" in HTML
    assert "border: 1px solid var(--accent-tint-line);" in HTML
    assert "background:var(--accent-tint);border:1px solid var(--accent-tint-line)" in tabs_js
    # No shadow - tab 1's container has none.
    assert "box-shadow:0 1px 3px rgba(0,0,0,.05)}" not in tabs_js.split(".dq-filters{", 1)[1].split("}", 1)[0] + "}"
    # Inner field boxes match .report-filter-group's 8px padding.
    assert ".report-filter-group { border: 1px solid var(--line); background: #ffffff; border-radius: 8px; padding: 8px; }" in HTML
    assert ".dq-sidebar .dq-filter-field{padding:8px}" in tabs_js
    assert ".dq-sidebar .dq-filter-field{padding:12px}" not in tabs_js


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
    assert 'records.some((row) => row[key] !== null && row[key] !== "")' in templates_js
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
    load = mapper_js.split("async function loadBrands(", 1)[1].split("\nasync function ", 1)[0]
    assert 'title="${escapeHtml(businessOptionLabel(brand))}"' in load
    assert "${escapeHtml(formatBrandName(brand.name))}</option>" in load


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


def test_quality_filters_auto_apply_with_a_stop_and_restart_toggle():
    # Asked for: "filters should be auto applied, with a choice to stop auto
    # apply button which change from stop to restart auto apply".
    tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()

    assert 'id="autoApplyFiltersBtn"' in tabs_js
    assert "let autoApplyFilters = true;" in tabs_js
    # Every filter control triggers it, not just one.
    assert "const QUALITY_FILTER_IDS = ['dqBrandFilter', 'dqStateFilter', 'dqReasonFilter', 'dqStatusFilter', 'dqStartDate', 'dqEndDate'];" in tabs_js
    assert "$(id)?.addEventListener('change', scheduleAutoApply);" in tabs_js
    # Debounced: three quick changes are one query, not three.
    assert "window.clearTimeout(autoApplyTimer);" in tabs_js
    assert "autoApplyTimer = window.setTimeout(() => loadQuality(), 400);" in tabs_js
    # The one button carries both labels.
    assert "button.textContent = autoApplyFilters ? 'Stop auto apply' : 'Restart auto apply';" in tabs_js
    # Restarting applies whatever changed while it was off, so the view can
    # never sit out of step with the controls.
    restart = tabs_js.split("if (autoApplyFilters) {", 1)[1].split("} else {", 1)[0]
    assert "scheduleAutoApply();" in restart
    # Off state is visually distinct.
    assert "#autoApplyFiltersBtn[data-auto='off']" in tabs_js
    # The explicit Apply button survives for a manual re-run.
    assert "$('applyQualityFiltersBtn')?.addEventListener('click', () => loadQuality());" in tabs_js


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
    assert 'function showAppNotice(message, title = "Done")' in common_js
    assert 'function showAppConfirm(message, title = "Please confirm")' in common_js
    assert 'id="appNoticeDialog"' in HTML and 'id="appConfirmDialog"' in HTML

    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()
    # The mapping-move prompt and the reset acknowledgement both went themed.
    assert "const move = await showAppConfirm(" in mapper_js
    assert 'showAppNotice("Workspace reset complete.' in mapper_js
    # Brand save/update now acknowledge in-theme, not just an inline banner.
    assert 'showAppNotice(`${formatBrandName(selectedBrand.name)} was created' in mapper_js
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

    # Markup now lives in tab 1, before the map section.
    tab_one = HTML.split('<div id="reportContent" class="hidden">', 1)[1].split("<!-- Location Map Section -->", 1)[0]
    assert 'id="dqHistoryChart"' in tab_one
    assert 'data-history-period="1W"' in tab_one
    assert 'data-history-period="1Y"' in tab_one
    # Same toggle markup as Trends, so both controls look identical.
    assert 'class="dq-period-toggle" role="group" aria-label="History period"' in tab_one
    # Removed from the quality panel.
    assert 'id="dqHistoryChart"' not in tabs_js.split("function buildQualityPanel", 1)[1].split("return panel", 1)[0]

    # Plots LISTINGS over time from the timeseries endpoint, not a single
    # invalid-records series from the quality snapshot.
    assert "async function loadQualityHistory()" in tabs_js
    assert "/api/reporting/timeseries?" in tabs_js
    assert "pick('Locations')" in tabs_js
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
    review_js = (ROOT / "ui" / "js" / "review.js").read_text()
    assert "const reviewTemplateCache = new Map();" in review_js
    assert "let templates = reviewTemplateCache.get(record.business_id);" in review_js
    assert "reviewTemplateCache.set(record.business_id, templates);" in review_js


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


def test_sample_data_loads_in_two_ntile_halves():
    # Splitting in SQL (NTILE(2)) rather than orchestrating halves in Python:
    # half 1 lands fast so the button can flip to "loaded", half 2 fills in
    # behind it. One statement per half also means a slow row cannot hold the
    # whole load hostage, which is what looked like a hang at "94%".
    import inspect
    import whitespace_tool.workflow_server as ws

    source = inspect.getsource(ws.load_sample_dataset)
    assert "def load_sample_dataset(reset: bool = False, load_half: int = 1)" in source
    assert "NTILE(2) OVER (ORDER BY listing_id) AS load_half" in source
    assert "WHERE s.load_half = @load_half" in source
    # Half 2 must ADD to half 1, not wipe it.
    assert "if load_half == 1:\n            client.query(f\"DELETE FROM" in source
    # Half 2 is kicked off in the background after half 1 returns.
    assert 'threading.Thread(target=load_second_half, name="sample-second-half", daemon=True).start()' in source
    assert "load_sample_dataset(reset=False, load_half=2)" in source


def test_brand_search_is_plain_and_client_side():
    # It filters the select's own options in memory - it never queries the
    # server - so explaining a minimum character count was noise.
    common_js = (ROOT / "ui" / "js" / "common.js").read_text()
    assert 'search.placeholder = selectId === "brandSelect" ? "Search brand" : "Search";' in common_js
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

    dialogs = re.findall(r"<dialog\b[^>]*>", html)
    assert len(dialogs) >= 12, f"expected the full dialog set, found {len(dialogs)}"
    for tag in dialogs:
        assert 'class="app-help-dialog' in tag, f"dialog off the shell: {tag}"
        assert "aria-labelledby=" in tag, f"dialog with no labelled title: {tag}"

    # Each dialog body carries the shell's content/header/title structure.
    for body in re.findall(r"<dialog\b[^>]*>(.*?)</dialog>", html, re.S):
        assert '<div class="app-help-content">' in body
        assert '<div class="app-help-header">' in body
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
