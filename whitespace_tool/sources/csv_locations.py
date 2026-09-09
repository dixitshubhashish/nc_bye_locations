"""CSV file location source - the `csv` source format.

Config-side counterpart of the app's CSV source type
(`whitespace_tool/source_adapters/csv_source.py`, which serves the mapper
screen). Pizza Hut is the CSV demo brand, so its entry in
`config/predefined_brand_templates.json` carries `"source_type": "csv"` and
resolves here.

This module also owns `LOCATION_SOURCE_MODULES` - the config `type` -> module
dispatcher - and `load_location_sources()`, the single entry point `cli.py`
calls for every format.

`pizza_hut_kaggle.py` was folded into this file rather than renamed into a
third module. It was a mapper-driven CSV reader: `csv.DictReader` over a local
file, each row through `normalize_location()`. That is the job this file
already did; the only real difference was how the config expressed its column
mapping - an inline `columns` dict here, a mapper template there. That is not
enough to justify a second CSV module, and `json_locations.py` already absorbs
the identical axis of variation inside one `load()` (its `resolve_mapper()`
accepts an inline mapping *or* a template path). "kaggle" also named the
provenance of one downloaded snapshot rather than a format - nothing can
dispatch on where a file happened to come from, and the module contained
nothing Pizza-Hut-specific either. So `load()` below branches on which mapping
shape the config supplied and both shapes keep working, while the old
`pizza_hut_kaggle` type string survives as an alias in the dispatcher because
`config/live_bigquery.json` still uses it.
"""

from __future__ import annotations

import csv
from importlib import import_module
from pathlib import Path
from typing import Any

from whitespace_tool.models import LocationRecord, utc_now_iso
from whitespace_tool.normalization import normalize_location
# `resolve_mapper` decides "inline mapping vs. template path", which is a
# property of how a config is written and has nothing to do with JSON. It lives
# in `json_locations.py` only because that is where it was first needed, and
# `get_json_api_locations.py` already imports it from there. Sharing the one
# implementation is worth the slightly odd-looking import direction; there is no
# cycle, as `json_locations.py` imports nothing from this module.
from whitespace_tool.sources.json_locations import resolve_mapper


def _clean_zip(value: str) -> str:
    # Deliberately not `normalization.clean_zip`. This is the legacy `columns`
    # path's own US-only rule (digits, zero-padded to 5); the shared helper also
    # preserves alphanumeric international codes. Switching it here would change
    # what already-written `columns` configs produce, which is a data decision,
    # not part of a module rename - so the divergence stays until someone asks.
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits[:5].zfill(5) if digits else ""


def _optional_float(value: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _resolve_path(value: str, config_dir: Path) -> Path:
    """Config paths are written relative to the config file's own directory.

    Joining is enough to cover an absolute path too: `Path("/a") / "/b"` is
    `/b`, so a config that spells out a full path still wins.
    """
    return config_dir / value


def load_mapped_csv(path: str | Path, source_name: str, mapper: dict[str, Any]) -> list[LocationRecord]:
    """Read a CSV through a mapper - the same cleaning path the JSON sources take.

    Opened as utf-8-sig, not utf-8: exported location CSVs routinely carry a
    byte-order mark, and leaving it in place turns the first header cell into a
    name no mapping matches, so the leading column silently maps to nothing.
    """
    records: list[LocationRecord] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        for index, row in enumerate(csv.DictReader(fh), start=1):
            record = normalize_location(row, mapper, source_name, index)
            if record:
                records.append(record)
    return records


def load_locations_csv(path: str | Path, source_name: str, column_map: dict[str, str]) -> list[LocationRecord]:
    """Read a CSV through a flat source-column -> field dict.

    Thinner than the mapper path and older than it: it hand-rolls the field
    extraction, drops any row without both a brand and a postal code, and
    synthesizes a location id when the source has none.

    `column_map` is the same shape as a mapper's `fields` - canonical field name
    to source column - and the id it synthesizes is character-for-character the
    one `normalize_location()` builds, so this is very close to being a third
    copy of the mapper path rather than a separate strategy. It is left standing
    for now because collapsing it would change what a `columns` config produces
    (the postal-code skip disappears, and ZIP cleaning switches to the shared
    helper that preserves international codes) - a data decision, not a rename.
    No config in this repo currently uses the shape, and nothing imports this
    function, so the collapse is cheap whenever someone decides it.
    """
    records: list[LocationRecord] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for index, row in enumerate(reader, start=1):
            postal_code = _clean_zip(row.get(column_map.get("postal_code", "postal_code"), ""))
            if not postal_code:
                continue
            brand = row.get(column_map.get("brand", "brand"), "").strip()
            if not brand:
                continue
            location_id = row.get(column_map.get("location_id", "location_id"), "").strip()
            if not location_id:
                location_id = f"{brand.lower().replace(' ', '_')}:{postal_code}:{index}"
            records.append(
                LocationRecord(
                    brand=brand,
                    # Explicitly None, and required: `LocationRecord` gained
                    # `business_id`/`source_type_id` as mandatory fields and this
                    # call site was never updated, so this path has been raising
                    # TypeError on its first row ever since (verified against
                    # HEAD - the fold did not introduce it). `None` matches what
                    # `normalize_location()` produces when a mapper omits them;
                    # a `columns` config has nowhere to express either one.
                    business_id=None,
                    source_type_id=None,
                    location_id=location_id,
                    name=row.get(column_map.get("name", "name"), "").strip(),
                    address=row.get(column_map.get("address", "address"), "").strip(),
                    city=row.get(column_map.get("city", "city"), "").strip(),
                    state=row.get(column_map.get("state", "state"), "").strip().upper(),
                    postal_code=postal_code,
                    latitude=_optional_float(row.get(column_map.get("latitude", "latitude"), "")),
                    longitude=_optional_float(row.get(column_map.get("longitude", "longitude"), "")),
                    source=source_name,
                    observed_at=row.get(column_map.get("observed_at", "observed_at"), "").strip() or utc_now_iso(),
                    raw=dict(row),
                )
            )
    return records


def load(source: dict[str, Any], config_dir: Path) -> list[LocationRecord]:
    """Dispatcher entry point for the `csv` format.

    Two mapping shapes arrive here and both are valid config - neither is a
    fallback for the other:

      * `mapper` - a workflow template path, or the mapping written inline. This
        is the shape the mapper screen and the JSON/API sources speak, and it
        runs rows through the shared `normalize_location()` cleaning pass, so
        prefer it for anything new. This is what the folded-in
        `pizza_hut_kaggle` module did.
      * `columns` - the older flat dict, handled by `load_locations_csv()`.
        Kept so configs written that way keep loading, though see that
        function's note: it is a near-duplicate of the mapper path.
    """
    path = _resolve_path(source["path"], config_dir)
    if source.get("mapper") is not None:
        return load_mapped_csv(path, source["name"], resolve_mapper(source, config_dir))
    return load_locations_csv(path, source["name"], source.get("columns", {}))


# Config `type` -> module providing `load(source, config_dir)`.
#
# This used to be a set whose members doubled as module names, which forced
# every source type to be named after whichever brand first needed it -
# `dominos_api`, `little_caesars_json`, `pizza_hut_kaggle`. That coupling is
# what let the naming go wrong: Little Caesars is the GET JSON API demo and
# Domino's is the JSON demo, so a "little_caesars_json" type/module pair told
# the reader the opposite of the truth. Separating type name from module name
# lets a config say what *format* it is reading, using the same vocabulary as
# the mapper screen.
#
# The brand-named entries below are retained deliberately as aliases, not as
# live names: `config/live_bigquery.json` still uses them and is outside this
# change's ownership. They resolve to the format modules, so those configs keep
# working while new configs use the format names.
LOCATION_SOURCE_MODULES = {
    # Format names - what a config should use.
    "csv": "csv_locations",
    "json": "json_locations",
    "api_get_json": "get_json_api_locations",
    # Legacy brand-named aliases, kept only so existing configs resolve.
    "dominos_api": "json_locations",
    "little_caesars_json": "json_locations",
    # `pizza_hut_kaggle` named a Kaggle download, not a format. Its module folded
    # into this file (see the module docstring), so the old type string now
    # resolves to the CSV format module it always effectively was.
    "pizza_hut_kaggle": "csv_locations",
}


def load_location_sources(config: dict[str, Any]) -> list[LocationRecord]:
    all_records: list[LocationRecord] = []
    base_dir = Path(config["_config_dir"])
    for source in config["location_sources"]:
        module_name = LOCATION_SOURCE_MODULES.get(source["type"])
        if not module_name:
            raise ValueError(f"Unsupported location source type: {source['type']}")
        # `csv` resolves to this module. `import_module` hands back the copy
        # already in `sys.modules`, so the self-reference is free and every
        # format goes through one uniform lookup rather than a special case for
        # the one format that happens to live beside the dispatcher.
        module = import_module(f"whitespace_tool.sources.{module_name}")
        all_records.extend(module.load(source, base_dir))
    return all_records
