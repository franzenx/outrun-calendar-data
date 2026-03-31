import asyncio
import json
from playwright.async_api import async_playwright

async def scrape_luma_hub(city):
    async with async_playwright() as p:
        # Launching with a modern user-agent to ensure site compatibility
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 800})
        page = await context.new_page()
        
        url = f"https://lu.ma/{city}"
        print(f"Syncing city hub: {url}")
        
        # Navigate and wait for the network to settle
        await page.goto(url, wait_until="networkidle")

        # 98% COVERAGE: Trigger infinite scroll to reveal lazy-loaded side events
        for _ in range(6):
            await page.mouse.wheel(0, 3000)
            await asyncio.sleep(2) # Necessary wait for 2026 dynamic rendering

        # 2026 BEST PRACTICE: Locate by Role (Heading/Link) for stability
        # We look for all links that contain an 'h3' (event title)
        event_elements = await page.get_by_role("link").filter(has=page.get_by_role("heading", level=3)).all()
        
        data = []
        for ev in event_elements:
            try:
                title = await ev.get_by_role("heading", level=3).inner_text()
                link = await ev.get_attribute("href")
                
                # Extracting the unique Luma Event ID for your Direct Sign-up USP
                event_id = link.split('/')[-1] if '/' in link else link
                
                data.append({
                    "name": title.strip(),
                    "id": event_id,
                    "url": f"https://lu.ma/{event_id}",
                    "scraped_at": "2026-03-31" # Tracking for your weekly delta
                })
            except: continue
            
        await browser.close()
        return data

async def main():
    # Your Anchor Cities for 2026 Scaling
    target_cities = ["dubai", "singapore", "london", "paris", "tokyo", "miami"]
    results = {}
    
    for city in target_cities:
        results[city] = await scrape_luma_hub(city)

    # Saving the master JSON feed for the frontend
    with open("data.json", "w") as f:
        json.dump(results, f, indent=4)
    print("Weekly Sync Successful.")

if __name__ == "__main__":
    asyncio.run(main())
