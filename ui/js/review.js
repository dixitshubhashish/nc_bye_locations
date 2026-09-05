// Review Error Listings tab: rejected-record search and the edit/retry modal.

let currentEditingRecord = null;
async function loadRejectedRecords() {
      const eventId = el("reviewEventId").value.trim();
      const target = el("reviewResults");
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
function openEditRecordModal(record) {
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

      // required_location fails in two ways: (1) no brand/ZIP at all, or
      // (2) brand+ZIP resolved but name/address/city/state didn't. Either
      // way, the missing value's mapped path may simply be absent from
      // raw_record (sparse JSON/XML/API sources omit blank fields), so it
      // never gets a regular input below. Surface exactly the fields the
      // triggered variant(s) need, keyed to the exact path the mapper will
      // look up on retry, so they're always fixable here.
      const locationErrors = Array.isArray(errs) ? errs.filter(e => e.field === "required_location") : [];
      const missingKeys = new Set();
      locationErrors.forEach((e) => {
        if (e.reason === "missing brand or ZIP Code") {
          missingKeys.add("brand");
          missingKeys.add("postal_code");
        } else {
          ["name", "address", "city", "state", "postal_code"].forEach((key) => missingKeys.add(key));
        }
      });
      const activeMapper = typeof getMapper === "function" ? getMapper() : { fields: {} };
      const mapperFields = activeMapper.fields || {};
      const fixedBrand = String(activeMapper.brand || "").trim();
      const LOCATION_FIELD_SPECS = {
        brand: { label: "Business / Brand Name", path: mapperFields.brand || "brand", note: fixedBrand ? `Optional - falls back to selected business "${fixedBrand}" if left blank.` : "Required - no fixed business is selected for this mapper." },
        name: { label: "Location Name", path: mapperFields.name || "name", note: "Required." },
        address: { label: "Address", path: mapperFields.address || "address", note: "Required." },
        city: { label: "City", path: mapperFields.city || "city", note: "Required." },
        state: { label: "State", path: mapperFields.state || "state", note: "Required." },
        postal_code: { label: "ZIP Code", path: mapperFields.postal_code || "postal_code", note: "Required - 5-digit US ZIP code." },
      };
      const requiredPaths = new Set();
      const requiredFieldHtml = ["brand", "name", "address", "city", "state", "postal_code"]
        .filter((key) => missingKeys.has(key))
        .map((key) => {
          const { label, path, note } = LOCATION_FIELD_SPECS[key];
          requiredPaths.add(path);
          return `
        <div style="display: flex; flex-direction: column;">
          <label style="font-size: 12px; font-weight: 700; color: var(--ink); margin-bottom: 4px;">${escapeHtml(label)} <span style="font-weight: 400; color: #cf1322;">(${escapeHtml(path)})</span></label>
          <input type="text" data-raw-key="${escapeHtml(path)}" value="${escapeHtml(String(getNestedRawValue(rawObj, path)))}" style="padding: 6px; border: 1px solid var(--line); border-radius: 4px; font-size: 13px;">
          <span style="font-size: 11px; color: var(--muted, #6b7280); margin-top: 2px;">${escapeHtml(note)}</span>
        </div>
      `;
        }).join('');

      const formEl = el("editRecordForm");
      formEl.innerHTML = requiredFieldHtml + Object.entries(rawObj).filter(([key]) => !requiredPaths.has(key)).map(([key, val]) => `
        <div style="display: flex; flex-direction: column;">
          <label style="font-size: 12px; font-weight: 700; color: var(--ink); margin-bottom: 4px;">${escapeHtml(key)}</label>
          <input type="text" data-raw-key="${escapeHtml(key)}" value="${escapeHtml(val !== null && val !== undefined ? String(val) : '')}" style="padding: 6px; border: 1px solid var(--line); border-radius: 4px; font-size: 13px;">
        </div>
      `).join('');

      el("editRecordDialog").showModal();
    }
el("closeEditRecordBtn")?.addEventListener("click", () => el("editRecordDialog").close());
el("cancelEditRecordBtn")?.addEventListener("click", () => el("editRecordDialog").close());
el("submitEditRecordBtn")?.addEventListener("click", async () => {
      if (!currentEditingRecord) return;
      const inputs = el("editRecordForm").querySelectorAll("input[data-raw-key]");
      const updatedRaw = {};
      inputs.forEach(input => {
        updatedRaw[input.dataset.rawKey] = input.value;
      });

      try {
        const response = await fetch("/api/reprocess", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            event_id: currentEditingRecord.event_id,
            row_numbers: [currentEditingRecord.row_number],
            mapper: getMapper(),
            rows: [updatedRaw]
          })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || "Could not reprocess record.");
        el("editRecordDialog").close();
        await loadRejectedRecords();
        setStatus(`Record #${currentEditingRecord.row_number} reprocessed. ${result.mapped_rows} accepted.`, "ok");
      } catch (error) {
        alert(productSafeError(error.message, "Could not reprocess this record."));
      }
    });
async function refreshReviewCount() {
      const businessId = selectedBrand?.business_id || "";
      try {
        const response = await fetch(`/api/error-listings/count?business_id=${encodeURIComponent(businessId)}`);
        const result = await response.json();
        if (response.ok) el("reviewCount").textContent = result.count;
      } catch (error) {
        el("reviewCount").textContent = "0";
      }
    }

