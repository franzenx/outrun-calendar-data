import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_luma_hub(city):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        # Based on your Tier 1 reference: Dubai, Brussels, London, etc.
        url = f"https://lu.ma/{city}"
        print(f"Deep-syncing: {url}")
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Heavy scroll to capture all sub-events in the hub
            for _ in range(8):
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(1.5)

            # Selecting all links that likely contain a Luma Event ID
            event_elements = await page.query_selector_all('a[href*="/"]')
            
            data = []
            seen_ids = set()

            for el in event_elements:
                href = await el.get_attribute('href')
                
                # Filter for valid event slugs, excluding platform pages
                if href and not any(x in href for x in ['facebook', 'twitter', 'terms', 'privacy', 'create', 'explore', 'calendar', 'settings']):
                    # Clean the ID (The 'evt-xxx' or custom slug)
                    event_id = href.split('/')[-1].split('?')[0]
                    
                    if event_id and event_id not in seen_ids and len(event_id) > 4:
                        # Grab event title from within the card
                        title_el = await el.query_selector('h3, .event-name, .title')
                        title = await title_el.inner_text() if title_el else event_id
                        
                        data.append({
                            "name": title.strip(),
                            "id": event_id,
                            "url": f"https://lu.ma/{event_id}",
                            "scraped_at": "2026-04-01"
                        })
                        seen_ids.add(event_id)
            
            await browser.close()
            return data
        except Exception as e:
            print(f"Error at {city}: {e}")
            await browser.close()
            return []

async def main():
    # Targeted based on your 'Master Calendar' Tier 1/2 Cities
    target_cities = ["dubai", "brussels", "london", "paris", "singapore", "bangkok"]
    results = {}
    
    for city in target_cities:
        results[city] = await scrape_luma_hub(city)

    with open("data.json", "w") as f:
        json.dump(results, f, indent=4)
    print("Full Deep-Scrape Successful.")

if __name__ == "__main__":
    asyncio.run(main())
