from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import pickle
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urlencode
import urllib.request
from urllib.error import HTTPError, URLError

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
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://order.dominos.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "X-DPZ-Market": "UNITED_STATES",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
            break
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == 2:
                raise
            sleep(1.5 * (attempt + 1))
    else:
        raise RuntimeError(f"Domino's locator request failed: {last_error}")
    _write_cached(cache_path, zip_code, order_type, payload)
    return payload


def _stores_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    stores = payload.get("Stores") or payload.get("stores") or []
    if isinstance(stores, dict):
        stores = list(stores.values())
    if not isinstance(stores, list):
        return []
    return [store for store in stores if isinstance(store, dict)]


def fetch_for_zips(
    zip_codes: list[str],
    order_type: str = "Carryout",
    cache_dir: str | Path | None = None,
    stores_per_zip: int | None = None,
    max_workers: int = 8,
) -> dict[str, Any]:
    observed_at = utc_now_iso()
    stores_by_id: dict[str, dict[str, Any]] = {}
    errors = []
    worker_count = max(1, min(max_workers, max(len(zip_codes), 1)))

    def fetch_one(zip_code: str) -> tuple[str, dict[str, Any] | None, str | None]:
        try:
            return zip_code, fetch_zip(zip_code, order_type=order_type, cache_dir=cache_dir), None
        except Exception as exc:
            return zip_code, None, str(exc)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(fetch_one, zip_code) for zip_code in zip_codes]
        for future in as_completed(futures):
            zip_code, payload, error = future.result()
            if error or payload is None:
                errors.append({"zip_code": zip_code, "error": error or "Unknown error"})
                continue
            stores = _stores_from_payload(payload)
            if stores_per_zip:
                stores = stores[:stores_per_zip]
            for store in stores:
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
        "stores_per_zip": stores_per_zip,
        "max_workers": worker_count,
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
