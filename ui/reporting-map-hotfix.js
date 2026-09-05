(() => {
  function install() {
    if (typeof renderReportingMap !== "function" || typeof el !== "function") {
      setTimeout(install, 100);
      return;
    }

    renderReportingMap = function renderReportingMapPreserved(mapRecords = [], gapRecords = [], stateRecords = []) {
      if (!el("reportingMap")) return;

      const displayStates = stateRecords.length ? stateRecords : defaultStateRecords;
      if (!window.L) {
        renderStaticUSMap(displayStates);
        return;
      }

      if (!reportingMap) {
        el("reportingMap").innerHTML = "";
        reportingMap = L.map("reportingMap", {
          zoomSnap: 0.1,
          zoomDelta: 0.5,
          minZoom: 2,
          maxZoom: 18
        }).setView([39.0, -96.5], 3.8);

        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(reportingMap);

        mapMarkerLayerGroup = L.layerGroup().addTo(reportingMap);
        stateBoundaryLayerGroup = L.layerGroup().addTo(reportingMap);
      }

      mapMarkerLayerGroup.clearLayers();
      stateBoundaryLayerGroup.clearLayers();

      const mainBrandSet = new Set(
        [el("reportMainBrandSelect")?.value || ""]
          .filter(Boolean)
          .map((brand) => brand.toLowerCase())
      );
      const bounds = [];

      if (!mapRecords.length && !gapRecords.length) {
        const states = (displayStates || []).filter((row) => stateCentroids[String(row.state || "").toUpperCase()]);
        const stateCounts = new Map(
          states.map((row) => [String(row.state || "").toUpperCase(), Number(row.locations || 0)])
        );

        fetch("https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/us-states.json")
          .then((response) => (response.ok ? response.json() : null))
          .then((geojson) => {
            if (!geojson || !stateBoundaryLayerGroup) return;
            stateBoundaryLayerGroup.clearLayers();

            L.geoJSON(geojson, {
              style: (feature) => {
                const code = stateNameToCode[feature?.properties?.name] || "";
                return {
                  color: stateCounts.has(code) ? "#2563eb" : "#94a3b8",
                  weight: stateCounts.has(code) ? 1.4 : 0.8,
                  fillColor: stateCounts.has(code) ? "#dbeafe" : "#f8fafc",
                  fillOpacity: stateCounts.has(code) ? 0.22 : 0.08
                };
              },
              onEachFeature: (feature, layer) => {
                const code = stateNameToCode[feature?.properties?.name] || "";
                if (!code) return;
                layer.bindTooltip(feature.properties.name || code, {
                  sticky: true,
                  className: "state-code-label"
                });
                layer.bindPopup(`
                  <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
                    <strong>${escapeHtml(feature.properties.name || code)}</strong><br/>
                    <span>${formatNumber(stateCounts.get(code) || 0)} ZIP locations</span>
                  </div>
                `);
              }
            }).addTo(stateBoundaryLayerGroup);
          })
          .catch(() => {});

        states.forEach((row) => {
          const stateCode = String(row.state || "").toUpperCase();
          const [lat, lon] = stateCentroids[stateCode];
          const marker = L.circleMarker([lat, lon], {
            radius: Math.max(8, Math.min(22, Math.sqrt(Number(row.locations || 0)) * 1.2)),
            fillColor: "#e7f0ff",
            color: "#2563eb",
            weight: 1.5,
            opacity: 0.9,
            fillOpacity: 0.85
          });

          marker.bindTooltip(stateCode, {
            permanent: true,
            direction: "center",
            className: "state-code-label"
          });

          marker.bindPopup(`
            <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
              <strong>${escapeHtml(row.state_name || stateCodeToName[stateCode] || stateCode)} (${escapeHtml(stateCode)})</strong><br/>
              <span>${formatNumber(row.locations)} ZIP location${Number(row.locations || 0) === 1 ? "" : "s"}</span>
            </div>
          `);

          mapMarkerLayerGroup.addLayer(marker);
        });
      }

      mapRecords.forEach((rec) => {
        const lat = parseFloat(rec.latitude);
        const lon = parseFloat(rec.longitude);
        if (!isUSLatLong(lat, lon)) return;

        bounds.push([lat, lon]);
        const isPrimary = mainBrandSet.has(String(rec.brand || "").toLowerCase());
        const color = isPrimary ? "#2563eb" : "#dc2626";
        const stateLabel = rec.state_name || rec.state || "";

        const marker = L.circleMarker([lat, lon], {
          radius: 6,
          fillColor: color,
          color: "#ffffff",
          weight: 1.5,
          opacity: 1,
          fillOpacity: 0.85
        });

        marker.bindPopup(`
          <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
            <strong style="color: ${color}; font-size: 14px;">${escapeHtml(rec.name || rec.brand)}</strong><br/>
            <span>${escapeHtml(rec.address || "")}</span><br/>
            <span>${escapeHtml(rec.city || "")}, ${escapeHtml(stateLabel)} ${escapeHtml(rec.zip_code || "")}</span><br/>
            <span style="color: #64748b; font-size: 11px;">🌐 Lat: ${lat.toFixed(4)}, Lon: ${lon.toFixed(4)}</span><br/>
            ${rec.phone_number ? `<span style="color: #64748b;">📞 ${escapeHtml(rec.phone_number)}</span>` : ""}
          </div>
        `);

        mapMarkerLayerGroup.addLayer(marker);
      });

      gapRecords.forEach((gap) => {
        const lat = parseFloat(gap.latitude);
        const lon = parseFloat(gap.longitude);
        if (!isUSLatLong(lat, lon)) return;

        bounds.push([lat, lon]);
        const stateLabel = gap.state_name || gap.state || "";
        const marker = L.circleMarker([lat, lon], {
          radius: 8,
          fillColor: "#16a34a",
          color: "#ffffff",
          weight: 2,
          opacity: 1,
          fillOpacity: 0.9
        });

        marker.bindPopup(`
          <div style="font-family: sans-serif; font-size: 13px; line-height: 1.4;">
            <strong style="color: #16a34a; font-size: 14px;">📍 Whitespace Candidate ZIP ${escapeHtml(gap.zip_code)}</strong><br/>
            <span>${escapeHtml(gap.city || "")}, ${escapeHtml(stateLabel)} (${escapeHtml(gap.county || "")})</span><br/>
            <span style="color: #64748b; font-size: 11px;">🌐 Lat: ${lat.toFixed(4)}, Lon: ${lon.toFixed(4)}</span>
            <hr style="margin: 6px 0; border: none; border-top: 1px solid #e2e8f0;"/>
            <span><strong>Competitors Operating:</strong> ${escapeHtml(gap.brands_present || "")} (${gap.competitor_locations} store${gap.competitor_locations > 1 ? "s" : ""})</span><br/>
            <span><strong>Population:</strong> ${formatNumber(gap.population)}</span><br/>
            <span><strong>Median Income:</strong> ${gap.median_household_income ? "$" + formatNumber(gap.median_household_income) : "N/A"}</span><br/>
            <span><strong>Median Age:</strong> ${gap.median_age || "N/A"} yrs</span>
          </div>
        `);

        mapMarkerLayerGroup.addLayer(marker);
      });

      if (mapRecords.length || gapRecords.length) {
        if (bounds.length) {
          reportingMap.fitBounds(bounds, { padding: [35, 35], maxZoom: 12 });
        } else {
          reportingMap.setView([38.5, -96.0], 3.8);
        }
      } else {
        reportingMap.fitBounds([[23.8, -125.0], [50.2, -66.5]], {
          padding: [10, 10],
          maxZoom: 4.0
        });
      }

      setTimeout(() => {
        if (!reportingMap) return;
        reportingMap.invalidateSize();
        if (!mapRecords.length && !gapRecords.length) {
          reportingMap.fitBounds([[23.8, -125.0], [50.2, -66.5]], {
            padding: [10, 10],
            maxZoom: 4.0
          });
        }
      }, 250);
    };
  }

  if (document.readyState === "complete") install();
  else window.addEventListener("load", install, { once: true });
})();
