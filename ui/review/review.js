/**
 * Review Error Listings UI Subpackage Module.
 * 
 * Manages rejected-record search, error listing details, and the interactive edit/retry modal.
 * Communicates directly with backend endpoints (`/api/rejected`, `/api/error-listings/count`, `/api/reprocess`)
 * routed to `whitespace_tool.review`.
 */

let currentEditingRecord = null;
let loadRejectedRecordsPromise = null;
let reviewBrandNames = {};
const ERROR_BRAND_COLORS = ["#2f6f6a", "#c26a3d", "#4c6ef5", "#b5559e", "#3c9a5f", "#c0392b", "#8a6d3b", "#6741d9", "#128fb0", "#9c6b1f"];

function _donutSvg(slices, total, size = 180) {
  const radius = size / 2;
  const inner = radius * 0.58;
  const cx = radius;
  const cy = radius;
  if (!total) return "";
  const nonZero = slices.filter((s) => s.value > 0);
  if (nonZero.length === 1) {
    const pct = Math.round(nonZero[0].value / total * 100);
    return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="One brand accounts for all error listings">
      <circle cx="${cx}" cy="${cy}" r="${(radius + inner) / 2}" fill="none" stroke="${nonZero[0].color}" stroke-width="${radius - inner}">
        <title>${escapeHtml(nonZero[0].label || 'Brand')}\n${nonZero[0].value} records\n${pct}% of errors</title>
      </circle>
      <text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="18" font-weight="700" fill="#1f2937">${total}</text>
      <text x="${cx}" y="${cy + 14}" text-anchor="middle" font-size="9" fill="#6b7280">total</text>
    </svg>`;
  }
  let angle = -Math.PI / 2;
  const arcs = slices.map((slice) => {
    if (slice.value <= 0) return "";
    const sweep = (slice.value / total) * Math.PI * 2;
    const a0 = angle;
    const a1 = angle + sweep;
    angle = a1;
    const large = sweep > Math.PI ? 1 : 0;
    const x0 = cx + radius * Math.cos(a0), y0 = cy + radius * Math.sin(a0);
    const x1 = cx + radius * Math.cos(a1), y1 = cy + radius * Math.sin(a1);
    const xi1 = cx + inner * Math.cos(a1), yi1 = cy + inner * Math.sin(a1);
    const xi0 = cx + inner * Math.cos(a0), yi0 = cy + inner * Math.sin(a0);
    const pct = Math.round(slice.value / total * 100);
    return `<path d="M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${radius} ${radius} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} L ${xi1.toFixed(2)} ${yi1.toFixed(2)} A ${inner} ${inner} 0 ${large} 0 ${xi0.toFixed(2)} ${yi0.toFixed(2)} Z" fill="${slice.color}"><title>${escapeHtml(slice.label || 'Brand')}\n${slice.value} records\n${pct}% of errors</title></path>`;
  }).join("");
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="Error listings by brand">
    ${arcs}
    <text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="18" font-weight="700" fill="#1f2937">${total}</text>
    <text x="${cx}" y="${cy + 14}" text-anchor="middle" font-size="9" fill="#6b7280">total</text>
  </svg>`;
}

async function loadErrorBrandBreakdown() {
  const container = el("reviewBrandBreakdown");
  if (!container) return;
  try {
    const response = await fetch("/api/error-listings/by-brand");
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load brand breakdown.");
    const brands = Array.isArray(result.brands) ? result.brands.filter((b) => b.count > 0) : [];
    const total = result.total || brands.reduce((sum, b) => sum + b.count, 0);
    if (!brands.length) {
      container.style.display = "none";
      return;
    }
    const withColor = brands.map((b, i) => ({ ...b, color: ERROR_BRAND_COLORS[i % ERROR_BRAND_COLORS.length] }));
    el("reviewBrandChart").innerHTML = _donutSvg(withColor.map((b) => ({ value: b.count, color: b.color, label: b.brand || b.business_id })), total);
    el("reviewBrandBreakdownTotal").textContent = `${total} across ${brands.length} brand${brands.length === 1 ? "" : "s"}`;
    el("reviewBrandTable").innerHTML = `<table style="width:100%; border-collapse: collapse; font-size: 12px;"><thead><tr>
        <th style="text-align:left; padding:4px 8px; border-bottom:1px solid var(--line);">Brand</th>
        <th style="text-align:right; padding:4px 8px; border-bottom:1px solid var(--line);">Errors</th>
        <th style="text-align:right; padding:4px 8px; border-bottom:1px solid var(--line);">Share</th>
      </tr></thead><tbody>${withColor.map((b) => `<tr>
        <td style="padding:4px 8px;"><span style="display:inline-block; width:10px; height:10px; border-radius:2px; background:${b.color}; margin-right:6px; vertical-align:middle;"></span>${escapeHtml(b.brand || b.business_id)}</td>
        <td style="padding:4px 8px; text-align:right; font-variant-numeric: tabular-nums;">${b.count}</td>
        <td style="padding:4px 8px; text-align:right; color: var(--muted); font-variant-numeric: tabular-nums;">${total ? Math.round(b.count / total * 100) : 0}%</td>
      </tr>`).join("")}</tbody></table>`;
    container.style.display = "block";
  } catch (error) {
    container.style.display = "none";
  }
}

async function loadReviewBrandFilter() {
  const select = el("reviewBrandFilter");
  if (!select || select.options.length > 1) return;
  try {
    const res = await fetch("/api/brands?search=");
    const data = await res.json();
    if (res.ok && Array.isArray(data.brands)) {
      reviewBrandNames = Object.fromEntries(data.brands.map(b => [b.business_id, b.name]));
      const currentVal = select.value;
      select.innerHTML = '<option value="">All Brands</option>' + data.brands.map(b => `<option value="${escapeHtml(b.business_id)}">${escapeHtml(b.name)}</option>`).join("");
      select.value = currentVal || "";
    }
  } catch (err) {
    // Soft fail
  }
}


function loadRejectedRecords() {
  if (loadRejectedRecordsPromise) return loadRejectedRecordsPromise;
  loadRejectedRecordsPromise = _loadRejectedRecordsOnce().finally(() => {
    loadRejectedRecordsPromise = null;
  });
  return loadRejectedRecordsPromise;
}

async function _loadRejectedRecordsOnce() {
  const eventId = el("reviewEventId") ? el("reviewEventId").value.trim() : "";
  const target = el("reviewResults");
  const searchBtn = el("reviewSearchBtn");
  if (!target) return;
  const originalSearchBtnHtml = searchBtn ? searchBtn.innerHTML : "Search Records";

  if (searchBtn) {
    searchBtn.disabled = true;
    searchBtn.innerHTML = `<span style="display: inline-flex; align-items: center; gap: 6px;"><span class="inline-spinner" style="display: inline-block; width: 12px; height: 12px; border: 2px solid rgba(255,255,255,0.3); border-top-color: #ffffff; border-radius: 50%; animation: spinCircle 0.8s linear infinite;"></span> Searching...</span>`;
  }

  target.className = "status";
  target.textContent = "Loading error listings...";
  try {
    const response = await fetch(`/api/rejected?event_id=${encodeURIComponent(eventId)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Could not load review records.");
    if (!result.records || !result.records.length) {
      target.textContent = "No error listings found for this event.";
      return;
    }
    target.className = "";
    target.innerHTML = `<table><thead><tr><th>Event</th><th>Row</th><th>Issues & Hints</th><th>Source Record</th><th>Action</th></tr></thead><tbody>${result.records.map((record) => {
      let errs = record.errors;
      if (typeof errs === 'string') {
        try { errs = JSON.parse(errs); } catch (e) { errs = []; }
      }
      const hintsHtml = Array.isArray(errs) ? errs.map(e => `
        <div style="background: #fff1f0; border: 1px solid #ffa39e; border-radius: 4px; padding: 4px 8px; margin-bottom: 4px; font-size: 12px; color: #cf1322;">
          <strong>⚠️ ${escapeHtml(e.field || 'Field')}</strong>: ${escapeHtml(e.hint || e.reason || 'Invalid value')} <em>(${escapeHtml(e.value || 'empty')})</em>
        </div>
      `).join('') : escapeHtml(JSON.stringify(record.errors));

      return `<tr>
        <td style="font-family: monospace; font-size: 11px;">${escapeHtml(record.event_id)}</td>
        <td><strong>#${escapeHtml(record.row_number)}</strong></td>
        <td style="max-width: 320px;">${hintsHtml}</td>
        <td style="max-width: 250px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: monospace; font-size: 11px;">${escapeHtml(JSON.stringify(record.raw_record))}</td>
        <td class="review-row-actions">
          <button type="button" data-open-edit="${escapeHtml(record.row_number)}" data-event="${escapeHtml(record.event_id)}">✏️ Edit &amp; Retry Fix</button>
        </td>
      </tr>`;
    }).join("")}</tbody></table>`;
    target.querySelectorAll("button[data-open-edit]").forEach((button) => {
      button.addEventListener("click", () => {
        const rec = result.records.find(r => r.event_id === button.dataset.event && String(r.row_number) === button.dataset.openEdit);
        if (rec) openEditRecordModal(rec);
      });
    });
  } catch (error) {
    target.className = "status error";
    target.textContent = productSafeError(error.message, "Could not load review records.");
  } finally {
    if (searchBtn) {
      searchBtn.disabled = false;
      searchBtn.innerHTML = originalSearchBtnHtml;
    }
  }
}

function getNestedRawValue(row, path) {
  if (!path) return "";
  let current = row;
  for (const part of path.split(".")) {
    if (current && typeof current === "object") current = current[part];
    else return "";
  }
  return current !== null && current !== undefined ? current : "";
}

async function openEditRecordModal(record) {
  currentEditingRecord = record;
  let rawObj = record.raw_record;
  if (typeof rawObj === 'string') {
    try { rawObj = JSON.parse(rawObj); } catch (e) { rawObj = {}; }
  }
  let errs = record.errors;
  if (typeof errs === 'string') {
    try { errs = JSON.parse(errs); } catch (e) { errs = []; }
  }

  const hintsEl = el("editRecordHints");
  if (hintsEl) {
    hintsEl.innerHTML = `<strong>Flagged Issues for Row #${record.row_number}:</strong><ul style="margin: 6px 0 0 18px; padding: 0;">` +
      (Array.isArray(errs) ? errs.map(e => `<li><strong>${escapeHtml(e.field)}</strong>: ${escapeHtml(e.hint || e.reason)}</li>`).join('') : '<li>Issue found.</li>') +
      `</ul>`;
  }

  let savedBrandsList = [];
  try {
    savedBrandsList = JSON.parse(el("brandSelect")?.dataset.brands || "[]");
  } catch (e) {
    savedBrandsList = [];
  }
  if (!savedBrandsList.length) {
    try {
      const res = await fetch("/api/brands?search=");
      const data = await res.json();
      if (res.ok && Array.isArray(data.brands)) {
        savedBrandsList = data.brands;
        if (el("brandSelect")) el("brandSelect").dataset.brands = JSON.stringify(savedBrandsList);
      }
    } catch (err) {
      // fallback
    }
  }

  const activeMapper = typeof getMapper === "function" ? getMapper() : { fields: {} };
  const mapperFields = activeMapper.fields || {};

  const rawBrandVal = String(getNestedRawValue(rawObj, mapperFields.brand || "brand") || record.brand || activeMapper.brand || "").trim();
  const rawNameVal = String(getNestedRawValue(rawObj, mapperFields.name || "name") || "").trim();
  const targetBusinessId = String(record.business_id || activeMapper.business_id || "").trim();

  let matchedBrand = savedBrandsList.find(b => targetBusinessId && b.business_id === targetBusinessId);
  if (!matchedBrand && rawBrandVal) {
    matchedBrand = savedBrandsList.find(b => b.name && b.name.toLowerCase() === rawBrandVal.toLowerCase());
  }
  if (!matchedBrand && rawNameVal) {
    matchedBrand = savedBrandsList.find(b => b.name && (rawNameVal.toLowerCase().includes(b.name.toLowerCase()) || b.name.toLowerCase().includes(rawNameVal.toLowerCase())));
  }

  const LOCATION_FIELD_SPECS = {
    brand: { label: "Business / Brand Name", path: mapperFields.brand || "brand", note: "Select the business/brand to associate with this record.", required: true },
    name: { label: "Location Name", path: mapperFields.name || "name", note: "Required.", required: true },
    address: { label: "Address", path: mapperFields.address || "address", note: "Required.", required: true },
    city: { label: "City", path: mapperFields.city || "city", note: "Required.", required: true },
    state: { label: "State", path: mapperFields.state || "state", note: "Required (2-letter code or state name).", required: true },
    postal_code: { label: "ZIP Code", path: mapperFields.postal_code || "postal_code", note: "Required (5-digit US ZIP code).", required: true },
    latitude: { label: "Latitude", path: mapperFields.latitude || "latitude", note: "Decimal latitude coordinate (e.g. 40.7128).", required: false },
    longitude: { label: "Longitude", path: mapperFields.longitude || "longitude", note: "Decimal longitude coordinate (e.g. -74.0060).", required: false },
  };
  const renderedPaths = new Set();

  const requiredFieldHtml = ["brand", "name", "address", "city", "state", "postal_code", "latitude", "longitude"]
    .map((key) => {
      const { label, path, note, required } = LOCATION_FIELD_SPECS[key];
      renderedPaths.add(path);
      if (key === "brand") {
        const optionsHtml = ['<option value="">Select a saved business</option>']
          .concat(savedBrandsList.map(b => {
            const isSelected = matchedBrand ? b.business_id === matchedBrand.business_id : (b.name.toLowerCase() === rawBrandVal.toLowerCase());
            return `<option value="${escapeHtml(b.name)}" data-business-id="${escapeHtml(b.business_id)}" ${isSelected ? 'selected' : ''}>${escapeHtml(b.name)}</option>`;
          }))
          .join('');
        return `
    <div style="display: flex; flex-direction: column;">
      <label style="font-size: 12px; font-weight: 700; color: var(--ink); margin-bottom: 4px;">${escapeHtml(label)} <span style="font-weight: 400; color: ${required ? '#cf1322' : 'var(--muted)'};">(${escapeHtml(path)})${required ? ' *' : ''}</span></label>
      <select id="editRecordBrandSelect" data-raw-key="${escapeHtml(path)}" data-field-type="brand" style="padding: 6px; border: 1px solid var(--line); border-radius: 4px; font-size: 13px; background: #fff;">
        ${optionsHtml}
      </select>
      <span style="font-size: 11px; color: var(--muted, #6b7280); margin-top: 2px;">${escapeHtml(note)}</span>
    </div>
  `;
      }
      const rawVal = getNestedRawValue(rawObj, path);
      return `
    <div style="display: flex; flex-direction: column;">
      <label style="font-size: 12px; font-weight: 700; color: var(--ink); margin-bottom: 4px;">${escapeHtml(label)} <span style="font-weight: 400; color: ${required ? '#cf1322' : 'var(--muted)'};">(${escapeHtml(path)})${required ? ' *' : ''}</span></label>
      <input type="text" data-raw-key="${escapeHtml(path)}" data-field-type="${escapeHtml(key)}" value="${escapeHtml(rawVal !== null && rawVal !== undefined ? String(rawVal) : '')}" style="padding: 6px; border: 1px solid var(--line); border-radius: 4px; font-size: 13px;">
      <span style="font-size: 11px; color: var(--muted, #6b7280); margin-top: 2px;">${escapeHtml(note)}</span>
    </div>
  `;
    }).join('');

  const formEl = el("editRecordForm");
  if (formEl) {
    formEl.innerHTML = requiredFieldHtml + Object.entries(rawObj).filter(([key]) => !renderedPaths.has(key)).map(([key, val]) => {
      const isLat = key.toLowerCase().includes("lat");
      const isLon = key.toLowerCase().includes("lon") || key.toLowerCase().includes("lng");
      const isZip = key.toLowerCase().includes("zip") || key.toLowerCase().includes("postal");
      const fieldType = isLat ? "latitude" : (isLon ? "longitude" : (isZip ? "postal_code" : ""));
      return `
      <div style="display: flex; flex-direction: column;">
        <label style="font-size: 12px; font-weight: 700; color: var(--ink); margin-bottom: 4px;">${escapeHtml(key)}${isLat || isLon || isZip ? ` <span style="font-weight: 400; color: var(--muted); font-size: 11px;">(${fieldType})</span>` : ''}</label>
        <input type="text" data-raw-key="${escapeHtml(key)}" data-field-type="${escapeHtml(fieldType)}" value="${escapeHtml(val !== null && val !== undefined ? String(val) : '')}" style="padding: 6px; border: 1px solid var(--line); border-radius: 4px; font-size: 13px;">
      </div>
    `;
    }).join('');
  }

  const feedbackEl = el("editRecordFeedback");
  if (feedbackEl) {
    feedbackEl.style.display = "none";
    feedbackEl.textContent = "";
    feedbackEl.className = "action-feedback";
  }

  const cityVal = String(getNestedRawValue(rawObj, mapperFields.city || "city") || rawObj.city || rawObj.City || "").trim();
  const stateVal = String(getNestedRawValue(rawObj, mapperFields.state || "state") || rawObj.state || rawObj.State || "").trim();
  const zipVal = String(getNestedRawValue(rawObj, mapperFields.postal_code || "postal_code") || rawObj.zip || rawObj.postal_code || "").trim();
  const latVal = String(getNestedRawValue(rawObj, mapperFields.latitude || "latitude") || rawObj.latitude || "").trim();
  const lonVal = String(getNestedRawValue(rawObj, mapperFields.longitude || "longitude") || rawObj.longitude || "").trim();
  const needsZip = !zipVal || zipVal.length < 5;
  const needsLatLon = !latVal || !lonVal || isNaN(parseFloat(latVal)) || isNaN(parseFloat(lonVal));

  if (cityVal && (needsZip || needsLatLon) && formEl) {
    try {
      fetch(`/api/zips/search?q=${encodeURIComponent(cityVal)}&state=${encodeURIComponent(stateVal)}&limit=5`)
        .then(res => res.json())
        .then(data => {
          if (data && Array.isArray(data.zips) && data.zips.length > 0) {
            const suggestionBox = document.createElement("div");
            suggestionBox.id = "zipSuggestionsBox";
            suggestionBox.style.gridColumn = "1 / -1";
            suggestionBox.style.background = "#e6f7ff";
            suggestionBox.style.border = "1px solid #91d5ff";
            suggestionBox.style.borderRadius = "6px";
            suggestionBox.style.padding = "8px 12px";
            suggestionBox.style.fontSize = "12px";
            suggestionBox.style.color = "#0050b3";
            suggestionBox.style.marginBottom = "8px";

            const zipsListHtml = data.zips.slice(0, 4).map(z => `
              <button type="button" class="secondary" style="padding: 2px 8px; font-size: 11px; margin: 2px 4px 2px 0; border: 1px solid #91d5ff; background: #fff; cursor: pointer;"
                onclick="(function(){
                  const zipInput = document.querySelector('input[data-field-type=\\'postal_code\\']');
                  if (zipInput) zipInput.value = '${escapeHtml(z.zip_code)}';
                  const cityInput = document.querySelector('input[data-field-type=\\'city\\']');
                  if (cityInput && !cityInput.value) cityInput.value = '${escapeHtml(z.city_name || '')}';
                  const stateInput = document.querySelector('input[data-field-type=\\'state\\']');
                  if (stateInput && !stateInput.value) stateInput.value = '${escapeHtml(z.state_code || '')}';
                  const latInput = document.querySelector('input[data-field-type=\\'latitude\\']');
                  if (latInput && ${z.latitude !== null && z.latitude !== undefined}) latInput.value = '${z.latitude ?? ''}';
                  const lonInput = document.querySelector('input[data-field-type=\\'longitude\\']');
                  if (lonInput && ${z.longitude !== null && z.longitude !== undefined}) lonInput.value = '${z.longitude ?? ''}';
                })()">📍 ${escapeHtml(z.zip_code)} (${escapeHtml(z.city_name || cityVal)}, ${escapeHtml(z.state_code || stateVal)})</button>
            `).join('');

            suggestionBox.innerHTML = `<strong>💡 Suggested ZIP + coordinates for ${escapeHtml(cityVal)}:</strong> <div style="margin-top: 4px;">${zipsListHtml}</div><div style="margin-top: 4px; font-size: 11px; color: #0050b3;">Coordinates are that ZIP's approximate center, not an exact address - fine for a nearby fix, not a precise pin.</div>`;
            formEl.insertBefore(suggestionBox, formEl.firstChild);
          }
        })
        .catch(() => {});
    } catch (e) {}
  }

  if (formEl) {
    formEl.querySelectorAll("input, select").forEach(input => {
      input.addEventListener("input", () => {
        if (feedbackEl && feedbackEl.className.includes("error")) {
          feedbackEl.style.display = "none";
          feedbackEl.textContent = "";
        }
      });
      input.addEventListener("change", () => {
        if (feedbackEl && feedbackEl.className.includes("error")) {
          feedbackEl.style.display = "none";
          feedbackEl.textContent = "";
        }
      });
    });
  }

  const dialog = el("editRecordDialog");
  if (dialog && typeof dialog.showModal === "function") dialog.showModal();
}

async function refreshReviewCount() {
  const businessId = selectedBrand?.business_id || "";
  try {
    const response = await fetch(`/api/error-listings/count?business_id=${encodeURIComponent(businessId)}`);
    const result = await response.json();
    if (response.ok && el("reviewCount")) el("reviewCount").textContent = result.count;
  } catch (error) {
    if (el("reviewCount")) el("reviewCount").textContent = "0";
  }
}

