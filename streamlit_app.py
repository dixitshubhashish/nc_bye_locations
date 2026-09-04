from __future__ import annotations

import os
from typing import Any

import streamlit as st

from whitespace_tool.source_adapters import api_get_source, csv_source, excel_source, json_source, xml_source
from whitespace_tool.source_adapters.common import flatten_object
from whitespace_tool.workflow_server import (
    list_brands,
    mapper_targets,
    prepare_zipcodes,
    save_mapper,
    validate_mapper,
)
from whitespace_tool.source_adapters.excel_source import list_sheets


FIELD_ORDER = [
    "name", "address", "city", "state", "postal_code", "location_id", "town", "province", "country",
    "latitude", "longitude", "franchise_name", "concept_type", "cuisine_type", "neighborhood", "district",
    "phone_number", "website_url", "google_maps_link", "social_media_handles", "operating_hours", "seating_capacity",
    "service_types", "opening_date", "status", "observed_at", "annual_revenue", "average_ticket_size", "daily_footfall",
    "monthly_footfall", "rental_cost", "lease_cost", "population_density", "average_household_income", "competitor_count",
    "foot_traffic_score", "parking_availability",
]
FIELD_ORDER_INDEX = {key: index for index, key in enumerate(FIELD_ORDER)}


st.set_page_config(page_title="Competitive Whitespace Tool", page_icon="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRMN8cedT14Ys3ypKhW3VrDD0t2kE9zx5yzNsXv7sj9kg&s", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #f4f7fb; color: #17233f; }
    [data-testid="stHeader"] { background: #101d3b; }
    [data-testid="stSidebar"] { background: #edf2f8; }
    h1, h2, h3 { color: #17233f; }
    .brand-bar { background: #101d3b; color: white; padding: 16px 24px; border-radius: 0 0 8px 8px; margin: -1rem -1rem 1.5rem; }
    .brand-bar strong { color: #0bb5d8; font-size: 1.1rem; }
    .coverage-low { color: #c43b54; font-weight: 800; font-size: 1.4rem; }
    .coverage-medium { color: #b97816; font-weight: 800; font-size: 1.4rem; }
    .coverage-high { color: #147d63; font-weight: 800; font-size: 1.4rem; }
    .disclaimer { color: #68758d; font-size: .75rem; border-top: 1px solid #dce3ee; padding-top: 1rem; margin-top: 2rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _secret(name: str, default: str) -> str:
    try:
        return str(st.secrets.get(name, os.environ.get(name, default)))
    except Exception:
        return os.environ.get(name, default)


def _reset_workflow() -> None:
    for key in ("source_preview", "source_bytes", "source_name", "source_type", "mapping"):
        st.session_state.pop(key, None)


@st.cache_data(ttl=300, show_spinner=False)
def cached_targets() -> list[dict[str, Any]]:
    return mapper_targets()


@st.cache_data(ttl=300, show_spinner=False)
def cached_brands() -> list[dict[str, Any]]:
    return list_brands().get("brands", [])


def _ordered_targets(targets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(targets, key=lambda target: (FIELD_ORDER_INDEX.get(target["key"], 10_000), target["label"]))


def _preview(source_type: str, content: bytes, file_name: str, record_path: str | None) -> dict[str, Any]:
    if source_type == "csv":
        return csv_source.preview(content, record_path)
    if source_type == "excel":
        return excel_source.preview(content, record_path, file_name)
    if source_type == "json":
        return json_source.preview(content, record_path)
    if source_type == "xml":
        return xml_source.preview(content, record_path)
    raise ValueError(f"Unsupported file source type: {source_type}")


def _coverage(mapping: dict[str, str], source_fields: list[str]) -> int:
    if not source_fields:
        return 0
    return round(len({value for value in mapping.values() if value}) / len(source_fields) * 100)


def login() -> bool:
    if st.session_state.get("authenticated"):
        return True
    st.markdown('<div class="brand-bar"><strong>birdeye</strong> &nbsp; Competitive Whitespace Tool</div>', unsafe_allow_html=True)
    st.subheader("Sign in")
    with st.form("login_form"):
        username = st.text_input("Username", value="admin")
        password = st.text_input("Password", type="password")
        remember = st.checkbox("Remember login")
        submitted = st.form_submit_button("Login")
    if submitted:
        if username.strip() == _secret("WORKFLOW_LOGIN_USER", "admin") and password == _secret("WORKFLOW_LOGIN_PASSWORD", "birdeye"):
            st.session_state["authenticated"] = True
            st.session_state["remember_login"] = remember
            st.rerun()
        st.error("Invalid username or password.")
    st.caption("ZIP reference preparation continues in the background while you sign in.")
    return False


def source_section() -> None:
    st.header("Source")
    source_type = st.selectbox("Source format", ["CSV", "Excel", "JSON", "XML", "GET API JSON"], key="source_type_select")
    source_name = st.text_input("Source name", placeholder="Example: dominos_store_locator_api")
    record_path = ""
    uploaded = None
    if source_type != "GET API JSON":
        uploaded = st.file_uploader("Upload source file", type=["csv", "xlsx", "xls", "json", "xml"], key="source_upload")
        if source_type == "Excel" and uploaded:
            sheets = list_sheets(uploaded.getvalue(), uploaded.name)
            record_path = st.selectbox("Excel sheet", sheets) if sheets else ""
        elif source_type == "JSON" and st.session_state.get("json_record_paths"):
            paths = st.session_state["json_record_paths"]
            selected = st.selectbox("JSON record layer", ["(automatic)", *paths], key="json_record_layer")
            record_path = "" if selected == "(automatic)" else selected
        elif source_type in {"JSON", "XML"}:
            record_path = st.text_input("Record path (optional)", placeholder="Example: data.locations")
    else:
        api_url = st.text_input("GET API URL", placeholder="https://example.com/stores.json")
        record_path = st.text_input("Record path (optional)", placeholder="Example: data.locations")

    if st.button("Preview source", type="primary"):
        try:
            if source_type == "GET API JSON":
                if not api_url.strip():
                    raise ValueError("Enter a GET API URL.")
                preview = api_get_source.preview_url(api_url.strip(), record_path or None)
                normalized_type = "api_get_json"
                source_bytes = None
            else:
                if uploaded is None:
                    raise ValueError("Choose a source file.")
                normalized_type = source_type.lower()
                source_bytes = uploaded.getvalue()
                preview = _preview(normalized_type, source_bytes, uploaded.name, record_path or None)
                if normalized_type == "json":
                    st.session_state["json_record_paths"] = preview.get("record_paths", [])
            st.session_state.update(source_preview=preview, source_bytes=source_bytes, source_name=source_name.strip(), source_type=normalized_type, source_record_path=record_path)
            st.session_state.pop("mapping", None)
            st.success(f"Parsed {preview['record_count']} records with {len(preview['fields'])} source fields.")
        except Exception as exc:
            st.error(str(exc))


def mapping_section() -> None:
    preview = st.session_state.get("source_preview")
    if not preview:
        st.info("Preview a source to begin field mapping.")
        return
    targets = _ordered_targets(cached_targets())
    source_fields = preview["fields"]
    previous = st.session_state.get("mapping", {})
    selections: dict[str, str] = {}
    with st.form("mapping_form"):
        st.header("Field Mapping")
        st.caption("Mandatory fields are listed first. Choose the source field that corresponds to each standard field.")
        for target in targets:
            options = ["Unmapped", *source_fields]
            selected = st.selectbox(target["label"] + (" *" if target.get("required") else ""), options, index=options.index(previous.get(target["key"], "Unmapped")) if previous.get(target["key"], "Unmapped") in options else 0, key=f"map_{target['key']}")
            selections[target["key"]] = "" if selected == "Unmapped" else selected
        submitted = st.form_submit_button("Update mapping")
    if submitted:
        st.session_state["mapping"] = selections
        st.rerun()
    mapping = st.session_state.get("mapping", selections)
    coverage = _coverage(mapping, source_fields)
    color = "low" if coverage < 50 else "medium" if coverage <= 75 else "high"
    st.markdown(f'<span class="coverage-{color}">Mapping coverage: {coverage}%</span>', unsafe_allow_html=True)
    st.caption(f"{len({value for value in mapping.values() if value})} of {len(source_fields)} source columns mapped")
    if coverage < 50:
        st.warning("Map at least 50% of source columns before saving.")
    return mapping, targets, coverage


def app() -> None:
    if not login():
        return
    st.markdown('<div class="brand-bar"><strong>birdeye</strong> &nbsp; Competitive Whitespace Tool</div>', unsafe_allow_html=True)
    with st.sidebar:
        try:
            st.session_state["brands"] = cached_brands()
        except Exception as exc:
            st.warning(f"Businesses are unavailable until storage is configured: {exc}")
        if st.button("Prepare ZIP reference"):
            with st.spinner("Preparing reference data..."):
                try:
                    result = prepare_zipcodes()
                    st.success("Reference data is ready.")
                except Exception as exc:
                    st.error(str(exc))
        if st.button("Log out"):
            st.session_state["authenticated"] = False
            st.rerun()
    source_section()
    mapping_result = mapping_section()
    if not mapping_result:
        return
    mapping, targets, coverage = mapping_result
    preview = st.session_state["source_preview"]
    with st.expander("Source preview", expanded=True):
        st.dataframe(preview["rows"], use_container_width=True, hide_index=True)
    with st.expander("Workflow template JSON"):
        st.json({"source_name": st.session_state.get("source_name", ""), "source_type": st.session_state.get("source_type", ""), "fields": mapping})
    brand_options = {brand["name"]: brand for brand in st.session_state.get("brands", [])}
    if not brand_options:
        st.info("Select a business in the HTML workflow or configure businesses in BigQuery before saving from Streamlit.")
    selected_brand_name = st.selectbox("Business", ["Select a business", *brand_options.keys()])
    if st.button("Save workflow template", type="primary", disabled=coverage < 50):
        if selected_brand_name == "Select a business":
            st.error("Select a business before saving.")
            return
        mapper = {
            "brand": selected_brand_name,
            "business_id": brand_options[selected_brand_name]["business_id"],
            "source_name": st.session_state.get("source_name", ""),
            "source_type": st.session_state.get("source_type", ""),
            "fields": mapping,
        }
        errors = validate_mapper(mapper, preview["fields"], preview["rows"])
        if errors:
            st.error(f"Please complete the mapping: {', '.join(errors)}")
            return
        try:
            with st.spinner("Processing your records..."):
                prepare_zipcodes()
                result = save_mapper({"mapper": mapper, "rows": preview["rows"], "source_fields": preview["fields"]})
            st.success(f"Processing complete: {result['mapped_rows']} of {result['total_rows']} records processed successfully; {result['error_listings']} records need review.")
        except Exception as exc:
            st.error(str(exc))
    st.markdown('<div class="disclaimer">Birdeye is a trademark of Birdeye, Inc. All rights in the Birdeye name and logo are reserved by Birdeye, Inc. This prototype is provided for assessment and evaluation purposes only; no other use is intended or authorized.</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    app()
