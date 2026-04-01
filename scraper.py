import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_luma_hub(city):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()
        
        url = f"https://lu.ma/{city}"
        print(f"Syncing city hub: {url}")
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Scroll to load dynamic events inside the Hub
            for _ in range(5):
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(1)

            # Target links that look like individual Luma events
            links = await page.query_selector_all('a[href*="/"]')
            
            data = []
            seen_ids = set()

            for link in links:
                href = await link.get_attribute('href')
                # Filter for actual event paths (avoiding social/policy links)
                if href and not any(x in href for x in ['facebook', 'twitter', 'instagram', 'terms', 'privacy', 'create']):
                    # Extract the ID/Slug (e.g., 'evt-xxxx' or 'event-name')
                    event_id = href.split('/')[-1].split('?')[0]
                    
                    if event_id and event_id not in seen_ids and len(event_id) > 5:
                        title_el = await link.query_selector('h3, .event-name, span')
                        title = await title_el.inner_text() if title_el else event_id
                        
                        data.append({
                            "name": title.strip(),
                            "id": event_id, # This is the ID needed for the pop-up
                            "url": f"https://lu.ma/{event_id}",
                            "scraped_at": "2026-04-01"
                        })
                        seen_ids.add(event_id)
            
            await browser.close()
            return data
        except Exception as e:
            print(f"Error scraping {city}: {e}")
            await browser.close()
            return []

async def main():
    target_cities = ["dubai", "london", "paris", "lisbon", "singapore"]
    results = {}
    
    for city in target_cities:
        results[city] = await scrape_luma_hub(city)

    with open("data.json", "w") as f:
        json.dump(results, f, indent=4)
    print("USP Sync Successful.")

if __name__ == "__main__":
    asyncio.run(main())
