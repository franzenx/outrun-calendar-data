"""
Outrun Luma Calendar Scraper
============================
Uses Playwright to navigate each Luma hub/calendar page and intercepts
the internal Luma API responses (api.lu.ma) to extract real event data
including proper evt-XXXX IDs needed for the Luma checkout widget.

Setup:
    pip install playwright
    playwright install chromium

Run:
    python scraper.py
"""

import asyncio
import json
import re
from datetime import datetime, timezone

# ─── Hub Configuration ────────────────────────────────────────────────────────
# Key = city slug (used in frontend grouping)
# Value = list of Luma calendar hubs in that city
HUBS = {
    "dubai": [
        {"name": "TOKEN2049 Dubai", "slug": "token2049-dubai"},
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
        {"name": "Hello Miami",         "slug": "hello_miami"},
        {"name": "Les Femmes Social Club", "slug": "socialclublf"},
        {"name": "Miami AI Hub",        "slug": "miamiaihub"},
    ],
    "lisbon": [
        {"name": "OneThousandClub Lisbon", "slug": "onethousandclub_lisbon"},
    ],
    "berlin": [],
    "rio": [],
    "mexico-city": [],
    "sao-paulo": [],
    "copenhagen": [],
    "warsaw": [],
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def extract_events_from_payload(payload: dict, seen_ids: set) -> list:
    """
    Luma's API returns events in several shapes depending on endpoint.
    This function handles all known variants and extracts normalised event dicts.
    """
    candidates = []

    # Shape A: { entries: [ { event: {...}, ... } ] }
    for entry in payload.get("entries", []):
        if isinstance(entry, dict):
            event = entry.get("event") or entry
            candidates.append(event)

    # Shape B: { events: [ {...} ] }
    for event in payload.get("events", []):
        candidates.append(event)

    # Shape C: { data: { entries: [...] } }
    data_block = payload.get("data", {})
    if isinstance(data_block, dict):
        for entry in data_block.get("entries", []):
            event = entry.get("event") or entry
            candidates.append(event)

    results = []
    for event in candidates:
        if not isinstance(event, dict):
            continue
        api_id = event.get("api_id", "")
        # Only keep real event IDs (format: evt-XXXXXXXXXXXXXXXXXXXX)
        if not api_id or not api_id.startswith("evt-"):
            continue
        if api_id in seen_ids:
            continue
        seen_ids.add(api_id)

        # Resolve the public URL — prefer the slug stored in `url` field
        slug = event.get("url") or api_id
        public_url = f"https://lu.ma/{slug}"

        # Geo / location
        geo = event.get("geo_address_info") or {}
        location = (
            geo.get("full_address")
            or geo.get("city_state")
            or geo.get("description")
            or ""
        )

        results.append({
            "api_id":    api_id,
            "name":      (event.get("name") or "Untitled Event").strip(),
            "start_at":  event.get("start_at", ""),
            "end_at":    event.get("end_at", ""),
            "url":       public_url,
            "cover_url": event.get("cover_url") or "",
            "location":  location,
        })

    return results


# ─── Scraper ──────────────────────────────────────────────────────────────────

async def scrape_hub(browser, hub_name: str, hub_slug: str) -> list:
    """
    Open a Luma calendar/hub page, intercept all api.lu.ma responses,
    scroll to trigger pagination, and return all discovered events.
    """
    from playwright.async_api import async_playwright

    context = await browser.new_context(
        viewport={"width": 1280, "height": 900},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        locale="en-US",
    )
    page = await context.new_page()

    captured_events: list = []
    seen_ids: set = set()

    async def on_response(response):
        """Intercept every response from api.lu.ma and try to extract events."""
        if "api.lu.ma" not in response.url:
            return
        if response.status != 200:
            return
        try:
            payload = await response.json()
            new_events = extract_events_from_payload(payload, seen_ids)
            if new_events:
                print(f"    ✓ +{len(new_events)} events from {response.url.split('?')[0]}")
                captured_events.extend(new_events)
        except Exception:
            pass  # Not JSON or unrelated endpoint — skip silently

    page.on("response", on_response)

    url = f"https://lu.ma/{hub_slug}"
    print(f"  → Scraping: {url}")

    try:
        await page.goto(url, wait_until="networkidle", timeout=60_000)

        # Scroll repeatedly to trigger lazy-load and infinite scroll
        for i in range(12):
            await page.mouse.wheel(0, 2500)
            await asyncio.sleep(1.2)

        # Final wait for any trailing requests to complete
        await page.wait_for_timeout(3_000)

    except Exception as exc:
        print(f"    ✗ Navigation error for {hub_slug}: {exc}")
    finally:
        await context.close()

    print(f"    → {len(captured_events)} total events captured for [{hub_name}]")
    return captured_events


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    from playwright.async_api import async_playwright

    output = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)

        for city, hubs in HUBS.items():
            print(f"\n📍 City: {city.upper()}")
            city_result = []

            for hub in hubs:
                events = await scrape_hub(browser, hub["name"], hub["slug"])
                city_result.append({
                    "name":   hub["name"],
                    "id":     hub["slug"],
                    "url":    f"https://lu.ma/{hub['slug']}",
                    "events": events,
                })

            output[city] = city_result

        await browser.close()

    # Write enriched data.json
    result = {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hubs": output,
    }

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    total_events = sum(
        len(hub["events"])
        for city_hubs in output.values()
        for hub in city_hubs
    )
    print(f"\n✅ Scrape complete — {total_events} events written to data.json")


if __name__ == "__main__":
    asyncio.run(main())
