import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_luma_hub(city):
    async with async_playwright() as p:
        # Launching browser with modern 2026 headers
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = f"https://lu.ma/{city}"
        print(f"Syncing city hub: {url}")
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Scroll to trigger lazy loading of side events
            for _ in range(5):
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(2)

            # 2026 USP Logic: Extract specific event links
            # We look for links containing event slugs/IDs
            event_links = await page.query_selector_all('a[href*="/"]')
            
            data = []
            seen_ids = set()

            for link in event_links:
                href = await link.get_attribute('href')
                
                # Filter out navigation/social links to find actual events
                if href and not any(x in href for x in ['facebook', 'twitter', 'instagram', 'terms', 'privacy', 'create', 'explore', 'calendar']):
                    # Clean the ID (e.g., from "/evt-123?ref=hub" to "evt-123")
                    event_id = href.split('/')[-1].split('?')[0]
                    
                    if event_id and event_id not in seen_ids and len(event_id) > 4:
                        # Try to grab the closest heading for the title
                        title_el = await link.query_selector('h3, .event-name, span')
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
            print(f"Error scraping {city}: {e}")
            await browser.close()
            return []

async def main():
    # Anchor cities for Outrun Scaling
    target_cities = ["dubai", "london", "paris", "lisbon", "singapore"]
    results = {}
    
    for city in target_cities:
        results[city] = await scrape_luma_hub(city)

    # Save master JSON feed
    with open("data.json", "w") as f:
        json.dump(results, f, indent=4)
    print("Full Data Sync Successful.")

if __name__ == "__main__":
    asyncio.run(main())
