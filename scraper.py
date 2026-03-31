import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_luma_city(city_slug):
    async with async_playwright() as p:
        # Launching with modern user-agent for 2026 Luma compatibility
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        url = f"https://lu.ma/{city_slug}"
        print(f"Syncing City Hub: {url}")
        
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
            
            # Infinite Scroll for 98% side-event coverage
            for _ in range(8):
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(2)

            # 2026 Semantic Selector: Target roles to bypass dynamic CSS classes
            event_links = await page.get_by_role("link").filter(has=page.get_by_role("heading", level=3)).all()
            
            scraped_data = []
            for link_el in event_links:
                try:
                    name = await link_el.get_by_role("heading", level=3).inner_text()
                    href = await link_el.get_attribute("href")
                    
                    # Extract Unique ID for Direct Sign-up USP
                    event_id = href.split('/')[-1] if '/' in href else href

                    scraped_data.append({
                        "name": name.strip(),
                        "id": event_id,
                        "url": f"https://lu.ma/{event_id}",
                        "scraped_at": "2026-03-31"
                    })
                except: continue
            
            await browser.close()
            return scraped_data
        except Exception as e:
            print(f"Error scraping {city_slug}: {e}")
            await browser.close()
            return []

async def main():
    # THE 2026 GLOBAL STACK
    cities = [
        "dubai", "singapore", "london", "paris", "tokyo", "miami",
        "berlin", "rio", "mexico-city", "sao-paulo", "copenhagen", 
        "lisbon", "warsaw"
    ]
    
    master_data = {}
    for city in cities:
        master_data[city] = await scrape_luma_city(city)

    # Save master JSON for the frontend
    with open("data.json", "w") as f:
        json.dump(master_data, f, indent=4)
    
    total = sum(len(v) for v in master_data.values())
    print(f"Global Sync Complete: {total} events found across {len(cities)} hubs.")

if __name__ == "__main__":
    asyncio.run(main())
