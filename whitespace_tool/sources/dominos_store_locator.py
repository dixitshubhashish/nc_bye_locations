from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
import urllib.request

from whitespace_tool.models import utc_now_iso


LOCATOR_URL = "https://order.dominos.com/power/store-locator"


def _cache_key(zip_code: str, order_type: str) -> str:
    return f"{zip_code}_{order_type.lower()}.pickle"


def _load_cached(cache_dir: Path, zip_code: str, order_type: str) -> dict[str, Any] | None:
    path = cache_dir / _cache_key(zip_code, order_type)
    if not path.exists():
        return None
    with path.open("rb") as handle:
        return pickle.load(handle)


def _write_cached(cache_dir: Path, zip_code: str, order_type: str, payload: dict[str, Any]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    with (cache_dir / _cache_key(zip_code, order_type)).open("wb") as handle:
        pickle.dump(payload, handle)


def fetch_zip(zip_code: str, order_type: str = "Carryout", cache_dir: str | Path | None = None, use_cache: bool = True) -> dict[str, Any]:
    zip_code = str(zip_code).zfill(5)[:5]
    cache_path = Path(cache_dir or "outputs/cache/dominos_locator")
    if use_cache:
        cached = _load_cached(cache_path, zip_code, order_type)
        if cached is not None:
            return cached
    query = urlencode({"s": "", "c": zip_code, "type": order_type})
    request = urllib.request.Request(
        f"{LOCATOR_URL}?{query}",
        headers={
            "accept": "application/json",
            "user-agent": "Mozilla/5.0 competitive-whitespace-prototype",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    _write_cached(cache_path, zip_code, order_type, payload)
    return payload


def _stores_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    stores = payload.get("Stores") or payload.get("stores") or []
    if isinstance(stores, dict):
        stores = list(stores.values())
    if not isinstance(stores, list):
        return []
    return [store for store in stores if isinstance(store, dict)]


def fetch_for_zips(zip_codes: list[str], order_type: str = "Carryout", cache_dir: str | Path | None = None) -> dict[str, Any]:
    observed_at = utc_now_iso()
    stores_by_id: dict[str, dict[str, Any]] = {}
    errors = []
    for zip_code in zip_codes:
        try:
            payload = fetch_zip(zip_code, order_type=order_type, cache_dir=cache_dir)
        except Exception as exc:
            errors.append({"zip_code": zip_code, "error": str(exc)})
            continue
        for store in _stores_from_payload(payload):
            store_id = str(store.get("StoreID") or store.get("StoreId") or store.get("store_id") or "").strip()
            if not store_id:
                continue
            normalized = dict(store)
            normalized["ObservedAt"] = observed_at
            stores_by_id[store_id] = normalized
    return {
        "source": "unofficial_dominos_store_locator",
        "locator_url": LOCATOR_URL,
        "order_type": order_type,
        "observed_at": observed_at,
        "zip_count": len(zip_codes),
        "Stores": sorted(stores_by_id.values(), key=lambda row: str(row.get("StoreID") or "")),
        "errors": errors,
    }


def _read_zip_codes(path: str | Path) -> list[str]:
    zip_codes = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            digits = "".join(ch for ch in line if ch.isdigit())
            if digits:
                zip_codes.append(digits[:5].zfill(5))
    return sorted(set(zip_codes))


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Domino's store-locator JSON by ZIP code.")
    parser.add_argument("--zip-file", required=True, help="Text file with one ZIP code per line.")
    parser.add_argument("--output", default="outputs/dominos_store_locator.json")
    parser.add_argument("--cache-dir", default="outputs/cache/dominos_locator")
    parser.add_argument("--type", default="Carryout", choices=["Carryout", "Delivery"])
    args = parser.parse_args()
    result = fetch_for_zips(_read_zip_codes(args.zip_file), order_type=args.type, cache_dir=args.cache_dir)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(result['Stores'])} Domino's stores to {output_path}")


if __name__ == "__main__":
    main()
