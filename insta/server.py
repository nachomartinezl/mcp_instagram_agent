from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright, Page
import asyncio
from typing import Optional
import os
import json
from datetime import datetime
import random
import logging

# --- Set up logging ---
log_file = "instagram_server.log"
logging.basicConfig(
    level=logging.INFO, # Capture INFO, WARNING, ERROR, CRITICAL
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file), # Log to a file
        # logging.StreamHandler() # Optional: Uncomment to ALSO log to console IF run directly
    ]
)
# ---------------------


class InstagramServer:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.screenshots_dir = "instagram_screenshots"
        self.cookies_path = os.path.join(
            os.path.dirname(__file__), "cookies", "instagram.json"
        )
        # Create screenshots directory if it doesn't exist
        os.makedirs(self.screenshots_dir, exist_ok=True)
        logging.info("InstagramServer instance created.")

    async def load_cookies(self):
        """Load cookies from instagram.json file"""
        if os.path.exists(self.cookies_path):
            try:
                with open(self.cookies_path, 'r') as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
                logging.info("Cookies loaded successfully from %s", self.cookies_path) # <-- Use logging
                return True
            except Exception as e:
                logging.error("Failed to load or add cookies from %s: %s", self.cookies_path, e) # <-- Use logging
                return False
        logging.warning("Cookie file not found at %s", self.cookies_path) # <-- Use logging
        return False

    async def init(self):
        if self.browser:
            logging.debug("Browser already initialized.") # Use debug for less important info
            return

        playwright = await async_playwright().start()
        window_width = 900
        window_height = 1000

        chrome_executable_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        logging.info("Initializing browser...") # <-- Use logging
        logging.info(f"Attempting to launch Chrome from: {chrome_executable_path}")
        try:
            self.browser = await playwright.chromium.launch(
                executable_path=chrome_executable_path,
                headless=False,
                args=[
                    f"--window-size={window_width},{window_height}",
                    # '--disable-gpu',
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            logging.info("Launched successfully using specified Chrome executable.") # <-- Use logging
        except Exception as e:
            logging.error(f"Failed to launch Chrome using specified path! Error: {e}", exc_info=True) # Log the full error
            logging.info("Falling back to default Chromium launch.")
            try:
                # Fallback logic - make sure this also logs!
                 self.browser = await playwright.chromium.launch(
                    headless=False,
                    args=[
                        f"--window-size={window_width},{window_height}",
                        "--disable-gpu",
                        "--disable-blink-features=AutomationControlled",
                    ],
                    chromium_sandbox=False, # Add if needed
                 )
                 logging.info("Launched successfully using default Chromium fallback.")
            except Exception as fallback_e:
                 logging.critical("FATAL: Failed to launch browser using fallback Chromium!", exc_info=True) # Very bad if this fails
                 raise fallback_e # Stop server if browser can't launch

        # --- Context, Page, Cookies, Headers ---
        logging.info("Creating browser context...")
        self.context = await self.browser.new_context(
             viewport={"width": window_width, "height": window_height},
             user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
         )
        await self.load_cookies() # Already logs inside
        logging.info("Creating new page...")
        self.page = await self.context.new_page()
        logging.info("Setting extra HTTP headers...")
        await self.page.set_extra_http_headers({
             'Accept-Language': 'en-US,en;q=0.9',
             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
         })

        # --- Add logging for page errors too ---
        def handle_page_error(error):
            logging.error(f"FATAL PAGE ERROR (JavaScript): {error}")
        self.page.on("pageerror", handle_page_error)

        def handle_console_message(msg):
            # Log console errors/warnings from the browser page
            if msg.type.lower() in ['error', 'warning']:
                logging.warning(f"BROWSER CONSOLE [{msg.type.upper()}]: {msg.text}")
        self.page.on("console", handle_console_message)
        # ------------------------------------------

        logging.info("Browser and page initialization complete.")

    async def close(self):
        if self.browser:
            await self.browser.close()
            self.browser = None

    async def wait_for_selector(
        self, selector: str, timeout: int = 30000
    ) -> Optional[any]:  # Default 30 secs now!
        try:
            # Waiting for 'visible' is usually a good bet for interactable elements
            print(f"Waiting for selector '{selector}' to be visible...")
            element = await self.page.wait_for_selector(
                selector, state="visible", timeout=timeout
            )
            print(f"Selector '{selector}' found!")
            return element
        except (
            Exception
        ) as e:  # Catching Playwright's TimeoutError is more specific if you like
            print(f"OMG, Timeout or error waiting for selector '{selector}': {e}")
            # Maybe take a screenshot when it fails? Totally helps debug!
            # await self.capture_screenshot(f"error_wait_for_{selector.replace(':', '_').replace(' ', '_')}")
            return None

    async def capture_screenshot(self, prefix: str) -> str:
        """Capture a screenshot with a given prefix"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = os.path.join(self.screenshots_dir, filename)
        await self.page.screenshot(path=filepath)
        return filepath

    async def like_post(self, post_url: str) -> str:
        """Like a post given its URL with natural behavior"""
        # First perform some natural interactions
        await self.simulate_natural_interaction()

        await self.page.goto(post_url)
        await self.page.wait_for_load_state("networkidle")

        # Scroll the post into view naturally
        await self.simulate_human_scroll(1, 2)
        screenshot_path = await self.capture_screenshot("post")

        like_button = await self.wait_for_selector('article svg[aria-label="Like"]')
        if like_button:
            # Random delay before liking (0.5 to 2 seconds)
            await asyncio.sleep(random.uniform(0.5, 2))
            await like_button.click()
            return f"Post liked successfully. Screenshot saved at: {screenshot_path}"
        return f"Could not find like button. Screenshot saved at: {screenshot_path}"

    async def comment_on_post(self, post_url: str, comment_text: str) -> str:
        """Comment on a post with natural behavior"""
        # First perform some natural interactions
        await self.simulate_natural_interaction()

        await self.page.goto(post_url)
        await self.page.wait_for_load_state("networkidle")

        # Scroll the post into view naturally
        await self.simulate_human_scroll(1, 2)
        screenshot_path = await self.capture_screenshot("post")

        # Click comment button to open comment section
        comment_button = await self.wait_for_selector('svg[aria-label="Comment"]')
        if comment_button:
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await comment_button.click()

        # Find and fill comment textarea
        comment_input = await self.wait_for_selector(
            'textarea[aria-label="Add a comment…"]'
        )
        if comment_input:
            # Random delay before typing (0.5 to 2 seconds)
            await asyncio.sleep(random.uniform(0.5, 2))
            # Type comment with random delays between characters
            for char in comment_text:
                await comment_input.type(char, delay=random.uniform(50, 200))

            await asyncio.sleep(random.uniform(0.5, 1.5))
            await comment_input.press("Enter")
            return (
                f"Comment posted successfully. Screenshot saved at: {screenshot_path}"
            )
        return f"Could not post comment. Screenshot saved at: {screenshot_path}"

    async def open_stories(self) -> str:
        """Open the first Instagram story from the feed using a stable selector."""
        # --- Smart Navigation (Checks if already on feed) ---
        current_url = self.page.url
        if not (
            "instagram.com" in current_url
            and "/p/" not in current_url
            and "/reels/" not in current_url
        ):
            print("Not on main feed? Navigating to homepage first...")
            # Use the existing reliable access function IF AVAILABLE, otherwise basic goto
            # Assuming access_instagram is available globally or accessible somehow:
            # await access_instagram() # Ideally call the tool function if possible from here
            # Or, fallback to basic nav if direct tool call isn't easy:
            await self.page.goto(
                "https://www.instagram.com/", wait_until="domcontentloaded"
            )
            await self.wait_for_selector(
                "main[role='main']", timeout=20000
            )  # Wait for feed

        print("Looking for the first story ring button using aria-label...")

        # *** UPDATED RELIABLE SELECTOR ***
        # Targets the clickable div based on role, tabindex, and partial aria-label
        stories_button_selector = (
            'div[role="button"][aria-label^="Story by"][tabindex="0"]'
        )

        stories_button = await self.wait_for_selector(
            stories_button_selector, timeout=15000
        )  # Wait 15 secs

        if stories_button:
            print(
                f"Found story button matching selector: '{stories_button_selector}'! Clicking..."
            )
            try:
                # Maybe add a tiny hover first?
                await stories_button.hover(timeout=3000)
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await stories_button.click(timeout=5000)

                # Wait for the story viewer modal/dialog to appear. Inspect this element too!
                # Common selectors: 'div[role="dialog"]', 'section > div[role="dialog"]'
                # Let's try a generic one, refine if needed by inspecting the story view
                print("Waiting for story viewer dialog...")
                # *** UPDATED SELECTOR FOR STORY VIEWER ***
                story_viewer_selector = "section > div[role='dialog']" # More specific: dialog inside a section
                await self.page.wait_for_selector(
                    story_viewer_selector, timeout=15000, state="visible" # Keep timeout for now
                )
                print(f"Story view dialog appeared using selector '{story_viewer_selector}'!")

                await asyncio.sleep(random.uniform(0.5, 1.5))  # Let story load
                screenshot_path = await self.capture_screenshot("story_opened")
                return f"Stories opened successfully. Screenshot saved at: {screenshot_path}"
            except Exception as e:
                print(f"Error clicking story button or waiting for story view: {e}")
                await self.capture_screenshot("story_click_error")
                # Include the selector that failed in the error message
                return f"Found story button, but failed to open view (waiting for '{story_viewer_selector}'): {e}"
        else:
            print(
                f"Could not find the story button using selector: '{stories_button_selector}'. Did the feed load correctly?"
            )
            await self.capture_screenshot("story_button_not_found")
            return "Could not find the first story element to click."

    async def story_interaction(self, action: str) -> str:
        """Interact with current story with natural behavior"""
        if action not in ["like", "next", "previous", "reply"]:
            # For regular story viewing, add natural viewing behavior
            await self.simulate_story_viewing(1, 3)

        # Capture the current story while paused
        screenshot_path = await self.capture_story_screenshot()

        actions = {
            "like": 'svg[aria-label="Like"]',
            "next": 'button[aria-label="Next"]',
            "previous": 'button[aria-label="Previous"]',
            "reply": 'textarea[aria-label="Reply to story..."]',
        }

        if action not in actions:
            return f"Unknown action: {action}. Screenshot saved at: {screenshot_path}"

        element = await self.wait_for_selector(actions[action])
        if element:
            # Add random delay before action
            await asyncio.sleep(random.uniform(0.3, 1))
            await element.click()
            return f"Story {action} action performed successfully. Screenshot saved at: {screenshot_path}"
        return (
            f"Could not perform {action} action. Screenshot saved at: {screenshot_path}"
        )

    async def scroll_feed(self, amount: int = 1) -> str:
        """Scroll down in the feed"""
        for _ in range(amount):
            await self.page.evaluate("window.scrollBy(0, window.innerHeight)")
            await self.page.wait_for_timeout(1000)  # Wait for content to load
        return f"Scrolled {amount} times"

    async def pause_story(self) -> bool:
        """Pause the current story using the pause button"""
        pause_button = await self.wait_for_selector('button[aria-label="Pause"]')
        if pause_button:
            await pause_button.click()
            # Wait a moment to ensure the story is paused
            await asyncio.sleep(0.5)
            return True
        return False

    async def resume_story(self):
        """Resume the story playback"""
        play_button = await self.wait_for_selector('button[aria-label="Play"]')
        if play_button:
            await play_button.click()

    async def capture_story_screenshot(self) -> str:
        """Capture a screenshot of the current story while paused"""
        is_paused = await self.pause_story()
        if is_paused:
            try:
                screenshot_path = await self.capture_screenshot("story")
                return screenshot_path
            finally:
                # Resume story playback after screenshot
                await self.resume_story()
        else:
            # Fallback to regular screenshot if pause fails
            return await self.capture_screenshot("story")

    async def simulate_human_scroll(self, min_scrolls: int = 2, max_scrolls: int = 5):
        """Simulate human-like scrolling behavior"""
        num_scrolls = random.randint(min_scrolls, max_scrolls)
        for _ in range(num_scrolls):
            # Random scroll amount between 100 and full viewport height
            scroll_amount = random.randint(
                100, await self.page.evaluate("window.innerHeight")
            )
            await self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
            # Random pause between scrolls (0.5 to 2 seconds)
            await asyncio.sleep(random.uniform(0.5, 2))

            # Sometimes pause for a bit longer (20% chance)
            if random.random() < 0.2:
                await asyncio.sleep(random.uniform(1, 3))

    async def simulate_story_viewing(self, min_stories: int = 3, max_stories: int = 7):
        """Simulate natural story viewing behavior"""
        num_stories = random.randint(min_stories, max_stories)
        actions = [
            "next",
            "next",
            "next",
            "previous",
            "next",
        ]  # Weight towards moving forward

        for _ in range(num_stories):
            # Random viewing time for each story (2 to 5 seconds)
            await asyncio.sleep(random.uniform(2, 5))

            # Randomly choose an action with weights
            action = random.choice(actions)

            # Sometimes like a story (10% chance)
            if random.random() < 0.1:
                await self.story_interaction("like")
                await asyncio.sleep(random.uniform(0.5, 1))

            # Perform the chosen navigation action
            await self.story_interaction(action)

            # Sometimes pause the story (15% chance)
            if random.random() < 0.15:
                await self.pause_story()
                await asyncio.sleep(random.uniform(1, 3))
                await self.resume_story()

    async def skip_to_next_user_stories(self):
        """Skip to the next user's stories"""
        next_user_button = await self.wait_for_selector(
            'button[aria-label="Next user"]'
        )
        if next_user_button:
            await next_user_button.click()
            await asyncio.sleep(random.uniform(0.5, 1))
            return True
        return False

    async def simulate_natural_interaction(self):
        """Perform random natural interactions before taking actions"""
        # 70% chance to scroll feed
        if random.random() < 0.7:
            await self.simulate_human_scroll()

        # 40% chance to view stories
        if random.random() < 0.4:
            if await self.open_stories():
                await self.simulate_story_viewing()
                # 30% chance to skip to next user's stories
                if random.random() < 0.3:
                    await self.skip_to_next_user_stories()
                # Return to feed
                exit_button = await self.wait_for_selector('button[aria-label="Close"]')
                if exit_button:
                    await exit_button.click()


# Create a FastMCP server
mcp = FastMCP("instagram-server")
instagram = InstagramServer()


@mcp.tool()
async def access_instagram() -> str:
    """Access Instagram homepage quickly, using a refresh if needed."""
    await instagram.init()  # Ensures browser/page is ready
    print("Quickly navigating to Insta homepage...")
    target_url = "https://www.instagram.com/"
    try:
        # SUPER FAST Initial navigation attempt - just check if it loads DOM quickly
        await instagram.page.goto(
            target_url, wait_until="domcontentloaded", timeout=10000
        )  # 10 secs MAX for first attempt
        print("Initial page load attempt done. Quick check for main content...")

        # Check VERY briefly if the main content magically appeared (low timeout)
        main_content = await instagram.wait_for_selector(
            "main[role='main']", timeout=2000
        )  # Only wait 2 seconds!

        if main_content:
            print("Whoa! It loaded first try super fast!")
            await asyncio.sleep(0.5)  # Tiny pause
            await instagram.capture_screenshot("homepage_loaded_first_try_fast")
            return "Opened Instagram homepage successfully on first try!"

        else:
            print("Okay, didn't load instantly. Hitting refresh now...")
            # await instagram.capture_screenshot("homepage_before_reload_fast") # Optional: screenshot blankness
            # **** THE REFRESH ****
            await instagram.page.reload(
                wait_until="domcontentloaded", timeout=60000
            )  # Give reload time
            print("Page reloaded! Waiting for the main content properly this time...")

            # Wait for the main content with a reasonable timeout AFTER reload
            main_content_after_reload = await instagram.wait_for_selector(
                "main[role='main']", timeout=30000
            )  # 30 secs should be plenty

            if main_content_after_reload:
                print("Yasss! Refresh worked, page is loaded!")
                await asyncio.sleep(random.uniform(0.5, 1.5))  # Settle down
                await instagram.capture_screenshot("homepage_loaded_after_reload")
                return "Opened Instagram homepage successfully after a quick refresh!"
            else:
                print("OMG, even the refresh didn't work? Insta is ghosting us.")
                await instagram.capture_screenshot("homepage_failed_after_reload")
                return "Ugh, tried reloading the page but still couldn't see the main content."

    except Exception as e:
        print(f"Oh no! Error accessing Insta: {e}")
        try:
            await instagram.capture_screenshot("homepage_load_ERROR")
        except Exception as screen_err:
            print(f"Couldn't even take a screenshot: {screen_err}")
        return f"Error accessing Instagram homepage: {e}"


@mcp.tool()
async def like_instagram_post(post_url: str) -> str:
    """Like an Instagram post given its URL"""
    await instagram.init()
    return await instagram.like_post(post_url)


@mcp.tool()
async def comment_on_instagram_post(post_url: str, comment: str) -> str:
    """Comment on an Instagram post"""
    await instagram.init()
    return await instagram.comment_on_post(post_url, comment)


@mcp.tool()
async def view_instagram_stories() -> str:
    """Open and view Instagram stories"""
    await instagram.init()
    return await instagram.open_stories()


@mcp.tool()
async def interact_with_story(action: str) -> str:
    """Interact with current story. Actions: 'like', 'next', 'previous', 'reply'"""
    await instagram.init()
    return await instagram.story_interaction(action)


@mcp.tool()
async def scroll_instagram_feed(scrolls: int = 1) -> str:
    """Scroll down in the Instagram feed"""
    await instagram.init()
    return await instagram.scroll_feed(scrolls)


@mcp.tool()
async def close_instagram() -> str:
    """Close Instagram browser session"""
    await instagram.close()
    return "Closed Instagram session"


if __name__ == "__main__":
    mcp.run(transport="stdio")
