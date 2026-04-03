 """
Outrun – Luma Event Scraper
============================
Strategy (in order of preference):
  1. Luma public API  →  GET api.lu.ma/calendar/get-profile  +  get-items
  2. __NEXT_DATA__ HTML parse  →  extract hydration JSON from page source
  3. Skip hub with a clear error log (never crash the whole run)

No Playwright / no browser required.

Setup:
    pip install requests
Run:
    python scraper.py
"""

import json
import re
import sys
import time
from datetime import datetime, timezone

import requests

# ── Request headers that mimic a real browser ─────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://lu.ma/",
    "Origin": "https://lu.ma",
}

# ── Hub configuration ──────────────────────────────────────────────────────────
HUBS = {
    "dubai": [
        {"name": "TOKEN2049 Dubai",  "slug": "token2049-dubai"},
    ],
    "singapore": [
        {"name": "BLOCK71 Singapore", "slug": "b71singapore"},
    ],
    "london": [
        {"name": "Future: UK",  "slug": "ldn"},
        {"name": "TechGames",   "slug": "techgames"},
        {"name": "Granola",     "slug": "granola"},
    ],
    "paris": [
        {"name": "Climate House", "slug": "climate.house"},
        {"name": "ArtVerse",      "slug": "artverseparis"},
    ],
    "tokyo": [
        {"name": "Startup Calendar", "slug": "startup-calendar"},
        {"name": "Superteam Japan",  "slug": "superteamJapan"},
    ],
    "miami": [
        {"name": "Hello Miami",            "slug": "hello_miami"},
        {"name": "Les Femmes Social Club", "slug": "socialclublf"},
        {"name": "Miami AI Hub",           "slug": "miamiaihub"},
    ],
    "lisbon": [
        {"name": "OneThousandClub Lisbon", "slug": "onethousandclub_lisbon"},
    ],
    "berlin":      [],
    "rio":         [],
    "mexico-city": [],
    "sao-paulo":   [],
    "copenhagen":  [],
    "warsaw":      [],
}

PAGINATION_LIMIT = 50
REQUEST_TIMEOUT  = 20   # seconds
SLEEP_BETWEEN    = 1.5  # seconds between hub requests (be polite)


# ── Helper: normalise a raw event dict ────────────────────────────────────────

def normalise_event(raw: dict) -> dict | None:
    """
    Convert a raw Luma event object (from any API shape) into our
    canonical schema.  Returns None if the event has no valid api_id.
    """
    api_id = raw.get("api_id", "")
    if not api_id or not api_id.startswith("evt-"):
        return None

    geo   = raw.get("geo_address_info") or {}
    loc   = (
        geo.get("full_address")
        or geo.get("city_state")
        or geo.get("description")
        or ""
    )
    slug  = raw.get("url") or api_id
    return {
        "api_id":    api_id,
        "name":      (raw.get("name") or "Untitled").strip(),
        "start_at":  raw.get("start_at", ""),
        "end_at":    raw.get("end_at", ""),
        "url":       f"https://lu.ma/{slug}",
        "cover_url": raw.get("cover_url") or "",
        "location":  loc,
    }


def dedup(events: list[dict]) -> list[dict]:
    seen, out = set(), []
    for ev in events:
        if ev["api_id"] not in seen:
            seen.add(ev["api_id"])
            out.append(ev)
    return out


# ── Approach 1: Luma public API ───────────────────────────────────────────────

def api_get_calendar_id(slug: str) -> str | None:
    """Resolve a calendar slug to its internal cal-xxx api_id."""
    url = f"https://api.lu.ma/calendar/get-profile?url_name={slug}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        cal = r.json().get("calendar", {})
        cal_id = cal.get("api_id", "")
        if cal_id:
            print(f"    [API] Resolved '{slug}' → {cal_id}")
            return cal_id
    except Exception as exc:
        print(f"    [API] get-profile failed for '{slug}': {exc}")
    return None


def api_get_events(cal_id: str) -> list[dict]:
    """Paginate through all events for a calendar api_id."""
    events, cursor = [], None

    while True:
        params = {"calendar_api_id": cal_id, "pagination_limit": PAGINATION_LIMIT}
        if cursor:
            params["pagination_cursor"] = cursor

        try:
            r = requests.get(
                "https://api.lu.ma/calendar/get-items",
                params=params, headers=HEADERS, timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print(f"    [API] get-items failed (cursor={cursor}): {exc}")
            break

        entries = data.get("entries", [])
        for entry in entries:
            raw   = entry.get("event") or entry
            event = normalise_event(raw)
            if event:
                events.append(event)

        cursor = data.get("next_cursor")
        if not cursor or not entries:
            break

        time.sleep(0.5)

    print(f"    [API] {len(events)} events fetched via direct API")
    return events


# ── Approach 2: __NEXT_DATA__ HTML parse ──────────────────────────────────────

def _walk(obj, found: list, seen: set):
    """Recursively walk a JSON object and collect all event-shaped dicts."""
    if isinstance(obj, dict):
        api_id = obj.get("api_id", "")
        if api_id.startswith("evt-") and "name" in obj:
            ev = normalise_event(obj)
            if ev and ev["api_id"] not in seen:
                seen.add(ev["api_id"])
                found.append(ev)
        for v in obj.values():
            _walk(v, found, seen)
    elif isinstance(obj, list):
        for item in obj:
            _walk(item, found, seen)


def html_get_events(slug: str) -> list[dict]:
    """
    Fetch the Luma calendar page, extract the embedded __NEXT_DATA__ JSON blob,
    and recursively harvest any event objects from it.
    """
    url = f"https://lu.ma/{slug}"
    try:
        r = requests.get(url, headers={**HEADERS, "Accept": "text/html"}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        html = r.text
    except Exception as exc:
        print(f"    [HTML] Page fetch failed for '{slug}': {exc}")
        return []

    # Extract __NEXT_DATA__ JSON blob
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    if not match:
        print(f"    [HTML] __NEXT_DATA__ not found for '{slug}'")
        return []

    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        print(f"    [HTML] JSON parse error for '{slug}': {exc}")
        return []

    found, seen = [], set()
    _walk(next_data, found, seen)
    print(f"    [HTML] {len(found)} events extracted from __NEXT_DATA__")
    return found


# ── Main scraper ───────────────────────────────────────────────────────────────

def scrape_hub(hub_name: str, slug: str) -> list[dict]:
    print(f"  → [{hub_name}] lu.ma/{slug}")

    # ── Try API first ──────────────────────────────────────────────────────────
    cal_id = api_get_calendar_id(slug)
    if cal_id:
        events = api_get_events(cal_id)
        if events:
            return dedup(events)
        print(f"    [API] No events returned — falling back to HTML parse")

    # ── Fallback: parse HTML ───────────────────────────────────────────────────
    events = html_get_events(slug)
    if events:
        return dedup(events)

    print(f"    ✗ No events found for '{slug}' via any method")
    return []


def main():
    # ── Load existing data.json (preserves the conferences structure from Excel) ──
    try:
        with open("data.json", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        payload = {}

    conferences = payload.get("conferences", [])
    total = 0

    # ── If conferences format exists, update events within each conference ────────
    if conferences:
        print(f"Updating events for {len(conferences)} conferences...\n")
        for conf in conferences:
            slug = conf.get("luma_slug", "")
            if not slug:
                continue
            print(f"\n📍 {conf['name']} (lu.ma/{slug})")
            events = scrape_hub(conf["name"], slug)
            if events:
                conf["events"] = events
                total += len(events)
            time.sleep(SLEEP_BETWEEN)

    # ── Fallback: if no conferences key, build from HUBS config (legacy) ─────────
    else:
        print("No conferences key found — building from HUBS config...\n")
        num = 1
        for city, hubs in HUBS.items():
            print(f"\n📍 {city.upper()}")
            for hub in hubs:
                events = scrape_hub(hub["name"], hub["slug"])
                total += len(events)
                conferences.append({
                    "id":        hub["slug"],
                    "num":       num,
                    "name":      hub["name"],
                    "city":      city.capitalize(),
                    "country":   "",
                    "region":    "",
                    "tier":      2,
                    "tier_label": "Luma Hub",
                    "start":     "",
                    "end":       "",
                    "quarter":   "TBC",
                    "status":    "✅ Confirmed",
                    "focus":     "",
                    "attendance": "",
                    "website":   f"https://lu.ma/{hub['slug']}",
                    "opportunity": "",
                    "luma_slug": hub["slug"],
                    "events":    events,
                })
                num += 1
                time.sleep(SLEEP_BETWEEN)

    payload["conferences"]  = conferences
    payload["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Remove legacy hubs key if present
    payload.pop("hubs", None)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print(f"\n✅  Done — {total} events updated across {len(conferences)} conferences")


if __name__ == "__main__":
    main()
