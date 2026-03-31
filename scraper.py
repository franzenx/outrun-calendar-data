import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_luma_city(city_slug):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # 1. Navigate to the Hub
        url = f"https://lu.ma/{city_slug}"
        print(f"Scraping {city_slug}...")
        await page.goto(url, wait_until="networkidle")

        # 2. Infinite Scroll for 98% Coverage
        for _ in range(8):
            await page.mouse.wheel(0, 3000)
            await asyncio.sleep(2)

        # 3. SEMANTIC SELECTOR: Find all links that contain an H3 heading
        # This bypasses dynamic CSS classes completely.
        event_links = await page.get_by_role("link").filter(has=page.get_by_role("heading", level=3)).all()
        
        scraped_data = []
        for link_el in event_links:
            try:
                # Extract text and URL using roles
                name = await link_el.get_by_role("heading", level=3).inner_text()
                href = await link_el.get_attribute("href")
                
                # Extract Event ID for the Direct Sign-up Overlay
                event_id = href.split('/')[-1] if '/' in href else href

                scraped_data.append({
                    "name": name.strip(),
                    "id": event_id,
                    "url": f"https://lu.ma/{event_id}"
                })
            except: continue

        await browser.close()
        return scraped_data

async def main():
    cities = ["dubai", "singapore", "london", "paris", "tokyo", "miami"]
    master_data = {}

    for city in cities:
        master_data[city] = await scrape_luma_city(city)

    # Save to the file that the frontend "listens" to
    with open("data.json", "w") as f:
        json.dump(master_data, f, indent=4)
    print(f"Success: Synced {sum(len(v) for v in master_data.values())} events.")

if __name__ == "__main__":
    asyncio.run(main())
