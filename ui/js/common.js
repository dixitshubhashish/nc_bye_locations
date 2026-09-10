// Shared/common utilities used across all tabs: DOM helpers, formatting,
// loading overlays, status messaging, login/session bootstrap.

let appDataLoaded = false;
let appReady = false;
let readinessCheckInFlight = null;
const loginReadinessTimeoutMs = 2500;

let sourceTypes = [];

// Canonical human-readable labels for internal source_type keys, matching
// the #sourceType select in the Mappings tab - reused wherever a source
// type needs to be displayed (e.g. the Template Library table/filter)
// instead of showing the raw code name.
const SOURCE_TYPE_LABELS = {
  csv: "CSV",
  excel: "EXCEL (.XLSX)",
  api_get_json: "GET API JSON",
  json: "JSON",
  python_editor: "PYTHON EDITOR",
  xml: "XML",
};
function sourceTypeLabel(sourceTypeKey) {
      return SOURCE_TYPE_LABELS[sourceTypeKey] || String(sourceTypeKey || "Unknown");
    }

const loginSessionStorageKey = "competitive_whitespace_login_session";
const mappingSessionStorageKey = "competitive_whitespace_mapping_session";
const serverLaunchStorageKey = "competitive_whitespace_server_launch";
const el = (id) => document.getElementById(id);

// Keep an expired session from leaving the shell in a partially rendered
// state. Login/session probes must be allowed to report their own errors
// without redirecting recursively.
//
// 401/403 ONLY, deliberately NOT 404 (found and fixed 2026-09-10): 401/403
// are the only statuses that actually mean "this session is not
// authenticated" - a 404 means one specific resource/route was not found,
// which happens for perfectly ordinary reasons unrelated to the session
// (a stale in-flight request for a record that was just deleted, a
// not-yet-existing gold view during a rebuild, a genuinely missing route).
// Treating 404 as "wipe the session and hard-navigate to /login" meant
// ANY single such 404, anywhere on the page, force-redirected the whole
// app away from whatever the user was looking at mid-render - a
// self-inflicted version of exactly the "page never settles / numbers
// never render" symptom this was chasing. Endpoints that need their own
// retry-on-failure behavior (e.g. refreshReviewFixStates() in review.js)
// can only ever get a chance to run if a transient failure does NOT
// immediately blow away the page out from under them.
if (!window.__authResponseGuardInstalled) {
  const nativeFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const response = await nativeFetch(...args);
    const requestUrl = String(args[0]?.url || args[0] || "");
    const isAuthProbe = requestUrl.includes("/api/login") || requestUrl.includes("/api/session");
    if ([401, 403].includes(response.status) && !isAuthProbe && !window.location.pathname.endsWith("/login")) {
      sessionStorage.removeItem(loginSessionStorageKey);
      sessionStorage.removeItem(mappingSessionStorageKey);
      window.location.replace("/login");
    }
    return response;
  };
  window.__authResponseGuardInstalled = true;
}
function newSessionId() {
      return window.crypto?.randomUUID ? window.crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    }

function escapeHtml(value) {
      return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }
function productSafeError(message, fallback = "Something went wrong. Please try again.") {
      const text = String(message || "");
      const sensitiveTerms = ["big" + "query", "data" + "set", "project" + "_id", "data" + "set_id", "credentials", "service" + " account", "google", "s" + "ql", "ware" + "house", "bron" + "ze", "sil" + "ver", "table", "module named"];
      if (sensitiveTerms.some((term) => text.toLowerCase().includes(term))) {
        return fallback;
      }
      return text || fallback;
    }

function formatNumber(value) {
      const number = Number(value || 0);
      return Number.isFinite(number) ? number.toLocaleString() : "0";
    }
// Every created_at/updated_at display (Template Library, brand list, etc.)
// should read down to the second, not a bare ISO string with fractional
// seconds and a "T" separator, and not date-only either - shared so every
// such timestamp is formatted identically instead of drifting per call site.
// Shared searchable-select behavior (FLT-02/FLT-03/FLT-05 all use this same
// component, per the explicit "build once, not three implementations"
// instruction). Rebuilds the real <option> list on input instead of hiding
// options with CSS, since a native <select>'s open dropdown does not
// reliably respect display:none on options across browsers - removing them
// from the DOM does. Call again (e.g. after reloading the option list) to
// refresh the cached options; it reuses the existing search input rather
// than creating a duplicate.
function attachSearchableSelect(selectId, { threshold = 15, minChars = 2, hasMore = false } = {}) {
      const select = document.getElementById(selectId);
      if (!select) return;
      const liveOptions = Array.from(select.options).map((option) => ({ value: option.value, text: option.textContent, className: option.className }));
      // Refresh the cache BEFORE the threshold check. Bailing out early left
      // an existing input holding a stale option list: after saving a brand,
      // loadBrands() reloads with a search term, the select briefly holds
      // only a handful of options, this returned - and the cache kept the old
      // list, which did not contain the brand just created. The suggestion
      // panel then could not offer it, and the next keystroke rebuilt the
      // select from that stale list, so the new brand vanished from the
      // dropdown too (BB9/BB10).
      const existing = document.getElementById(`${selectId}Search`);
      if (existing && liveOptions.length) existing.dataset.allOptions = JSON.stringify(liveOptions);
      // Threshold only gates a SMALL, already-complete list (e.g. a 5-option
      // source-format picker) out of getting pointless search chrome. It must
      // never gate out the box on a list that is merely still loading - the
      // brand pickers start with just the 2 static options (blank +
      // "+ Create New Brand") before the network round trip resolves, and
      // waiting for >threshold real brands to exist meant the box (and the
      // ability to type at all) simply was not there for the first several
      // seconds on a cold load. `hasMore` lets a caller that KNOWS more data
      // is coming (the brand pickers) force the box to exist immediately.
      if (!hasMore && liveOptions.length <= threshold) return;

      // Dropdown stays on the left at its full width; the search box is a
      // collapsed icon by default and only takes space (shrinking the
      // select) once the user actually opens it - a permanently-visible
      // second input next to the select was the thing being replaced here.
      // Wrapping both in one element also sidesteps every surrounding
      // layout's own column rules (a grid, a flex row, a plain block panel):
      // the wrap is a single self-contained flex row wherever it lands, so
      // it does not depend on - or fight with - whatever CSS the wrap's
      // parent happens to apply to ITS children.
      let wrap = document.getElementById(`${selectId}SearchWrap`);
      if (!wrap) {
        wrap = document.createElement("div");
        wrap.id = `${selectId}SearchWrap`;
        wrap.className = "searchable-select-wrap";
        select.parentNode.insertBefore(wrap, select);
        wrap.appendChild(select);
      } else if (wrap.parentNode == null || select.parentNode !== wrap) {
        // Self-healing, same reason as before: a panel relocation elsewhere
        // in the app (syncPreParseWorkspace) can move the select without
        // knowing this wrap exists yet if it ran before this function's
        // first call. Put the select back inside its own wrap rather than
        // trusting where either one was left.
        wrap.appendChild(select);
      }
      let search = existing;
      if (!search) {
        search = document.createElement("input");
        search.type = "search";
        search.id = `${selectId}Search`;
        search.className = "report-filter-control searchable-select-input";
        search.autocomplete = "off";
        // Plain label. This filters the select's own options in memory
        // (liveOptions above) - it never queries the server - so there is no
        // reason to explain a minimum length to the user.
        // Both brand pickers (the mapping view's and the 40/60 pre-parse
        // window's) say what they search; everything else is generic.
        search.placeholder = (selectId === "brandSelect" || selectId === "parserBusinessSelect")
          ? "Select or search brand" : "Search";
        search.setAttribute("aria-label", "Search this list");
      }
      let toggle = document.getElementById(`${selectId}SearchToggle`);
      if (!toggle) {
        toggle = document.createElement("button");
        toggle.type = "button";
        toggle.id = `${selectId}SearchToggle`;
        toggle.className = "searchable-select-toggle";
        // An inline SVG, not the 🔍 emoji: an emoji renders in its own
        // fixed built-in colors on every platform, so `color`/size/rotation
        // CSS on the button had no visible effect on it. `currentColor`
        // makes this glyph a normal styleable icon instead.
        toggle.innerHTML = '<svg viewBox="0 0 24 24" width="1em" height="1em" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><circle cx="10" cy="10" r="7"></circle><line x1="21" y1="21" x2="15.2" y2="15.2"></line></svg>';
        toggle.setAttribute("aria-label", "Search this list");
      }
      if (search.parentNode !== wrap) wrap.appendChild(search);
      if (toggle.parentNode !== wrap) wrap.appendChild(toggle);
      search.dataset.allOptions = JSON.stringify(liveOptions);

      // ONE visible control, not two: the underlying <select> is hidden by
      // CSS (.searchable-select-wrap > select { display: none }) and kept
      // only for its value/change-event semantics - every earlier version
      // of this component that showed a select AND a search box side by
      // side, in any collapsed/expanded arrangement, kept rendering as two
      // visibly separate boxes depending on the surrounding layout, which
      // is what was actually being reported. The search input is now the
      // only thing on screen, always full width, and behaves like a
      // combobox: it displays the current selection's text when not being
      // edited, and clicking/focusing it opens the full list exactly like
      // a native <select> would - typing narrows it, same as before.
      const syncDisplayedValue = () => {
        if (document.activeElement === search) return; // don't fight typing
        if (!select.value) { search.value = ""; return; }
        const current = liveOptions.find((option) => option.value === select.value);
        search.value = current?.text || "";
      };
      syncDisplayedValue();
      const openFullList = () => {
        // A disabled search input (see setTemplateEditBrandLock()) is the
        // ONLY visible control now that the real <select> is hidden -
        // disabling the select alone no longer stops interaction, since
        // nothing is reading that property here otherwise.
        if (search.disabled) return;
        search.focus();
        renderSuggestions(search.value.trim().toLowerCase().replace(/\s+/g, " "), true);
      };
      // Re-bind on every call rather than only once: idempotent and cheap.
      toggle.onclick = openFullList;

      // A real suggestion list, not just a filtered <select>.
      //
      // Filtering the select's own options only helps once the dropdown is
      // already open - the user typing sees nothing happen, which is why this
      // read as "the suggestion doesn't pop up". A standard typeahead panel
      // shows the matches under the input as you type, click to choose.
      let panel = document.getElementById(`${selectId}Suggestions`);
      if (!panel) {
        panel = document.createElement("div");
        panel.id = `${selectId}Suggestions`;
        panel.className = "select-suggestions hidden";
        panel.setAttribute("role", "listbox");
      }
      // Re-home on every call, for the same reason the input is re-homed:
      // this app physically relocates these controls between panels. Only
      // the DOM position matters now: the panel is position:fixed and takes
      // its coordinates from the input's own rect (positionSuggestions,
      // below), so it no longer needs its container to be a positioning
      // context and no longer forces position:relative onto it.
      if (panel.parentNode !== search.parentNode) {
        search.parentNode.insertBefore(panel, search.nextSibling);
      }

      const hideSuggestions = () => { panel.classList.add("hidden"); panel.innerHTML = ""; };

      // ---- Viewport-anchored placement ---------------------------------
      // The panel was absolutely positioned inside whatever card held the
      // control, so ANY ancestor with overflow auto/hidden/clip sliced it off
      // at that ancestor's edge. The reporting filter rail is exactly such an
      // ancestor: it is pinned (position:sticky) AND scrolls inside itself,
      // because a pinned rail that does not scroll internally leaves its own
      // "Apply All Filters" / "Reset All" buttons below the fold with no way
      // to reach them. Both of those have to hold at once, so the panel is
      // the piece that has to get out.
      //
      // position:fixed is how it gets out: a fixed box's containing block is
      // the viewport, and an ancestor's overflow only clips descendants whose
      // containing-block chain runs through it - so the rail's scroll box
      // cannot touch this panel. (Nothing between these controls and <body>
      // sets transform/filter/contain, which are the properties that would
      // drag a fixed box back inside an ancestor.) The trade is that a fixed
      // box does not travel with its anchor, so the coordinates are computed
      // from the input's live rect on open and again on every scroll/resize
      // while the panel is open.
      const PANEL_MAX_HEIGHT = 320; // keep in step with .select-suggestions
      const VIEWPORT_MARGIN = 8;
      const ANCHOR_GAP = 2;
      // Nearest clipping ancestor - the filter rail, on both reporting tabs.
      // Resolved once per attach (the option list is re-read far more often
      // than the controls are relocated) and used only to tell whether the
      // anchor is still showing.
      let clipper;
      const getClipper = () => {
        if (clipper !== undefined) return clipper;
        clipper = null;
        let node = search.parentElement;
        while (node && node !== document.body && node !== document.documentElement) {
          try {
            const style = window.getComputedStyle(node);
            if (/(auto|scroll|hidden|clip)/.test(`${style.overflowY} ${style.overflowX}`)) { clipper = node; break; }
          } catch (_) {}
          node = node.parentElement;
        }
        return clipper;
      };
      // Scrolling the rail can carry the input out of sight while it still
      // holds focus. A panel left hanging beside nothing is worse than no
      // panel, so that case closes it instead of repositioning it.
      const anchorOnScreen = (rect) => {
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        if (rect.bottom <= 0 || rect.top >= viewportHeight) return false;
        if (rect.right <= 0 || rect.left >= viewportWidth) return false;
        const box = getClipper()?.getBoundingClientRect();
        return !box || (rect.bottom > box.top && rect.top < box.bottom);
      };
      const positionSuggestions = () => {
        if (panel.classList.contains("hidden")) return;
        const rect = search.getBoundingClientRect();
        if (!anchorOnScreen(rect)) { hideSuggestions(); return; }
        const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
        const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
        // The panel stands in for the select's own popup, so it matches the
        // control's width. min-width has to be overridden as well, or the
        // stylesheet's generic 220px floor makes the panel wider than a
        // narrow control and hangs it off that control's right edge.
        const width = Math.round(rect.width) || search.offsetWidth || select.offsetWidth;
        if (width) {
          panel.style.width = `${width}px`;
          panel.style.minWidth = `${width}px`;
          panel.style.maxWidth = "none";
        }
        const roomBelow = viewportHeight - rect.bottom - ANCHOR_GAP - VIEWPORT_MARGIN;
        const roomAbove = rect.top - ANCHOR_GAP - VIEWPORT_MARGIN;
        // Flip above the input when there is more room up there. This is what
        // keeps the LAST filters in a pinned rail usable: a control sitting
        // near the bottom of the viewport has almost nothing under it, and a
        // fixed panel drawn downwards would run off the screen - a fixed box
        // does not lengthen the page, so nothing could ever scroll to it.
        const flipUp = roomBelow < Math.min(PANEL_MAX_HEIGHT, roomAbove) && roomAbove > roomBelow;
        panel.style.maxHeight = `${Math.max(120, Math.min(PANEL_MAX_HEIGHT, flipUp ? roomAbove : roomBelow))}px`;
        panel.style.position = "fixed";
        panel.style.right = "auto";
        const maxLeft = viewportWidth - (width || rect.width) - VIEWPORT_MARGIN;
        panel.style.left = `${Math.round(Math.max(VIEWPORT_MARGIN, Math.min(rect.left, maxLeft)))}px`;
        if (flipUp) {
          panel.style.top = "auto";
          panel.style.bottom = `${Math.round(viewportHeight - rect.top + ANCHOR_GAP)}px`;
        } else {
          panel.style.bottom = "auto";
          panel.style.top = `${Math.round(rect.bottom + ANCHOR_GAP)}px`;
        }
      };
      // Anything that can move the anchor has to move the panel: the page
      // scrolling, the rail scrolling inside itself, the window resizing.
      // capture:true is required for the middle one - scroll events do not
      // bubble, so a listener on window only sees a nested scroller's scroll
      // during the capture phase. Registered once per panel: this whole
      // function re-runs on every option-list refresh, so the previous pair
      // is removed first rather than piling up a listener per rebuild.
      if (typeof panel.__untrackViewport === "function") panel.__untrackViewport();
      const onViewportChange = () => positionSuggestions();
      window.addEventListener("scroll", onViewportChange, true);
      window.addEventListener("resize", onViewportChange);
      panel.__untrackViewport = () => {
        window.removeEventListener("scroll", onViewportChange, true);
        window.removeEventListener("resize", onViewportChange);
      };
      const choose = (value) => {
        // search.oninput() narrows select.innerHTML down to only whatever
        // matched the LAST thing typed, and nothing ever widens it back out
        // afterwards - so picking a suggestion for a brand that isn't in
        // that stale, narrowed option list makes `select.value = value` a
        // silent no-op (assigning a <select> a value with no matching
        // <option> is simply ignored by the browser, no error). That is
        // "the dropdown loads suggestions but picking one doesn't set
        // anything" - the option genuinely was not there to select. Rebuild
        // from the full cached list first so the value being set always
        // has something to land on.
        if (!Array.from(select.options).some((option) => option.value === value)) {
          const all = JSON.parse(search.dataset.allOptions || "[]");
          select.innerHTML = all.map((option) => `<option value="${escapeHtml(option.value)}"${option.className ? ` class="${escapeHtml(option.className)}"` : ""}>${escapeHtml(option.text)}</option>`).join("");
        }
        select.value = value;
        hideSuggestions();
        select.dispatchEvent(new Event("change"));
        // Display the chosen option's TEXT, combobox-style - this is the
        // one visible control, so it has to show what got picked, not go
        // blank the way a "search box next to a select" could afford to.
        // Set it directly rather than via syncDisplayedValue(): its "don't
        // fight typing" guard (`activeElement === search` => no-op) also
        // swallowed this call, because the suggestion panel's mousedown
        // handler calls preventDefault() specifically to keep focus on the
        // input - so a completed click-selection left the box showing the
        // last-typed query (e.g. "Pizza") instead of the brand actually
        // picked (e.g. "Domino's Pizza"), even though the underlying
        // <select> value was already correct. Confirmed live in a headless
        // browser (2026-09-10).
        const chosenOption = JSON.parse(search.dataset.allOptions || "[]").find((option) => option.value === value);
        search.value = chosenOption ? chosenOption.text : "";
      };
      panel.onmousedown = (event) => {
        const row = event.target.closest("[data-suggestion-value]");
        if (!row) return;
        event.preventDefault();
        choose(row.dataset.suggestionValue);
      };
      search.onblur = () => window.setTimeout(() => {
        hideSuggestions();
        // Nothing chosen - restore the display to whatever is actually
        // selected (a typed query with no pick made must not overwrite the
        // real value shown to the user).
        syncDisplayedValue();
      }, 150);
      // Focusing shows the FULL list immediately (this is the one visible
      // control now, so it has to double as the dropdown - a bare click
      // with nothing typed yet must behave like opening a <select>, not
      // show nothing until the user starts typing). Select-all on focus so
      // a click-to-open immediately lets typing REPLACE the shown value
      // rather than insert into the middle of it.
      search.onfocus = () => {
        search.select();
        renderSuggestions(search.value.trim().toLowerCase().replace(/\s+/g, " "), true);
      };
      search.onkeydown = (event) => { if (event.key === "Escape") hideSuggestions(); };
      toggle.setAttribute("aria-label", "Open brand list");

      // showAll: open the panel with the whole list, for focus/click. The
      // native <select> popup cannot be height-capped by CSS - with 1,000
      // brands the browser draws a list the length of the screen. The panel
      // can be, and already is (.select-suggestions: fixed max-height with
      // scroll), so opening it on focus gives the user the bounded, scrollable
      // list instead of the native one.
      const renderSuggestions = (query, showAll = false) => {
        if (!query && !showAll) return hideSuggestions();
        const all = JSON.parse(search.dataset.allOptions || "[]");
        // "+ Create New Brand" is a real <option> on these selects. Now that
        // the native popup never opens, the panel is the ONLY way to reach it,
        // so pin it to the top and keep it visible whatever the query - it is
        // an action, not a search result, and a user typing a name that does
        // not exist yet is exactly who needs it.
        const pinned = all.filter((option) => option.value === "__create_new__");
        const matches = all
          .filter((option) => option.value && option.value !== "__create_new__"
            && (!query || String(option.text || "").toLowerCase().replace(/\s+/g, " ").includes(query)))
          ;
        // No item cap: the panel has a fixed height and scrolls (see
        // .select-suggestions), so truncating the list only hid brands the
        // user had already narrowed to. With 1,000 brands a one-character
        // query can legitimately match a hundred of them, and the twelfth
        // being silently the last is worse than a scrollbar.
        if (!matches.length && !pinned.length) {
          if (!query) return hideSuggestions();
          panel.innerHTML = '<div class="select-suggestion-empty">No matches</div>';
          panel.classList.remove("hidden");
          positionSuggestions();
          return;
        }
        const renderRow = (option, extraClass = "") =>
          `<div class="select-suggestion${extraClass}" role="option" data-suggestion-value="${escapeHtml(option.value)}">${escapeHtml(option.text)}</div>`;
        panel.innerHTML = pinned.map((option) => renderRow(option, " is-create")).join("")
          + (matches.length ? matches.map((option) => renderRow(option)).join("")
             : (query ? '<div class="select-suggestion-empty">No matches</div>' : ""));
        panel.classList.remove("hidden");
        // Width AND coordinates both come from the input's live rect now,
        // not from an offset parent - see positionSuggestions above.
        positionSuggestions();
      };

      search.oninput = () => {
        const allOptions = JSON.parse(search.dataset.allOptions || "[]");
        const query = search.value.trim().toLowerCase().replace(/\s+/g, " ");
        const selected = select.value;
        // Case- and whitespace-insensitive, and it matches anywhere in the
        // name, so "verde" finds "Casa Verde" and "CASA" finds it too.
        const matches = query.length < minChars
          ? allOptions
          : allOptions.filter((option) => !option.value
              || option.value === selected
              || String(option.text || "").toLowerCase().replace(/\s+/g, " ").includes(query));
        select.innerHTML = matches.map((option) => `<option value="${escapeHtml(option.value)}"${option.className ? ` class="${escapeHtml(option.className)}"` : ""}>${escapeHtml(option.text)}</option>`).join("");
        select.value = matches.some((option) => option.value === selected) ? selected : "";
        renderSuggestions(query);
      };

      // The user may already be typing against the placeholder 2-option list
      // (blank + "+ Create New Brand") when the real data lands - a later
      // call to this function refreshes `search.dataset.allOptions` above,
      // but nothing repaints the select or the open panel until the NEXT
      // keystroke. Re-run the already-typed query against the fresh data now
      // instead of leaving a stale/empty result sitting under an unchanged
      // input - same effect as if the user had just typed the last character
      // again, minus the keystroke.
      if (document.activeElement === search && search.value.trim()) {
        search.oninput();
      }
    }
function formatTimestamp(value) {
      if (!value) return "";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      const pad = (n) => String(n).padStart(2, "0");
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    }
function formatBrandName(value) {
      return String(value ?? "").trim().replace(/_/g, " ").replace(/[^A-Za-z0-9\s#'\-.]/g, "").replace(/\s+/g, " ").replace(/[A-Za-z][^\s-]*/g, (word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase());
    }
// Turns a raw db/backend field key (e.g. "opening_date") into a readable
// column name ("Opening Date") for any validation-error/hint display -
// shared so every such listing (Review Error Listings, Data Quality) shows
// the same formatted name instead of the literal stored key.
function formatFieldLabel(value) {
      return String(value || "").replace(/[_-]+/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
    }
function renderSimpleTable(targetId, columns, rows) {
      const target = el(targetId);
      const visibleRows = rows.length ? rows : [Object.fromEntries(columns.map((column) => {
        const label = String(column.label || column.key || "").toLowerCase();
        const value = /count|number|store|location|state|city|zip|population|income|age|share|covered/.test(label) ? 0 : "";
        return [column.key, value];
      }))];
      if (!rows.length) {
        target.innerHTML = `<table><thead><tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr></thead><tbody>${visibleRows.map((row) => `<tr>${columns.map((column) => {
          if (column.key === "pct") return '<td>0%</td>';
          const value = column.format ? column.format(row[column.key], row) : row[column.key];
          return `<td>${column.html ? value : escapeHtml(value)}</td>`;
        }).join("")}</tr>`).join("")}</tbody></table>`;
        return;
      }
      // Every table paginates once it is long enough to need it. Before this
      // only the market-gaps table had a pager; everything else rendered
      // every row (or a silent .slice(0, 10) that hid the rest with no way
      // to reach it). State is per-target so two tables cannot fight.
      const page = simpleTablePages.get(targetId) || 0;
      const pageCount = Math.ceil(visibleRows.length / SIMPLE_TABLE_PAGE_SIZE);
      const safePage = Math.min(Math.max(page, 0), Math.max(pageCount - 1, 0));
      simpleTablePages.set(targetId, safePage);
      const pageRows = pageCount > 1
        ? visibleRows.slice(safePage * SIMPLE_TABLE_PAGE_SIZE, (safePage + 1) * SIMPLE_TABLE_PAGE_SIZE)
        : visibleRows;
      const tableHtml = `<table><thead><tr>${columns.map((column) => `<th>${escapeHtml(column.label)}</th>`).join("")}</tr></thead><tbody>${pageRows.map((row) => `<tr>${columns.map((column) => {
        const value = column.format ? column.format(row[column.key], row) : row[column.key];
        return `<td>${column.html ? value : escapeHtml(value)}</td>`;
      }).join("")}</tr>`).join("")}</tbody></table>`;
      const pager = pageCount > 1
        ? `<div class="simple-table-pager" style="display:flex; justify-content:center; align-items:center; gap:8px; margin-top:10px;">
             <button type="button" class="secondary" data-simple-page="prev" data-target="${escapeHtml(targetId)}"${safePage === 0 ? " disabled" : ""}>Previous</button>
             <span style="font-size:12px; color:var(--muted);">Page ${safePage + 1} of ${pageCount} &middot; ${visibleRows.length.toLocaleString()} rows</span>
             <button type="button" class="secondary" data-simple-page="next" data-target="${escapeHtml(targetId)}"${safePage >= pageCount - 1 ? " disabled" : ""}>Next</button>
           </div>`
        : "";
      target.innerHTML = tableHtml + pager;
      target.dataset.simpleTableColumns = "1";
      simpleTableData.set(targetId, { columns, rows });
    }

// Paging state and the last dataset per table, so a page change can re-render
// without refetching. Module scope: renderSimpleTable is called repeatedly.
const SIMPLE_TABLE_PAGE_SIZE = 10;
const simpleTablePages = new Map();
const simpleTableData = new Map();

// One delegated listener for every simple table's pager.
document.addEventListener("click", (event) => {
      const button = event.target?.closest?.("button[data-simple-page]");
      if (!button) return;
      event.preventDefault();
      const targetId = button.dataset.target;
      const stored = simpleTableData.get(targetId);
      if (!stored) return;
      const current = simpleTablePages.get(targetId) || 0;
      simpleTablePages.set(targetId, button.dataset.simplePage === "next" ? current + 1 : current - 1);
      renderSimpleTable(targetId, stored.columns, stored.rows);
    });

function flattenObject(value, prefix = "", output = {}) {
      if (value && typeof value === "object" && !Array.isArray(value)) {
        Object.entries(value).forEach(([key, child]) => {
          const path = prefix ? `${prefix}.${key}` : key;
          flattenObject(child, path, output);
        });
      } else {
        output[prefix] = value;
      }
      return output;
    }
function getByPath(row, path) {
      if (!path) return "";
      return path.split(".").reduce((current, part) => {
        if (current && typeof current === "object" && part in current) return current[part];
        return "";
      }, row);
    }
function setStatus(message, type = "", options = {}) {
      const target = el("status");
      if (!target) return;
      target.className = `status ${type}`.trim();
      target.textContent = message;
      if (["warn", "warning", "error"].includes(String(type).toLowerCase())) {
        const close = document.createElement("button");
        close.type = "button";
        close.className = "status-close";
        close.setAttribute("aria-label", "Dismiss message");
        close.textContent = "×";
        close.addEventListener("click", () => {
          target.className = "status hidden";
          target.textContent = "";
        });
        target.appendChild(close);
        if (options.retry) {
          const retry = document.createElement("button");
          retry.type = "button";
          retry.className = "status-retry";
          retry.textContent = "Reload source";
          retry.addEventListener("click", () => {
            if (typeof window.parseSource === "function") window.parseSource();
          });
          target.insertBefore(retry, close);
        }
      }
    }

function addStatusClose(target) {
      if (!target || target.querySelector(".status-close")) return;
      const close = document.createElement("button");
      close.type = "button";
      close.className = "status-close";
      close.setAttribute("aria-label", "Dismiss message");
      close.textContent = "×";
      close.addEventListener("click", () => {
        target.className = "status hidden";
        target.textContent = "";
      });
      target.appendChild(close);
    }

function showLoadingOverlay(message, onCancel, onHide) {
      if (activeAbortController) {
        try { activeAbortController.abort(); } catch (_) {}
      }
      activeAbortController = new AbortController();
      el("loadingOverlayMessage").innerHTML = busyMarkup(message || "Working");
      el("loadingOverlaySub").textContent = "Processing records.";
      el("loadingOverlay").classList.remove("hidden");
      el("loadingCancelBtn").classList.toggle("hidden", typeof onCancel !== "function");
      el("loadingCancelBtn").onclick = () => {
        if (typeof onCancel !== "function") return;
        if (activeAbortController) {
          activeAbortController.abort();
          activeAbortController = null;
        }
        hideLoadingOverlay();
        if (typeof onCancel === "function") onCancel();
        setStatus("Cancelled. No changes.", "warn");
      };
      // Distinct from Cancel - this doesn't abort anything, it just lets the
      // caller (setProgress(), for a save already in flight) suppress
      // further redraws until the operation finishes on its own.
      el("loadingHideBtn").classList.toggle("hidden", typeof onHide !== "function");
      el("loadingHideBtn").onclick = () => {
        hideLoadingOverlay();
        if (typeof onHide === "function") onHide();
      };
    }
function updateLoadingOverlay(message, detail = "") {
      el("loadingOverlayMessage").innerHTML = busyMarkup(message || "Working");
      el("loadingOverlaySub").textContent = detail || "Processing records.";
    }
function hideLoadingOverlay() {
      el("loadingOverlay").classList.add("hidden");
      el("loadingCancelBtn").classList.remove("hidden");
      el("loadingHideBtn").classList.add("hidden");
      activeAbortController = null;
    }
// Set by the save flow (mapper.js) when the user clicks "Hide - notify me
// when done" on the loading overlay - suppresses further progress redraws
// (the save keeps running regardless; this only stops re-showing UI the
// user explicitly dismissed) until the next fresh save resets it.
let saveProgressHiddenByUser = false;
function setProgress(percent, message) {
      if (saveProgressHiddenByUser) return;
      const boundedPercent = Math.max(0, Math.min(100, percent));
      el("saveProgress").classList.remove("hidden");
      el("saveProgress").setAttribute("aria-busy", "true");
      el("progressFill").style.width = `${boundedPercent}%`;
      el("progressValue").textContent = `${boundedPercent}%`;
      el("progressMessage").textContent = message;
      showLoadingOverlay(`${message} (${boundedPercent}%)`, undefined, () => {
        saveProgressHiddenByUser = true;
        el("saveProgress").classList.add("hidden");
        el("saveProgress").setAttribute("aria-busy", "false");
        if (typeof showBackgroundSaveNotice === "function") showBackgroundSaveNotice();
        // Hiding the progress means "let this finish in the background and
        // give me my workspace back" - so return the mapper to the pre-parse
        // 40/60 layout, ready for a new parse. Without this the dismissed
        // save left the post-parse mapping workspace on screen with no way
        // to start another source. The save itself keeps running: it works
        // from data captured before this point, not from mapper state.
        if (typeof resetMapping === "function") resetMapping();
      });
    }
function hideProgress() {
      saveProgressHiddenByUser = false;
      el("saveProgress").classList.add("hidden");
      el("saveProgress").setAttribute("aria-busy", "false");
      hideLoadingOverlay();
      if (typeof clearBackgroundSaveNotice === "function") clearBackgroundSaveNotice();
    }
// Themed replacements for window.alert / window.confirm. The native ones
// ignore the app theme entirely and cannot be styled, so they looked like a
// different product every time they appeared. Both degrade to the native
// call only if the dialog element is missing (e.g. a page that does not
// include the shell markup).
// tone: "ok" (default) | "warn" | "error" | "info". It only changes the icon
// and its colour - the shell stays the one Birdeye dialog.
function showAppNotice(message, title = "Done", tone = "ok") {
      const dialog = el("appNoticeDialog");
      if (!dialog || typeof dialog.showModal !== "function") { window.alert(message); return; }
      const icons = { ok: "\u2713", warn: "!", error: "\u2715", info: "i" };
      dialog.classList.remove("tone-warn", "tone-error", "tone-info");
      if (tone && tone !== "ok") dialog.classList.add(`tone-${tone}`);
      const icon = el("appNoticeIcon");
      if (icon) icon.textContent = icons[tone] || icons.ok;
      el("appNoticeTitle").textContent = title;
      el("appNoticeMessage").textContent = message;
      const ok = el("appNoticeOk");
      if (ok && !ok.dataset.bound) {
        ok.dataset.bound = "1";
        ok.addEventListener("click", () => dialog.close());
      }
      dialog.showModal();
    }
function showAppConfirm(message, title = "Please confirm") {
      const dialog = el("appConfirmDialog");
      if (!dialog || typeof dialog.showModal !== "function") return Promise.resolve(window.confirm(message));
      el("appConfirmTitle").textContent = title;
      el("appConfirmMessage").textContent = message;
      return new Promise((resolve) => {
        const finish = (answer) => {
          el("appConfirmYes").removeEventListener("click", onYes);
          el("appConfirmNo").removeEventListener("click", onNo);
          dialog.close();
          resolve(answer);
        };
        const onYes = () => finish(true);
        const onNo = () => finish(false);
        el("appConfirmYes").addEventListener("click", onYes);
        el("appConfirmNo").addEventListener("click", onNo);
        dialog.showModal();
      });
    }

function busyMarkup(label = "Loading") {
      // Strips BOTH "..." and the single-glyph ellipsis. The spinner is the
      // app's one progress signal - trailing dots next to a spinner say the
      // same thing twice, and on their own they say it worse.
      const cleanLabel = String(label).replace(/(\.\.\.+|\u2026)\s*$/, "").trim();
      return `<span class="busy-label">${escapeHtml(cleanLabel)} <span class="inline-spinner"></span></span>`;
    }
function setButtonBusy(button, label = "Loading") {
      if (!button) return "";
      const previous = button.innerHTML;
      button.disabled = true;
      button.innerHTML = busyMarkup(label);
      return previous;
    }
function clearButtonBusy(button, previousHtml) {
      if (!button) return;
      button.disabled = false;
      if (previousHtml !== undefined) button.innerHTML = previousHtml;
    }

function switchView(viewId, isBootRestore = false) {
      if (!viewId) viewId = "mapperView";
      try {
        sessionStorage.setItem("activeTab", viewId);
        const urlParams = new URLSearchParams(window.location.search);
        urlParams.set("view", viewId);
        const nextUrl = `${window.location.pathname}?${urlParams.toString()}`;
        history.replaceState(null, "", nextUrl);
      } catch (e) {}
      // The mapper is reused as the template EDITOR. When it was opened from
      // Template Library > Review, the work is still "template library" work,
      // so the top nav must keep showing Template Library rather than jumping
      // the highlight to Mapping.
      const highlightViewId = (viewId === "mapperView" && el("mapperView")?.classList.contains("template-edit-mode"))
        ? "templateLibraryView"
        : viewId;
      document.querySelectorAll("[data-view]").forEach((button) => button.classList.toggle("active", button.dataset.view === highlightViewId));
      ["mapperView", "reportingView", "reviewView", "templateLibraryView"].forEach((id) => el(id).classList.toggle("hidden", id !== viewId));
      el("appShell").querySelector("header").classList.toggle("reporting-active", viewId === "reportingView");
      // Reset Fields Mapping only makes sense while actually on the Mapper
      // tab - it was previously kept visible everywhere as a deliberate
      // simplification, but the user explicitly asked for it to be
      // scoped back to Mapper only.
      el("resetMappingBtn")?.classList.toggle("hidden", viewId !== "mapperView");
      // Reset Fields Mapping's grid slot must not stay reserved as an
      // empty gap once the button itself is hidden outside Mapper - see
      // .header-data-actions.reset-mapping-hidden.
      document.querySelector(".header-data-actions")?.classList.toggle("reset-mapping-hidden", viewId !== "mapperView");
      if (viewId === "mapperView" && typeof renderMappings === "function") renderMappings();
      if (viewId === "reportingView" && !reportLoaded) loadReporting();
      // A genuine nav click into Reporting always lands on the first inner
      // tab; a page refresh while already on Reporting (isBootRestore) must
      // keep whatever inner tab was active - reporting-tabs.js's own init()
      // already restores that from sessionStorage in that case.
      if (viewId === "reportingView" && !isBootRestore) {
        try { sessionStorage.setItem("reportingInnerTab", "location"); } catch (_) {}
        if (typeof window.reportingResetToLocationTab === "function") window.reportingResetToLocationTab();
      }
      // loadAppData() (this file) already ran loadTemplateFilters() once at
      // boot, for every view, so templateLibraryLoaded is already true by
      // the time a user's first real nav click lands here - the
      // !templateLibraryLoaded guard below (kept for the template LISTING,
      // which is the expensive, paginated fetch worth caching) was also
      // gating the FILTERS refetch, so #templateBusinessFilter's brand
      // option list was permanently frozen at its boot-time snapshot for
      // the rest of the session: a brand created afterward in Mapper never
      // appeared there without a full page reload (confirmed live,
      // 2026-09-10). loadTemplateFilters() is two lightweight GETs
      // (brands + source types), cheap enough to run on every visit to this
      // tab; only the template listing itself stays behind the cache guard.
      if (viewId === "templateLibraryView") {
        loadTemplateFilters();
        if (!templateLibraryLoaded) loadTemplateLibrary();
      }
      if (viewId === "reviewView") {
        loadRejectedRecords();
        refreshReviewCount();
        if (typeof loadErrorBrandBreakdown === "function") loadErrorBrandBreakdown();
        if (typeof refreshFixCountersOnce === "function") refreshFixCountersOnce();
        // Needs Review is a separate failure population (see codex.md) with
        // its own sub-tab inside this view. A genuine nav click always lands
        // back on Review Error Listings, same convention Reporting uses for
        // its own inner tabs; only a page refresh while already here
        // (isBootRestore) restores whichever sub-tab was open.
        if (typeof restoreReviewInnerTab === "function") restoreReviewInnerTab(isBootRestore);
      }
    }

async function testReadiness() {
      const button = el("testReadinessBtn");
      const previousButton = setButtonBusy(button, "Testing Readiness");
      try {
        await refreshHeaderReadiness(true);
      } finally {
        clearButtonBusy(button, previousButton);
      }
    }
async function fetchReadinessPing() {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), loginReadinessTimeoutMs);
      try {
        return await fetch("/api/ping", { signal: controller.signal });
      } finally {
        clearTimeout(timeout);
      }
    }
function setHeaderReadiness(message, type = "") {
      const target = el("headerReadinessStatus");
      if (!target) return;
      target.className = `header-readiness ${type}`.trim();
      target.textContent = message;
    }
function setReadinessButtonDisabled(disabled) {
      const button = el("testReadinessBtn");
      if (!button) return;
      button.disabled = Boolean(disabled);
      button.title = disabled ? "ZIP reference data is already loaded." : "";
    }
function updateLoginButtonReferenceState() {
      const loginButton = el("loginBtn");
      if (!loginButton) return;
      loginButton.className = `reference-login-button ${appReady ? "ready" : "warn"}`;
      loginButton.disabled = false;
    }
async function refreshHeaderReadiness(force = false) {
      if (readinessCheckInFlight && !force) return readinessCheckInFlight;
      setHeaderReadiness("Checking ZIPs", "warn");
      setReadinessButtonDisabled(true);
      readinessCheckInFlight = (async () => {
        try {
          const response = await fetch(`/api/prepare${force ? "?force=1" : ""}`);
          const result = await response.json();
          if (!response.ok) throw new Error(result.error || "ZIP setup needs attention.");
          const ready = result.status === "ready" || result.loaded === true;
          appReady = ready;
          updateLoginButtonReferenceState();
          setHeaderReadiness(ready ? "ZIPs loaded" : "Loading US ZIPs", ready ? "ok" : "warn");
          setReadinessButtonDisabled(ready);
          return result;
        } catch (error) {
          appReady = false;
          updateLoginButtonReferenceState();
          setHeaderReadiness("ZIPs need attention", "error");
          setReadinessButtonDisabled(false);
          return null;
        } finally {
          readinessCheckInFlight = null;
        }
      })();
      return readinessCheckInFlight;
    }
async function runReadinessCheck(target) {
      if (!target) {
        await refreshHeaderReadiness(true);
        return;
      }
      target.className = "status";
      target.textContent = "Checking readiness";
      try {
        const response = await fetchReadinessPing();
        const result = await response.json();
        if (!response.ok) throw new Error("Setup is still finishing.");
        appReady = true;
        updateLoginButtonReferenceState();
        target.className = "status ok";
        target.textContent = "Storage ready.";
      } catch (error) {
        appReady = false;
        updateLoginButtonReferenceState();
        target.className = "status error";
        target.textContent = "Setup is still finishing.";
        addStatusClose(target);
      }
    }

async function login() {
      const status = el("loginStatus");
      status.className = "status hidden";
      try {
        const response = await fetch("/api/login", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ username: el("loginUser").value.trim(), password: el("loginPassword").value })
        });
        const result = await response.json();
        if (!response.ok || !result.authenticated) throw new Error(result.error || "Invalid username or password.");
        if (el("rememberLogin").checked) localStorage.setItem("mapper_login_remembered", "true");
        else localStorage.removeItem("mapper_login_remembered");
        sessionStorage.setItem(loginSessionStorageKey, "true");
        sessionStorage.setItem(mappingSessionStorageKey, newSessionId());
        sessionStorage.removeItem(draftStorageKey);
        sessionStorage.removeItem("activeTab");
        window.location.replace("/app?view=mapperView");
      } catch (error) {
        status.className = "status error";
        status.textContent = productSafeError(error.message, "Invalid username or password.");
      }
    }
async function loadAppData() {
      if (appDataLoaded) return;
      appDataLoaded = true;
      // Paint the remembered brands FIRST, synchronously. loadBrands() is a
      // network round trip and attachSearchableSelect() cannot create the
      // search box until options exist, so the brand controls were simply
      // absent for the first few seconds of a cold start. The real list
      // overwrites this as soon as it lands.
      if (typeof paintRememberedBrands === "function") {
        try { paintRememberedBrands(); } catch (_) {}
      }
      // Create the search box right now, synchronously, using whatever the
      // select currently holds - the remembered list just painted above, or
      // (on a first-ever visit, nothing remembered) just its 2 static
      // options. `hasMore: true` is what lets this fire before real data
      // exists at all: the user can start typing immediately, and
      // attachSearchableSelect()'s later calls (once loadBrands() below
      // resolves) refresh the option list under it and repaint any
      // already-typed query against the real data.
      if (typeof attachSearchableSelect === "function") {
        attachSearchableSelect("brandSelect", { threshold: 15, minChars: 1, hasMore: true });
        attachSearchableSelect("parserBusinessSelect", { threshold: 15, minChars: 1, hasMore: true });
      }
      await Promise.allSettled([loadFieldRegistry(), loadBrands(), loadTemplateFilters()]);
      // Apply the initial mapper layout (and enable the brand-dependent
      // "Edit a brand" radio/buttons) as soon as brands are in, rather than
      // queuing it behind the unrelated Template Library fetch below - that
      // queuing was why "Edit a brand" could take a visibly long time to
      // become available even though loadBrands() itself was already done.
      if (typeof renderMappings === "function") renderMappings();
      if (typeof updateOutput === "function") updateOutput();
      // Template records are intentionally fetched only after authentication
      // and app initialization, so the library tab opens instantly later.
      if (typeof loadTemplateLibrary === "function") await loadTemplateLibrary();
}

function enableSortableTable(table) {
  if (!table) return;
  table.querySelectorAll("th[data-sort-key]").forEach((header) => {
    if (header.dataset.sortBound === "true") return;
    header.dataset.sortBound = "true";
    header.classList.add("sortable-header");
    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.setAttribute("aria-sort", "none");
    const indicator = document.createElement("span");
    indicator.className = "sort-indicator";
    indicator.textContent = "↕";
    header.appendChild(indicator);
    const sort = () => {
      const ascending = header.dataset.sortDirection !== "asc";
      table.querySelectorAll("th[data-sort-key]").forEach((item) => {
        item.dataset.sortDirection = "";
        item.setAttribute("aria-sort", "none");
        const icon = item.querySelector(".sort-indicator");
        if (icon) icon.textContent = "↕";
      });
      header.dataset.sortDirection = ascending ? "asc" : "desc";
      header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
      indicator.textContent = ascending ? "↑" : "↓";
      const rows = [...table.querySelectorAll("tbody tr")];
      const column = header.cellIndex;
      rows.sort((left, right) => {
        const a = left.cells[column]?.dataset.sortValue ?? left.cells[column]?.textContent.trim() ?? "";
        const b = right.cells[column]?.dataset.sortValue ?? right.cells[column]?.textContent.trim() ?? "";
        const numeric = header.dataset.sortType === "number";
        const comparison = numeric ? Number(a) - Number(b) : String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
        return (ascending ? 1 : -1) * comparison;
      });
      const body = table.querySelector("tbody");
      rows.forEach((row) => body.appendChild(row));
    };
    header.addEventListener("click", sort);
    header.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") { event.preventDefault(); sort(); }
    });
  });
}
function restoreRememberedLogin() {
      const remembered = localStorage.getItem("mapper_login_remembered") === "true";
      el("rememberLogin").checked = remembered;
    }
async function resetLoginSessionFromLaunch() {
      try {
        const response = await fetch("/api/session", { cache: "no-store" });
        const result = await response.json();
        if (!response.ok || !result.server_launch_id) throw new Error("Session check failed.");
        const previousLaunchId = sessionStorage.getItem(serverLaunchStorageKey);
        const currentLaunchId = String(result.server_launch_id);
        if (previousLaunchId && previousLaunchId !== currentLaunchId) {
          sessionStorage.removeItem(loginSessionStorageKey);
          sessionStorage.removeItem(mappingSessionStorageKey);
          sessionStorage.removeItem(draftStorageKey);
          sessionStorage.setItem(serverLaunchStorageKey, currentLaunchId);
          const currentSearch = window.location.search || "";
          window.location.replace("/login" + currentSearch);
          return;
        }
        sessionStorage.setItem(serverLaunchStorageKey, currentLaunchId);
      } catch (error) {
        sessionStorage.removeItem(loginSessionStorageKey);
        sessionStorage.removeItem(mappingSessionStorageKey);
        sessionStorage.removeItem(draftStorageKey);
        const currentSearch = window.location.search || "";
        window.location.replace("/login" + currentSearch);
        return;
      }
      if (sessionStorage.getItem(loginSessionStorageKey) !== "true") {
        const currentSearch = window.location.search || "";
        window.location.replace("/login" + currentSearch);
        return;
      }
      el("loginScreen")?.classList.add("hidden");
      el("appShell")?.classList.remove("hidden");
    }
async function prepareReferenceData() {
      const loginButton = el("loginBtn");
      const status = el("loginReadinessStatus");
      loginButton.className = "reference-login-button warn";
      loginButton.disabled = false;
      if (status) {
        status.className = "status";
        status.textContent = "Preparing ZIP reference data";
      }
      try {
        const response = await fetch("/api/prepare");
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "ZIP reference data could not be prepared.");
        appReady = true;
        updateLoginButtonReferenceState();
        if (status) {
          status.className = "status ok";
          status.textContent = "ZIP reference data ready.";
        }
        return result;
      } catch (error) {
        appReady = false;
        updateLoginButtonReferenceState();
        if (status) {
          status.className = "status error";
          status.textContent = productSafeError(error.message, "ZIP reference data needs attention.");
        }
        return null;
      }
    }

function logout() {
      localStorage.removeItem("mapper_login_remembered");
      sessionStorage.removeItem(loginSessionStorageKey);
      sessionStorage.removeItem(mappingSessionStorageKey);
      sessionStorage.removeItem(draftStorageKey);
      window.location.replace("/login");
    }

// The app header is position:sticky at the top of every view, so anything
// else that pins itself has to start below it - the reporting filter rail
// (.report-filter-rail, both reporting tabs) does exactly that. The header's
// height is not a constant: .header-actions wraps to a second line on narrow
// windows and the brand logo loads late, so a hard-coded offset either tucks
// the rail's first filter under the header or leaves a gap under it. Publish
// the measured height as a CSS custom property and let the stylesheet do the
// arithmetic (top / max-height) from it. Stylesheets read it as
// var(--app-header-h, 71px), so nothing breaks before this first runs.
function syncAppHeaderOffset() {
      const header = document.querySelector("header");
      if (!header) return;
      const height = Math.round(header.getBoundingClientRect().height);
      // A hidden or not-yet-laid-out header measures 0; keeping the previous
      // (or fallback) value is better than pinning the rail to the very top.
      if (height > 0) document.documentElement.style.setProperty("--app-header-h", `${height}px`);
    }
if (typeof document !== "undefined" && !window.__appHeaderOffsetTracked) {
      window.__appHeaderOffsetTracked = true;
      syncAppHeaderOffset();
      window.addEventListener("resize", syncAppHeaderOffset);
      // The header also changes height without the window changing size: the
      // logo image finishes loading, a long brand name pushes the account
      // actions onto their own row. ResizeObserver catches those; the resize
      // listener above is the fallback where it is unavailable.
      try {
        const header = document.querySelector("header");
        if (header && typeof ResizeObserver === "function") new ResizeObserver(syncAppHeaderOffset).observe(header);
      } catch (_) {}
    }
