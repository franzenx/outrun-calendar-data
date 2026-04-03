import json
import re
import time
from datetime import datetime, timezone

import requests

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

PAGINATION_LIMIT = 50
REQUEST_TIMEOUT = 20
SLEEP_BETWEEN = 1.5

# Fallback hub list — only used if data.json has no conferences key
HUBS = {
    "dubai":     [{"name": "TOKEN2049 Dubai",         "slug": "token2049-dubai"}],
    "singapore": [{"name": "BLOCK71 Singapore",       "slug": "b71singapore"}],
    "london":    [
        {"name": "Future: UK",  "slug": "ldn"},
        {"name": "TechGames",   "slug": "techgames"},
        {"name": "Granola",     "slug": "granola"},
    ],
    "paris":     [
        {"name": "Climate House", "slug": "climate.house"},
        {"name": "ArtVerse",      "slug": "artverseparis"},
    ],
    "tokyo":     [
        {"name": "Startup Calendar", "slug": "startup-calendar"},
        {"name": "Superteam Japan",  "slug": "superteamJapan"},
    ],
    "miami":     [
        {"name": "Hello Miami",            "slug": "hello_miami"},
        {"name": "Les Femmes Social Club", "slug": "socialclublf"},
        {"name": "Miami AI Hub",           "slug": "miamiaihub"},
    ],
    "lisbon":    [{"name": "OneThousandClub Lisbon", "slug": "onethousandclub_lisbon"}],
}


def normalise_event(raw):
    api_id = raw.get("api_id", "")
    if not api_id or not api_id.startswith("evt-"):
        return None
    geo = raw.get("geo_address_info") or {}
    loc = (
        geo.get("full_address")
        or geo.get("city_state")
        or geo.get("description")
        or ""
    )
    slug = raw.get("url") or api_id
    return {
        "api_id":    api_id,
        "name":      (raw.get("name") or "Untitled").strip(),
        "start_at":  raw.get("start_at", ""),
        "end_at":    raw.get("end_at", ""),
        "url":       "https://lu.ma/" + slug,
        "cover_url": raw.get("cover_url") or "",
        "location":  loc,
    }


def dedup(events):
    seen = set()
    out = []
    for ev in events:
        if ev["api_id"] not in seen:
            seen.add(ev["api_id"])
            out.append(ev)
    return out


def api_get_calendar_id(slug):
    url = "https://api.lu.ma/calendar/get-profile?url_name=" + slug
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        cal_id = r.json().get("calendar", {}).get("api_id", "")
        if cal_id:
            print("    [API] Resolved '" + slug + "' -> " + cal_id)
            return cal_id
    except Exception as exc:
        print("    [API] get-profile failed for '" + slug + "': " + str(exc))
    return None


def api_get_events(cal_id):
    events = []
    cursor = None
    while True:
        params = {"calendar_api_id": cal_id, "pagination_limit": PAGINATION_LIMIT}
        if cursor:
            params["pagination_cursor"] = cursor
        try:
            r = requests.get(
                "https://api.lu.ma/calendar/get-items",
                params=params,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            print("    [API] get-items failed: " + str(exc))
            break
        entries = data.get("entries", [])
        for entry in entries:
            raw = entry.get("event") or entry
            ev = normalise_event(raw)
            if ev:
                events.append(ev)
        cursor = data.get("next_cursor")
        if not cursor or not entries:
            break
        time.sleep(0.5)
    print("    [API] " + str(len(events)) + " events fetched")
    return events


def _walk(obj, found, seen):
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


def html_get_events(slug):
    url = "https://lu.ma/" + slug
    try:
        r = requests.get(
            url,
            headers=dict(HEADERS, Accept="text/html"),
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        html = r.text
    except Exception as exc:
        print("    [HTML] Page fetch failed: " + str(exc))
        return []
    match = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not match:
        print("    [HTML] __NEXT_DATA__ not found for '" + slug + "'")
        return []
    try:
        next_data = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        print("    [HTML] JSON parse error: " + str(exc))
        return []
    found = []
    seen = set()
    _walk(next_data, found, seen)
    print("    [HTML] " + str(len(found)) + " events extracted")
    return found


def scrape_hub(name, slug):
    print("  -> [" + name + "] lu.ma/" + slug)
    cal_id = api_get_calendar_id(slug)
    if cal_id:
        events = api_get_events(cal_id)
        if events:
            return dedup(events)
        print("    [API] No events — falling back to HTML parse")
    events = html_get_events(slug)
    if events:
        return dedup(events)
    print("    x No events found for '" + slug + "'")
    return []


def main():
    # Load existing data.json to preserve the conferences structure
    try:
        with open("data.json", encoding="utf-8") as f:
            payload = json.load(f)
    except FileNotFoundError:
        payload = {}

    conferences = payload.get("conferences", [])
    total = 0

    if conferences:
        # New format: update events within each conference that has a luma_slug
        print("Updating events for " + str(len(conferences)) + " conferences...\n")
        for conf in conferences:
            slug = conf.get("luma_slug", "")
            if not slug:
                continue
            print("\n>> " + conf["name"] + " (lu.ma/" + slug + ")")
            events = scrape_hub(conf["name"], slug)
            if events:
                conf["events"] = events
                total += len(events)
            time.sleep(SLEEP_BETWEEN)
    else:
        # Legacy fallback: build from HUBS config
        print("No conferences key found — building from HUBS config...\n")
        num = 1
        for city, hubs in HUBS.items():
            print("\n>> City: " + city.upper())
            for hub in hubs:
                events = scrape_hub(hub["name"], hub["slug"])
                total += len(events)
                conferences.append({
                    "id":          hub["slug"],
                    "num":         num,
                    "name":        hub["name"],
                    "city":        city.capitalize(),
                    "country":     "",
                    "region":      "",
                    "tier":        2,
                    "tier_label":  "Luma Hub",
                    "start":       "",
                    "end":         "",
                    "quarter":     "TBC",
                    "status":      "Confirmed",
                    "focus":       "",
                    "attendance":  "",
                    "website":     "https://lu.ma/" + hub["slug"],
                    "opportunity": "",
                    "luma_slug":   hub["slug"],
                    "events":      events,
                })
                num += 1
                time.sleep(SLEEP_BETWEEN)

    payload["conferences"] = conferences
    payload["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload.pop("hubs", None)

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    print("\nDone — " + str(total) + " events updated across " + str(len(conferences)) + " conferences")


if __name__ == "__main__":
    main()
