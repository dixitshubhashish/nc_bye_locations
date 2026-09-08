from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "ui" / "integrations.html").read_text()
COMMON_JS = (ROOT / "ui" / "js" / "common.js").read_text()


def test_header_groups_keep_primary_tabs_and_compact_utilities():
    assert '<nav class="top-tabs" aria-label="Primary navigation">' in HTML
    assert '<div class="header-data-actions">' in HTML
    assert '<div class="header-account-actions">' in HTML
    assert 'grid-template-areas: "title tabs utilities"' in HTML
    assert 'grid-template-areas: "sample reset zipstatus" "sample restart zipsync"' in HTML
    assert '.header-account-actions { display: flex; flex-direction: column;' in HTML
    assert '.header-account-actions #appHelpBtn::before' in HTML
    assert 'header.reporting-active #resetMappingBtn' not in HTML
    assert 'el("restartMappingBtn").classList.toggle("hidden", viewId !== "mapperView")' not in COMMON_JS
    assert 'el("resetMappingBtn").classList.toggle("hidden", viewId !== "mapperView")' not in COMMON_JS
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


def test_reporting_hero_actions_are_clear_and_refresh_only():
    assert 'id="refreshReportBtn"' in HTML
    assert 'id="clearSampleDatasetLink"' in HTML
    assert HTML.index('id="refreshReportBtn"') < HTML.index('id="clearSampleDatasetLink"')
    assert 'sample-load-link danger hidden' in HTML
    assert 'id="reloadSampleDatasetLink"' not in HTML
    assert 'grid-template-columns: auto auto;' in HTML
    assert 'justify-content: end;' in HTML
    assert '.sample-load-link.danger' in HTML
    assert '.report-hero-actions #clearSampleDatasetLink' in HTML
    assert 'min-height: 44px;' in HTML
    assert 'background: #dc2626;' in HTML
    assert 'refreshReportingNow();' in HTML
    assert 'el("clearSampleDatasetLink")?.addEventListener("click", () => clearSampleDataset());' in HTML
    assert 'el("reloadSampleDatasetLink")?.addEventListener' in HTML


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
    load_quality = reporting_tabs_js.split("async function loadQuality", 1)[1].split("function init()", 1)[0]

    force_refresh_block = load_quality.split("if (forceRefresh) {", 1)[1].split("} else {", 1)[0]
    assert "hasData" not in force_refresh_block
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
    assert "Report refresh started. Updating numbers..." in refresh_function
    assert "Report refresh is already running..." in refresh_function
    assert "await loadReporting({ interactive: true });" in refresh_function
    assert "clearButtonBusy(refreshBtn, previousRefreshBtn);" in refresh_function


def test_interactive_reporting_reload_keeps_visible_background_refresh_status():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    load_reporting = reporting_js.split("async function loadReporting", 1)[1].split("async function refreshReportingNow", 1)[0]

    assert "interactive && result.refreshing" in load_reporting
    assert "Refreshing report in the background..." in load_reporting
    assert "if (interactive && !result.refreshing) status.classList.add(\"hidden\");" not in load_reporting
    assert "if (interactive && !result.refreshing && hasBusinessData) status.classList.add(\"hidden\");" in load_reporting


def test_reporting_zero_setup_polls_frequently_until_business_data_exists():
    reporting_js = (ROOT / "ui" / "js" / "reporting.js").read_text()
    load_reporting = reporting_js.split("async function loadReporting", 1)[1].split("async function refreshReportingNow", 1)[0]

    assert "let reportingWarmupTimer = null;" in reporting_js
    assert "function reportHasBusinessData" in reporting_js
    assert "function scheduleReportingWarmupPoll" in reporting_js
    assert "window.setTimeout" in reporting_js
    assert "Preparing reporting data..." in load_reporting
    assert "scheduleReportingWarmupPoll(3000);" in load_reporting
    assert "clearTimeout(reportingWarmupTimer);" in load_reporting


def test_reporting_tab_refresh_preserves_selected_inner_tab():
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    init_block = reporting_tabs_js.split("function init()", 1)[1]

    assert "new URLSearchParams(window.location.search).get('reportTab')" in init_block
    assert "sessionStorage.getItem('reportingInnerTab')" in init_block
    assert "initialTab = requestedTab === 'quality' ? 'quality' : (sessionStorage.getItem('reportingInnerTab') === 'quality' ? 'quality' : 'location');" in init_block
    assert "switchTab(initialTab);" in init_block
    assert "$('refreshDataQualityBtn')?.addEventListener('click', () => loadQuality(true));" in init_block


def test_reporting_has_both_tab_panels_and_switches_each_independently():
    reporting_tabs_js = (ROOT / "ui" / "reporting-tabs.js").read_text()
    switch_tab = reporting_tabs_js.split("function switchTab(name)", 1)[1].split("tabs.addEventListener", 1)[0]

    assert 'data-report-tab="location"' in reporting_tabs_js
    assert 'data-report-tab="quality"' in reporting_tabs_js
    assert "shell.querySelectorAll('.report-location-panel').forEach((n) => n.classList.toggle('hidden', name !== 'location'));" in switch_tab
    assert "quality.classList.toggle('hidden', name !== 'quality');" in switch_tab
    assert "if (name === 'quality') loadQuality();" in switch_tab
    assert "if (name === 'location' && typeof window.reportingMap?.invalidateSize === 'function')" in switch_tab


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
    server_py = (ROOT / "whitespace_tool" / "workflow_server.py").read_text()
    registry = (ROOT / "config" / "field_registry.json").read_text()

    assert '{ key: "country", table: "listings", field: "country", label: "Country", required: false' in mapper_js
    assert 'REQUIRED_MAPPER_FIELDS = {"name", "address", "city", "state", "postal_code"}' in server_py
    assert 'REQUIRED_LOCATION_VALUES = ("name", "address", "city", "state", "postal_code")' in server_py
    assert '"key":"country","table":"listings","field":"country","label":"Country","type":"string","required":false' in registry


def test_parse_once_keeps_standard_mapping_workspace_until_reset():
    mapper_js = (ROOT / "ui" / "js" / "mapper.js").read_text()

    assert "let mappingWorkspaceActivated = false;" in mapper_js
    assert "mappingWorkspaceActivated || sourceParsed || sourceFields.length || activeTemplateId" in mapper_js
    assert "sourceParsed = true;\n        mappingWorkspaceActivated = true;" in mapper_js
    assert "sourceParsed = false;\n      mappingWorkspaceActivated = false;" in mapper_js


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
