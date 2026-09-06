// Review Error Listings tab: rejected-record search and the edit/retry modal.

let currentEditingRecord = null;
let loadRejectedRecordsPromise = null;
// login-hotfix.js and integrations.html's own bootstrap script can each
// independently call switchView("reviewView") on the same page load (the
// hotfix script loads async, so ordering isn't guaranteed) - without this
// guard, two concurrent runs race on the Search button's "restore original
// html" step: whichever finishes last can restore the OTHER call's
// mid-spin snapshot, leaving the button stuck spinning even though
// #reviewResults already rendered real records from the call that won.
function loadRejectedRecords() {
      if (loadRejectedRecordsPromise) return loadRejectedRecordsPromise;
      loadRejectedRecordsPromise = _loadRejectedRecordsOnce().finally(() => {
        loadRejectedRecordsPromise = null;
      });
      return loadRejectedRecordsPromise;
    }
async function _loadRejectedRecordsOnce() {
      const eventId = el("reviewEventId").value.trim();
      const target = el("reviewResults");
      const searchBtn = el("reviewSearchBtn");
      const originalSearchBtnHtml = searchBtn ? searchBtn.innerHTML : "Search Records";

      if (searchBtn) setButtonBusy(searchBtn, "Searching...");

      target.className = "status";
      target.textContent = "Loading error listings...";
      try {
        const response = await fetch(`/api/rejected?event_id=${encodeURIComponent(eventId)}`);
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not load review records.");
        if (!result.records.length) {
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
          clearButtonBusy(searchBtn, originalSearchBtnHtml);
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
      hintsEl.innerHTML = `<strong>Flagged Issues for Row #${record.row_number}:</strong><ul style="margin: 6px 0 0 18px; padding: 0;">` +
        (Array.isArray(errs) ? errs.map(e => `<li><strong>${escapeHtml(e.field)}</strong>: ${escapeHtml(e.hint || e.reason)}</li>`).join('') : '<li>Issue found.</li>') +
        `</ul>`;

      // Fetch saved businesses directly from DB API if not already cached
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
          // fallback to empty
        }
      }

      const activeMapper = typeof getMapper === "function" ? getMapper() : { fields: {} };
      const mapperFields = activeMapper.fields || {};

      // Match similar business from existing data:
      // Check record.business_id, rawObj business_id/brand, active mapper brand, or name matching
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

      const feedbackEl = el("editRecordFeedback");
      if (feedbackEl) {
        feedbackEl.style.display = "none";
        feedbackEl.textContent = "";
        feedbackEl.className = "action-feedback";
      }

      // City/State level ZIP & lat/long suggestion helper. Coordinates come
      // straight from us_zipcodes.latitude/longitude - real ZIP-centroid
      // reference data already stored for every ZIP, not fabricated - so a
      // suggestion is an honest "somewhere in this ZIP", not an exact
      // address-level fix.
      const cityVal = String(getNestedRawValue(rawObj, mapperFields.city || "city") || rawObj.city || rawObj.City || "").trim();
      const stateVal = String(getNestedRawValue(rawObj, mapperFields.state || "state") || rawObj.state || rawObj.State || "").trim();
      const zipVal = String(getNestedRawValue(rawObj, mapperFields.postal_code || "postal_code") || rawObj.zip || rawObj.postal_code || "").trim();
      const latVal = String(getNestedRawValue(rawObj, mapperFields.latitude || "latitude") || rawObj.latitude || "").trim();
      const lonVal = String(getNestedRawValue(rawObj, mapperFields.longitude || "longitude") || rawObj.longitude || "").trim();
      const needsZip = !zipVal || zipVal.length < 5;
      const needsLatLon = !latVal || !lonVal || isNaN(parseFloat(latVal)) || isNaN(parseFloat(lonVal));

      if (cityVal && (needsZip || needsLatLon)) {
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

      el("editRecordForm").querySelectorAll("input, select").forEach(input => {
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

      el("editRecordDialog").showModal();
    }
el("closeEditRecordBtn")?.addEventListener("click", () => el("editRecordDialog").close());
el("cancelEditRecordBtn")?.addEventListener("click", () => el("editRecordDialog").close());
el("submitEditRecordBtn")?.addEventListener("click", async () => {
      if (!currentEditingRecord) return;
      const feedbackEl = el("editRecordFeedback");
      const showDialogError = (msg) => {
        if (feedbackEl) {
          feedbackEl.className = "action-feedback error";
          feedbackEl.style.color = "#cf1322";
          feedbackEl.style.background = "#fff1f0";
          feedbackEl.style.border = "1px solid #ffa39e";
          feedbackEl.style.borderRadius = "4px";
          feedbackEl.style.padding = "8px 12px";
          feedbackEl.textContent = msg;
          feedbackEl.style.display = "block";
        } else {
          alert(msg);
        }
      };

      const inputs = el("editRecordForm").querySelectorAll("input[data-raw-key], select[data-raw-key]");
      const updatedRaw = {};
      const validationErrors = [];
      let selectedBusinessId = "";
      let selectedBrandName = "";

      inputs.forEach(input => {
        const val = input.value.trim();
        const rawKey = input.dataset.rawKey;
        const fieldType = input.dataset.fieldType || "";
        updatedRaw[rawKey] = input.value;

        if (fieldType === "brand") {
          selectedBrandName = val;
          if (input.tagName === "SELECT") {
            const opt = input.selectedOptions[0];
            selectedBusinessId = opt?.dataset.businessId || "";
          }
        }

        // Field specific data validation
        if (fieldType === "latitude" && val) {
          const num = parseFloat(val);
          if (isNaN(num)) {
            validationErrors.push(`Latitude '${val}' for '${rawKey}' must be a valid decimal number.`);
          } else if (num < 13.0 || num > 72.0) {
            validationErrors.push(`Latitude ${num} is outside standard US territory boundaries (13.0 to 72.0). Please correct coordinate.`);
          }
        } else if (fieldType === "longitude" && val) {
          const num = parseFloat(val);
          if (isNaN(num)) {
            validationErrors.push(`Longitude '${val}' for '${rawKey}' must be a valid decimal number.`);
          } else if (!((num >= -180.0 && num <= -64.0) || (num >= 144.0 && num <= 146.0))) {
            validationErrors.push(`Longitude ${num} is outside standard US territory boundaries (-180.0 to -64.0). Please correct coordinate.`);
          }
        } else if (fieldType === "postal_code" && val) {
          const digits = val.replace(/\D/g, "");
          if (digits.length < 5) {
            validationErrors.push(`ZIP Code '${val}' for '${rawKey}' must contain at least 5 digits.`);
          }
        }
      });

      if (validationErrors.length > 0) {
        showDialogError(validationErrors[0]);
        return;
      }

      if (feedbackEl) feedbackEl.style.display = "none";

      const activeMapper = typeof getMapper === "function" ? getMapper() : {};
      const finalBrandName = selectedBrandName || activeMapper.brand || currentEditingRecord.brand || "";
      const finalBusinessId = selectedBusinessId || currentEditingRecord.business_id || activeMapper.business_id || "";

      const retryMapper = {
        ...activeMapper,
        business_id: finalBusinessId,
        source_type_id: currentEditingRecord.source_type_id || activeMapper.source_type_id || "",
        brand: finalBrandName,
        source_name: activeMapper.source_name || "error_listings_review",
        source_type: activeMapper.source_type || "csv",
        fields: activeMapper.fields && Object.keys(activeMapper.fields).length ? activeMapper.fields : {
          name: "name",
          address: "address",
          city: "city",
          state: "state",
          postal_code: "postal_code",
          latitude: "latitude",
          longitude: "longitude"
        }
      };

      const showDialogSuccess = (msg) => {
        if (feedbackEl) {
          feedbackEl.className = "action-feedback ok";
          feedbackEl.style.color = "#389e0d";
          feedbackEl.style.background = "#f6ffed";
          feedbackEl.style.border = "1px solid #b7eb8f";
          feedbackEl.style.borderRadius = "4px";
          feedbackEl.style.padding = "8px 12px";
          feedbackEl.textContent = msg;
          feedbackEl.style.display = "block";
        }
      };

      const submitBtn = el("submitEditRecordBtn");
      const cancelBtn = el("cancelEditRecordBtn");
      const originalBtnHtml = submitBtn ? submitBtn.innerHTML : "Retry Record";

      try {
        if (submitBtn) setButtonBusy(submitBtn, "Retrying...");
        if (cancelBtn) cancelBtn.disabled = true;

        const response = await fetch("/api/reprocess", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            event_id: currentEditingRecord.event_id,
            row_numbers: [currentEditingRecord.row_number],
            mapper: retryMapper,
            rows: [updatedRaw]
          })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not reprocess record.");

        if (result.mapped_rows > 0) {
          const cleanup = result.error_listings_cleanup;
          if (cleanup && cleanup.attempted && !cleanup.ok) {
            // The row is safely in listings, but the old error entry didn't
            // get cleared - say so plainly instead of a blanket "success"
            // that would leave the count silently stuck.
            showDialogError(`Record moved to listings, but the old error entry could not be cleared (still counted in Review Error Listings). ${cleanup.error ? escapeHtml(cleanup.error) : "Please retry or check server logs."}`);
          } else {
            showDialogSuccess(`✅ Record #${currentEditingRecord.row_number} successfully validated & moved from error listings to listings.`);
            setTimeout(() => {
              el("editRecordDialog").close();
            }, 1200);
          }
          await loadRejectedRecords();
          // reprocess already re-counted from BigQuery and wrote it back to
          // SQLite; use the returned total directly for an instant, correct
          // badge, falling back to a forced refresh if it wasn't returned.
          if (typeof result.error_count_total === "number") {
            el("reviewCount").textContent = result.error_count_total;
          } else {
            await refreshReviewCount(true);
          }
          await loadErrorBrandBreakdown();
          setStatus(`Record #${currentEditingRecord.row_number} reprocessed successfully and moved to listings.`, "ok");
        } else {
          // Still invalid: the queue didn't shrink, but a fresh error row may
          // have replaced the old one - re-count from source and refresh the
          // brand breakdown so both stay truthful.
          if (typeof result.error_count_total === "number") {
            el("reviewCount").textContent = result.error_count_total;
          } else {
            await refreshReviewCount(true);
          }
          await loadErrorBrandBreakdown();
          showDialogError("Record validation failed again. Please review required fields, valid ZIP Code, and coordinates.");
        }
      } catch (error) {
        showDialogError(productSafeError(error.message, "Could not reprocess this record."));
      } finally {
        if (submitBtn) {
          clearButtonBusy(submitBtn, originalBtnHtml);
        }
        if (cancelBtn) cancelBtn.disabled = false;
      }
    });
// The tab badge shows the overall Review Error Listings total (all
// businesses), not a per-brand slice - the per-brand split lives in the
// brand-impact breakdown inside the tab. `refresh` forces a live BigQuery
// re-count (and rewrites the SQLite cache); leave it false for cheap lazy
// reads (tab open, app boot) that just want the last-known number instantly.
async function refreshReviewCount(refresh = false) {
      try {
        const response = await fetch(`/api/error-listings/count?business_id=&refresh=${refresh ? "1" : "0"}`);
        const result = await response.json();
        if (response.ok && typeof result.count === "number") el("reviewCount").textContent = result.count;
      } catch (error) {
        // Keep whatever the badge already showed rather than blanking to 0 -
        // a transient fetch failure shouldn't wipe a valid cached count.
      }
    }

// Accessible, distinct categorical hues for the brand-impact donut. Reused
// slice-to-slice so the table swatch and the arc always agree.
const ERROR_BRAND_COLORS = ["#2f6f6a", "#c26a3d", "#4c6ef5", "#b5559e", "#3c9a5f", "#c0392b", "#8a6d3b", "#6741d9", "#128fb0", "#9c6b1f"];

function _donutSvg(slices, total, size = 132) {
      // slices: [{value, color}]. Renders an SVG donut; a single 100% slice
      // is drawn as a full ring (an arc path can't express a 360 deg sweep).
      const radius = size / 2;
      const inner = radius * 0.58;
      const cx = radius;
      const cy = radius;
      if (!total) return "";
      const nonZero = slices.filter((s) => s.value > 0);
      if (nonZero.length === 1) {
        return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="One brand accounts for all error listings">
          <circle cx="${cx}" cy="${cy}" r="${(radius + inner) / 2}" fill="none" stroke="${nonZero[0].color}" stroke-width="${radius - inner}"></circle>
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
        return `<path d="M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${radius} ${radius} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} L ${xi1.toFixed(2)} ${yi1.toFixed(2)} A ${inner} ${inner} 0 ${large} 0 ${xi0.toFixed(2)} ${yi0.toFixed(2)} Z" fill="${slice.color}"></path>`;
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
        el("reviewBrandChart").innerHTML = _donutSvg(withColor.map((b) => ({ value: b.count, color: b.color })), total);
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
