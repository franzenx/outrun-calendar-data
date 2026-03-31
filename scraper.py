import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_luma_city(city_slug):
    async with async_playwright() as p:
        # Launching with a high-end 2026 Browser profile
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        
        url = f"https://lu.ma/{city_slug}"
        print(f"🚀 Syncing: {url}")
        
        try:
            # 1. Navigate and wait for the network to settle
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # 2. FORCE LOAD: Wait for the event container to actually exist
            # We look for links that likely point to events
            await page.wait_for_selector("a[href*='/']", timeout=15000)
            
            # 3. HUMAN SCROLL: Luma hides events until you scroll down
            for _ in range(5):
                await page.mouse.wheel(0, 1500)
                await asyncio.sleep(1)

            # 4. BROAD SELECTOR: Find every link that looks like an event
            # We look for links that contain "h3" (titles) or have specific event patterns
            links = await page.query_selector_all("a")
            
            scraped_data = []
            for link in links:
                href = await link.get_attribute("href")
                # Filter for valid Luma event links only
                if href and (href.startswith("/") or "lu.ma/" in href) and len(href) > 5:
                    # Try to find a title inside that link
                    title_el = await link.query_selector("h3, .title, font")
                    if title_el:
                        name = await title_el.inner_text()
                        event_id = href.split('/')[-1].split('?')[0]
                        
                        # Avoid duplicates
                        if not any(d['id'] == event_id for d in scraped_data):
                            scraped_data.append({
                                "name": name.strip(),
                                "id": event_id,
                                "url": f"https://lu.ma/{event_id}"
                            })

            print(f"✅ Found {len(scraped_data)} events in {city_slug}")
            await browser.close()
            return scraped_data
            
        except Exception as e:
            print(f"⚠️ Error in {city_slug}: {e}")
            await browser.close()
            return []

async def main():
    cities = [
        "dubai", "singapore", "london", "paris", "tokyo", "miami",
        "berlin", "rio", "mexico-city", "sao-paulo", "copenhagen", 
        "lisbon", "warsaw"
    ]
    
    master_data = {}
    for city in cities:
        master_data[city] = await scrape_luma_city(city)

    # Final Write - This is what the Website "reads"
    with open("data.json", "w") as f:
        json.dump(master_data, f, indent=4)
    
    print("🏁 Global Sync Finished.")

if __name__ == "__main__":
    asyncio.run(main())
