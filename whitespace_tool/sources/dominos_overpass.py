from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import random
from time import monotonic, sleep
from typing import Any
import threading
import urllib.error
import urllib.parse
import urllib.request

from whitespace_tool.models import utc_now_iso


OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_USER_AGENT = "competitive-whitespace-prototype/1.0"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


def _query(zip_code: str) -> str:
    return f"""
[out:json][timeout:60];
(
  node["name"~"^Domino'?s( Pizza)?$",i]["addr:postcode"="{zip_code}"];
  way["name"~"^Domino'?s( Pizza)?$",i]["addr:postcode"="{zip_code}"];
  relation["name"~"^Domino'?s( Pizza)?$",i]["addr:postcode"="{zip_code}"];
);
out center tags;
"""


class OverpassSession:
    def __init__(self, delay_seconds: float = 1.0, retries: int = 3) -> None:
        self.delay_seconds = delay_seconds
        self.retries = retries
        self._last_request_at = 0.0

    def _rate_limit(self) -> None:
        elapsed = monotonic() - self._last_request_at
        if elapsed < self.delay_seconds:
            sleep(self.delay_seconds - elapsed)
        self._last_request_at = monotonic()

    def fetch_zip(self, zip_code: str) -> list[dict[str, Any]]:
        data = urllib.parse.urlencode({"data": _query(zip_code)}).encode("utf-8")
        request = urllib.request.Request(
            OVERPASS_URL,
            data=data,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded; charset=utf-8",
                "User-Agent": OVERPASS_USER_AGENT,
            },
        )
        for attempt in range(self.retries):
            self._rate_limit()
            try:
                with urllib.request.urlopen(request, timeout=75) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                elements = payload.get("elements", [])
                return [element for element in elements if isinstance(element, dict)]
            except urllib.error.HTTPError as exc:
                if exc.code not in RETRY_STATUS_CODES or attempt == self.retries - 1:
                    raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == self.retries - 1:
                    raise
            sleep((2 * (attempt + 1)) + random.uniform(0.2, 0.8))
        return []


def _to_store(element: dict[str, Any], zip_code: str, observed_at: str) -> dict[str, Any] | None:
    tags = element.get("tags") if isinstance(element.get("tags"), dict) else {}
    if element.get("type") == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:
        center = element.get("center") if isinstance(element.get("center"), dict) else {}
        lat, lon = center.get("lat"), center.get("lon")
    store_id = element.get("id")
    element_type = element.get("type")
    if store_id is None or not element_type:
        return None
    return {
        "StoreID": f"osm-{element_type}-{store_id}",
        "StoreName": tags.get("name") or "Domino's Pizza",
        "AddressDescription": f"{tags.get('addr:housenumber', '')} {tags.get('addr:street', '')}".strip(),
        "City": tags.get("addr:city", ""),
        "Region": tags.get("addr:state", ""),
        "PostalCode": tags.get("addr:postcode") or zip_code,
        "Latitude": lat,
        "Longitude": lon,
        "ObservedAt": observed_at,
        "QueryZip": zip_code,
    }


def fetch_for_zips(
    zip_codes: list[str],
    delay_seconds: float = 1.0,
    one_per_zip: bool = False,
    max_workers: int = 4,
) -> dict[str, Any]:
    observed_at = utc_now_iso()
    stores_by_id: dict[str, dict[str, Any]] = {}
    errors = []
    worker_count = max(1, min(max_workers, max(len(zip_codes), 1)))
    thread_local = threading.local()

    def session() -> OverpassSession:
        if not hasattr(thread_local, "session"):
            thread_local.session = OverpassSession(delay_seconds=delay_seconds)
        return thread_local.session

    def fetch_one(zip_code: str) -> tuple[str, list[dict[str, Any]], str | None]:
        try:
            return zip_code, session().fetch_zip(zip_code), None
        except Exception as exc:
            return zip_code, [], str(exc)

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(fetch_one, str(zip_code).zfill(5)[:5]) for zip_code in zip_codes]
        for future in as_completed(futures):
            zip_code, elements, error = future.result()
            if error:
                errors.append({"zip_code": zip_code, "error": error})
                continue
            stores = [_to_store(element, zip_code, observed_at) for element in elements]
            stores = [store for store in stores if store]
            if one_per_zip:
                stores = stores[:1]
            for store in stores:
                stores_by_id[store["StoreID"]] = store
    return {
        "source": "openstreetmap_overpass",
        "locator_url": OVERPASS_URL,
        "observed_at": observed_at,
        "zip_count": len(zip_codes),
        "one_per_zip": one_per_zip,
        "max_workers": worker_count,
        "Stores": sorted(stores_by_id.values(), key=lambda store: store["StoreID"]),
        "errors": errors,
    }
