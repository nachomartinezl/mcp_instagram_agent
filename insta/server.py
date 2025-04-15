from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright, Page, ElementHandle # Added ElementHandle
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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', # Added logger name
    handlers=[
        logging.FileHandler(log_file), # Log to a file
        # logging.StreamHandler() # Optional: Uncomment to ALSO log to console IF run directly
    ]
)
# Get a logger instance for this module
logger = logging.getLogger(__name__)
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
        logger.info("InstagramServer instance created. Screenshots dir: %s", self.screenshots_dir)

        # --- Centralized Selectors ---
        self.selectors = {
            "main_feed_content": "main[role='main']",
            "post_like_button": 'article svg[aria-label="Like"]',
            "post_comment_button": 'svg[aria-label="Comment"]',
            "post_comment_input": 'textarea[aria-label="Add a comment…"]',
            "first_story_button": 'div[role="button"][aria-label^="Story by"][tabindex="0"]',
            "story_viewer_dialog": 'div[role="dialog"]:has(button[aria-label="Close"])',
            "story_next_button": 'button[aria-label="Next"]',
            "story_previous_button": 'button[aria-label="Previous"]',
            "story_pause_button": 'button[aria-label="Pause"]',
            "story_play_button": 'button[aria-label="Play"]',
            "story_like_button": 'svg[aria-label="Like"]', # Inside story viewer
            "story_reply_input": 'textarea[placeholder^="Reply to"]',
            "story_close_button": 'button[aria-label="Close"]',
            # Add more selectors as needed
        }
        # -----------------------------

    async def load_cookies(self):
        """Load cookies from instagram.json file"""
        if os.path.exists(self.cookies_path):
            try:
                with open(self.cookies_path, 'r') as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
                logger.info("Cookies loaded successfully from %s", self.cookies_path)
                return True
            except Exception as e:
                logger.error("Failed to load or add cookies from %s", self.cookies_path, exc_info=True)
                return False
        logger.warning("Cookie file not found at %s", self.cookies_path)
        return False

    async def snapshot_page_tree(self, output_path="page_tree.json"):
        """Take an accessibility snapshot of the *current* page and save it to JSON."""
        if not self.page:
            logger.error("Page is not initialized. Run `init()` first.")
            return False

        current_url = self.page.url # Get current URL for logging
        logger.info("Taking accessibility snapshot of current page: %s", current_url)

        try:
            snapshot = await self.page.accessibility.snapshot()

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)

            logger.info("✅ Accessibility snapshot saved to %s", output_path)
            return True
        except Exception as e:
            logger.error("Failed to take accessibility snapshot for page %s: %s", current_url, e, exc_info=True)
            return False


    async def init(self):
        if self.browser:
            logger.debug("Browser already initialized.")
            return

        playwright = await async_playwright().start()
        window_width = 900
        window_height = 1000

        chrome_executable_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

        logger.info("Initializing browser...")
        logger.info("Attempting to launch Chrome from: %s", chrome_executable_path)
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
            logger.info("Launched successfully using specified Chrome executable.")
        except Exception as e:
            logger.error("Failed to launch Chrome using specified path! Error: %s", e, exc_info=True)
            logger.info("Falling back to default Chromium launch.")
            try:
                # Fallback logic
                 self.browser = await playwright.chromium.launch(
                    headless=False,
                    args=[
                        f"--window-size={window_width},{window_height}",
                        "--disable-gpu",
                        "--disable-blink-features=AutomationControlled",
                    ],
                    chromium_sandbox=False, # Add if needed
                 )
                 logger.info("Launched successfully using default Chromium fallback.")
            except Exception as fallback_e:
                 logger.critical("FATAL: Failed to launch browser using fallback Chromium!", exc_info=True)
                 raise fallback_e # Stop server if browser can't launch

        # --- Context, Page, Cookies, Headers ---
        logger.info("Creating browser context...")
        self.context = await self.browser.new_context(
             viewport={"width": window_width, "height": window_height},
             user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
         )
        await self.load_cookies() # Already logs inside
        logger.info("Creating new page...")
        self.page = await self.context.new_page()
        logger.info("Setting extra HTTP headers...")
        await self.page.set_extra_http_headers({
             'Accept-Language': 'en-US,en;q=0.9',
             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
         })

        # --- Add logging for page errors too ---
        def handle_page_error(error):
            logger.error("FATAL PAGE ERROR (JavaScript): %s", error)
        self.page.on("pageerror", handle_page_error)

        def handle_console_message(msg):
            # Log console errors/warnings from the browser page
            if msg.type.lower() in ['error', 'warning']:
                logger.warning("BROWSER CONSOLE [%s]: %s", msg.type.upper(), msg.text)
        self.page.on("console", handle_console_message)
        # ------------------------------------------

        logger.info("Browser and page initialization complete.")

    async def close(self):
        if self.browser:
            logger.info("Closing browser...")
            await self.browser.close()
            self.browser = None
            self.context = None
            self.page = None
            logger.info("Browser closed.")
        else:
            logger.info("Browser already closed or not initialized.")

    # --- Core Interaction Helpers ---

    async def wait_for_selector(
        self, selector: str, timeout: int = 30000, state: str = "visible" # Added state param
    ) -> Optional[ElementHandle]: # Return type hint updated
        """Waits for a selector to appear and be in the specified state."""
        logger.debug("Waiting for selector '%s' to be %s (timeout: %dms)...", selector, state, timeout)
        try:
            element = await self.page.wait_for_selector(
                selector, state=state, timeout=timeout
            )
            logger.info("Selector '%s' found and is %s!", selector, state)
            return element
        except Exception as e:
            # Log error only, not warning, as timeout is a common scenario
            logger.error("Timeout or error waiting for selector '%s' (state: %s): %s", selector, state, e)
            # Consider taking screenshot on error - maybe only for non-timeout errors?
            # if "timeout" not in str(e).lower():
            #    await self.capture_screenshot(f"error_wait_for_{selector.replace(':', '_').replace(' ', '_')}")
            return None

    async def click_element(self, selector: str, description: str, timeout: int = 10000, force_click: bool = False) -> bool:
        """Waits for an element and clicks it."""
        element = await self.wait_for_selector(selector, timeout=timeout)
        if not element:
            logger.error("Could not find %s (selector: %s) to click.", description, selector)
            await self.capture_screenshot(f"click_fail_notfound_{description.replace(' ', '_')}")
            return False
        try:
            if force_click:
                 logger.warning("Attempting to force click %s (selector: %s)", description, selector)
                 await element.click(timeout=5000, force=True)
            else:
                 await element.click(timeout=5000) # Standard click timeout
            logger.info("Clicked %s successfully.", description)
            return True
        except Exception as e:
            logger.error("Error clicking %s (selector: %s): %s", description, selector, e, exc_info=True)
            await self.capture_screenshot(f"click_fail_error_{description.replace(' ', '_')}")
            return False

    async def type_into_element(self, selector: str, text: str, description: str, timeout: int = 10000) -> bool:
        """Waits for an element and types text into it character by character."""
        element = await self.wait_for_selector(selector, timeout=timeout)
        if not element:
            logger.error("Could not find %s input (selector: %s) to type into.", description, selector)
            await self.capture_screenshot(f"type_fail_notfound_{description.replace(' ', '_')}")
            return False
        try:
            logger.info("Typing into %s: '%s'", description, text)
            await element.focus(timeout=3000) # Focus before typing
            await asyncio.sleep(random.uniform(0.1, 0.3)) # Small delay after focus
            for char in text:
                await element.type(char, delay=random.uniform(50, 150)) # Adjusted delay slightly
            logger.info("Finished typing into %s.", description)
            return True
        except Exception as e:
            logger.error("Error typing into %s (selector: %s): %s", description, selector, e, exc_info=True)
            await self.capture_screenshot(f"type_fail_error_{description.replace(' ', '_')}")
            return False

    async def capture_screenshot(self, prefix: str) -> str:
        """Capture a screenshot with a given prefix and timestamp."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = os.path.join(self.screenshots_dir, filename)
        try:
            await self.page.screenshot(path=filepath)
            logger.info("Screenshot captured: %s", filepath)
            return filepath
        except Exception as e:
            logger.error("Failed to capture screenshot %s: %s", filepath, e, exc_info=True)
            return f"Error capturing screenshot: {e}"

    async def simulate_human_scroll(self, min_scrolls: int = 2, max_scrolls: int = 5):
        """Simulate human-like scrolling behavior"""
        num_scrolls = random.randint(min_scrolls, max_scrolls)
        logger.info("Simulating human scroll: %d scrolls.", num_scrolls)
        try:
            for i in range(num_scrolls):
                scroll_max = await self.page.evaluate("window.innerHeight")
                scroll_amount = random.randint(100, scroll_max if scroll_max > 100 else 500)
                await self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                pause_duration = random.uniform(0.5, 2)
                logger.debug("Scroll %d/%d: Scrolled by %dpx, pausing for %.2fs", i+1, num_scrolls, scroll_amount, pause_duration)
                await asyncio.sleep(pause_duration)
                if random.random() < 0.2:
                    long_pause = random.uniform(1, 3)
                    logger.debug("Performing additional random pause for %.2fs", long_pause)
                    await asyncio.sleep(long_pause)
            logger.info("Finished simulating human scroll.")
        except Exception as e:
            logger.error("Error during human scroll simulation: %s", e, exc_info=True)
            # No return value needed, just log the error

    # --- High-Level Actions (Posts, Feed) ---

    async def like_post(self, post_url: str) -> str:
        """Like a post given its URL with natural behavior"""
        logger.info("Attempting to like post: %s", post_url)
        await self.simulate_natural_interaction() # Perform pre-action simulation

        logger.info("Navigating to post URL: %s", post_url)
        try:
            await self.page.goto(post_url, wait_until="networkidle", timeout=45000) # Increased timeout slightly
            logger.info("Page loaded for post: %s", post_url)
        except Exception as e:
            logger.error("Failed to navigate to post URL %s: %s", post_url, e, exc_info=True)
            screenshot_path = await self.capture_screenshot(f"post_nav_fail_{post_url.split('/')[-2] if '/' in post_url else 'post'}")
            return f"Failed to navigate to post {post_url}. Screenshot: {screenshot_path}"

        await self.simulate_human_scroll(1, 2) # Scroll post into view
        screenshot_path = await self.capture_screenshot(f"post_like_view_{post_url.split('/')[-2] if '/' in post_url else 'post'}")

        like_button_selector = self.selectors['post_like_button']
        logger.info("Looking for like button with selector: %s", like_button_selector)

        # Use the helper function for clicking
        if await self.click_element(like_button_selector, "Post like button"):
            return f"Post liked successfully. Screenshot saved at: {screenshot_path}"
        else:
            # Check if already liked (e.g., Unlike button is present)
            unlike_button = await self.page.query_selector('article svg[aria-label="Unlike"]')
            if unlike_button:
                logger.warning("Post %s might already be liked (Unlike button found).", post_url)
                return f"Post already liked or like button not found. Screenshot saved at: {screenshot_path}"
            else:
                logger.warning("Could not find or click like button for post: %s", post_url)
                return f"Could not find or click like button. Screenshot saved at: {screenshot_path}"


    async def comment_on_post(self, post_url: str, comment_text: str) -> str:
        """Comment on a post with natural behavior"""
        logger.info("Attempting to comment on post: %s", post_url)
        await self.simulate_natural_interaction() # Perform pre-action simulation

        logger.info("Navigating to post URL: %s", post_url)
        try:
            await self.page.goto(post_url, wait_until="networkidle", timeout=45000)
            logger.info("Page loaded for post: %s", post_url)
        except Exception as e:
            logger.error("Failed to navigate to post URL %s: %s", post_url, e, exc_info=True)
            screenshot_path = await self.capture_screenshot(f"post_nav_fail_{post_url.split('/')[-2] if '/' in post_url else 'post'}")
            return f"Failed to navigate to post {post_url}. Screenshot: {screenshot_path}"

        await self.simulate_human_scroll(1, 2) # Scroll post into view
        screenshot_path = await self.capture_screenshot(f"comment_post_view_{post_url.split('/')[-2] if '/' in post_url else 'post'}")

        # Click comment icon first to ensure input is visible/available
        comment_icon_selector = self.selectors['post_comment_button']
        if not await self.click_element(comment_icon_selector, "Post comment icon"):
             return f"Could not click comment icon to open input. Screenshot saved at: {screenshot_path}"

        # Now find and type into the comment input area
        comment_input_selector = self.selectors['post_comment_input']
        if not await self.type_into_element(comment_input_selector, comment_text, "Comment input"):
            return f"Could not find or type into comment input area. Screenshot saved at: {screenshot_path}"

        # Press Enter to submit
        try:
            await asyncio.sleep(random.uniform(0.5, 1.5)) # Wait after typing
            await self.page.keyboard.press("Enter")
            logger.info("Pressed Enter to submit comment for post: %s", post_url)
            # TODO: Add verification here - check if comment appears?
            await asyncio.sleep(random.uniform(1.0, 2.0)) # Wait for submission
            screenshot_after = await self.capture_screenshot(f"comment_post_submitted_{post_url.split('/')[-2] if '/' in post_url else 'post'}")
            return f"Comment posted successfully. Screenshot saved at: {screenshot_after}"
        except Exception as e:
            logger.error("Error pressing Enter to submit comment for post %s: %s", post_url, e, exc_info=True)
            screenshot_error = await self.capture_screenshot(f"comment_submit_error_{post_url.split('/')[-2] if '/' in post_url else 'post'}")
            return f"Error submitting comment: {e}. Screenshot saved at: {screenshot_error}"

    async def scroll_feed(self, amount: int = 1) -> str:
        """Scroll down in the feed using JavaScript"""
        logger.info("Scrolling feed %d time(s).", amount)
        try:
            for i in range(amount):
                scroll_height = await self.page.evaluate("window.innerHeight")
                await self.page.evaluate(f"window.scrollBy(0, {scroll_height * 0.8 + random.uniform(-50, 50)})") # Scroll ~80% + randomness
                logger.debug("Scrolled down by ~%d pixels (iteration %d/%d).", scroll_height, i+1, amount)
                await self.page.wait_for_timeout(random.uniform(750, 1500)) # Wait for content to potentially load
            logger.info("Finished scrolling feed %d time(s).", amount)
            return f"Scrolled {amount} times"
        except Exception as e:
            logger.error("Error during scrolling feed: %s", e, exc_info=True)
            return f"Error scrolling feed: {e}"

    # --- Story Related Methods ---

    async def open_stories(self) -> str:
        """Opens the first story from the feed, verifying by finding the 'Next' button."""
        logger.info("Attempting to open Instagram stories...")

        # --- Smart Navigation (Checks if already on feed) ---
        current_url = self.page.url
        logger.debug("Current URL: %s", current_url)
        # Check if not on main feed (more specific check)
        is_on_feed = "instagram.com" in current_url and "/p/" not in current_url and "/reels/" not in current_url and "/explore/" not in current_url and "/direct/" not in current_url
        if not is_on_feed:
            logger.info("Not on main feed. Navigating to homepage first...")
            try:
                await self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
                if not await self.wait_for_selector(self.selectors['main_feed_content'], timeout=20000):
                    raise Exception("Main feed content did not load after navigation.")
                logger.info("Successfully navigated to homepage.")
            except Exception as e:
                logger.error("Failed to navigate to homepage before opening stories: %s", e, exc_info=True)
                await self.capture_screenshot("error_nav_to_home_for_stories")
                return f"Failed to navigate to homepage to find stories: {e}"

        # --- Click First Story Button ---
        first_story_selector = self.selectors['first_story_button']
        logger.info("Looking for the first story ring button using selector: %s", first_story_selector)
        stories_button = await self.wait_for_selector(first_story_selector, timeout=15000)

        if not stories_button:
            logger.warning("Could not find the story button. Did the feed load correctly?")
            screenshot_path = await self.capture_screenshot("story_button_not_found")
            return f"Could not find the first story element to click. Screenshot: {screenshot_path}"

        logger.info("Found story button! Clicking...")
        try:
            await stories_button.hover(timeout=3000)
            await asyncio.sleep(random.uniform(0.2, 0.5))
            await stories_button.click(timeout=5000)
            logger.info("Story button clicked.")
        except Exception as e:
            logger.error("Error clicking story button: %s", e, exc_info=True)
            screenshot_path = await self.capture_screenshot("story_click_error")
            return f"Error clicking story button: {e}. Screenshot: {screenshot_path}"

        # --- Verify Story Opened (Wait for 'Next' button) ---
        logger.info("Waiting for story 'Next' button to appear as confirmation...")
        next_button_selector = self.selectors['story_next_button']
        next_button_element = await self.wait_for_selector(next_button_selector, timeout=25000) # Generous timeout

        if next_button_element:
            logger.info("Story 'Next' button found! Story viewer likely opened successfully.")
            screenshot_path = await self.capture_screenshot("story_opened_via_next_btn")
            return f"Stories opened successfully (verified by next button). Screenshot saved at: {screenshot_path}"
        else:
            logger.error("Clicked story button, but the 'Next' story button did not appear within 25s.")
            screenshot_path = await self.capture_screenshot("story_next_button_fail")
            # Check for the dialog element just in case, for logging
            dialog_present = await self.page.query_selector(self.selectors['story_viewer_dialog'])
            logger.warning(f"Story viewer dialog element present after timeout? {dialog_present is not None}")
            return f"Clicked story button, but story viewer did not seem to load correctly (Next button missing). Screenshot: {screenshot_path}"

    async def pause_story(self) -> bool:
        """Pause the current story using the pause button"""
        logger.debug("Attempting to pause story...")
        pause_button_selector = self.selectors['story_pause_button']
        # Use a shorter timeout as the button should be immediately visible if story is playing
        pause_button = await self.wait_for_selector(pause_button_selector, timeout=2000)
        if not pause_button:
            logger.debug("Pause button not found (story might already be paused or not loaded).")
            return False # Assume not paused or button not available

        try:
            await pause_button.click(timeout=1000) # Quick click timeout
            await asyncio.sleep(0.3) # Shorter wait to confirm pause
            logger.info("Story paused.")
            return True
        except Exception as e:
            # Element might have disappeared if story ended right before click
            logger.warning("Could not click pause button (maybe story ended?): %s", e)
            return False

    async def resume_story(self) -> bool:
        """Resume the story playback using the play button"""
        logger.debug("Attempting to resume story...")
        play_button_selector = self.selectors['story_play_button']
        play_button = await self.wait_for_selector(play_button_selector, timeout=2000)
        if not play_button:
            logger.debug("Play button not found (story might already be playing or not loaded).")
            return False

        try:
            await play_button.click(timeout=1000)
            logger.info("Story resumed.")
            return True
        except Exception as e:
             logger.warning("Could not click play button: %s", e)
             return False

    async def capture_story_screenshot(self) -> str:
        """Capture a screenshot of the current story, attempting to pause first."""
        logger.info("Attempting to capture screenshot of current story...")
        was_playing = False
        # Try to pause only if the pause button is visible (implies it was playing)
        pause_button = await self.page.query_selector(self.selectors['story_pause_button'])
        is_paused = False
        if pause_button and await pause_button.is_visible(timeout=500):
             was_playing = True
             is_paused = await self.pause_story()

        screenshot_path = "Error" # Default
        try:
            if was_playing and not is_paused:
                logger.warning("Could not pause story before taking screenshot. Capturing anyway.")
            screenshot_path = await self.capture_screenshot("story_view") # Use a consistent prefix
            logger.info("Story screenshot captured successfully.")
        except Exception as e:
             logger.error("Error capturing story screenshot: %s", e, exc_info=True)
             screenshot_path = f"Error capturing story screenshot: {e}"
        finally:
            # Resume story playback only if we successfully paused it AND it was playing initially
            if is_paused and was_playing:
                await self.resume_story()
        return screenshot_path

    async def story_interaction(self, action: str) -> str:
        """Interact with current story (like, next, previous, reply) with fallbacks."""
        logger.info("Attempting story interaction: '%s'", action)

        action_map = {
            "like": {"selector": self.selectors['story_like_button'], "keyboard": None},
            "next": {"selector": self.selectors['story_next_button'], "keyboard": "ArrowRight"},
            "previous": {"selector": self.selectors['story_previous_button'], "keyboard": "ArrowLeft"},
            "reply": {"selector": self.selectors['story_reply_input'], "keyboard": None},
        }

        if action not in action_map:
            logger.warning("Unknown story action requested: '%s'", action)
            screenshot_path = await self.capture_story_screenshot() # Capture state on unknown action
            return f"Unknown action: {action}. Screenshot saved at: {screenshot_path}"

        config = action_map[action]
        selector = config["selector"]
        keyboard_key = config["keyboard"]

        # Pre-action simulation/screenshot (only for nav/like)
        if action in ["next", "previous"]:
            await self.simulate_story_viewing_single() # Simulate viewing current story briefly
        if action != "reply":
            screenshot_before = await self.capture_story_screenshot() # Capture state before action
        else:
            screenshot_before = "N/A (reply action)" # No screenshot before focusing reply

        logger.info("Looking for element for action '%s' with selector: %s", action, selector)
        # Use query_selector first for non-blocking check, then wait if needed? Or just wait.
        element = await self.wait_for_selector(selector, timeout=5000, state="attached") # Wait for attached first

        if not element:
            logger.warning("Could not find element for story action '%s' using selector.", action)
            # Try keyboard fallback immediately if applicable and element not found
            if keyboard_key:
                logger.info("Element not found, attempting keyboard fallback ('%s') for action '%s'", keyboard_key, action)
                try:
                    await self.page.keyboard.press(keyboard_key)
                    await asyncio.sleep(random.uniform(0.5, 1.0)) # Wait for potential transition
                    # TODO: Add verification here - did the story advance?
                    screenshot_path_kbd = await self.capture_screenshot(f"story_{action}_kbd_fallback")
                    return f"Story action '{action}' performed via keyboard fallback. Screenshot: {screenshot_path_kbd}"
                except Exception as kbd_e:
                    logger.error("Error performing keyboard fallback '%s' for action '%s': %s", keyboard_key, action, kbd_e)
                    screenshot_path_kbd_fail = await self.capture_screenshot(f"story_{action}_kbd_fail")
                    return f"Could not find element and keyboard fallback failed for {action}. Screenshot: {screenshot_path_kbd_fail}"
            else:
                # No keyboard fallback for this action (like, reply)
                screenshot_path_notfound = await self.capture_screenshot(f"story_{action}_notfound")
                return f"Could not find element for {action} action (no keyboard fallback). Screenshot: {screenshot_path_notfound}"

        # --- Element Found ---
        try:
            is_visible = await element.is_visible(timeout=1000) # Quick visibility check

            # Use keyboard fallback if element exists but isn't visible (for next/previous)
            if not is_visible and keyboard_key:
                logger.warning("Element for action '%s' found but not visible. Attempting keyboard fallback ('%s').", action, keyboard_key)
                await self.page.keyboard.press(keyboard_key)
                await asyncio.sleep(random.uniform(0.5, 1.0)) # Wait for potential transition
                # TODO: Add verification here - did the story advance?
                screenshot_path_kbd = await self.capture_screenshot(f"story_{action}_kbd_invisible")
                return f"Story action '{action}' performed via keyboard fallback (element invisible). Screenshot: {screenshot_path_kbd}"

            # If visible, or no keyboard fallback, proceed with click
            logger.info("Element for action '%s' found%s. Proceeding with click.", action, " and visible" if is_visible else "")
            await asyncio.sleep(random.uniform(0.3, 0.8)) # Delay before click

            if action == "reply":
                await element.click(timeout=3000) # Click to focus
                logger.info("Reply input area focused.")
                # Capture screenshot *after* focusing reply
                screenshot_path_reply = await self.capture_story_screenshot()
                return f"Story reply input focused. Screenshot saved at: {screenshot_path_reply}"
            else:
                # Use force click if it wasn't visible but no keyboard fallback was available/used
                await element.click(timeout=3000, force=not is_visible)
                logger.info("Story action '%s' performed via click%s.", action, " (forced)" if not is_visible else "")
                await asyncio.sleep(random.uniform(0.2, 0.5)) # Wait for UI update
                # TODO: Add verification here - did the story advance/like state change?
                screenshot_path_after = await self.capture_screenshot(f"story_{action}_done")
                return f"Story {action} action performed successfully. Screenshot saved at: {screenshot_path_after}"

        except Exception as e:
            logger.error("Error performing story action '%s' on found element: %s", action, e, exc_info=True)
            # Try keyboard fallback as a last resort on error if applicable
            if keyboard_key:
                 logger.warning("Click failed for '%s', attempting keyboard fallback '%s' as last resort.", action, keyboard_key)
                 try:
                     await self.page.keyboard.press(keyboard_key)
                     await asyncio.sleep(random.uniform(0.5, 1.0))
                     # TODO: Add verification here
                     screenshot_path_kbd_error = await self.capture_screenshot(f"story_{action}_kbd_on_error")
                     return f"Story action '{action}' performed via keyboard fallback after click error. Screenshot: {screenshot_path_kbd_error}"
                 except Exception as kbd_e:
                     logger.error("Keyboard fallback '%s' also failed after click error for action '%s': %s", keyboard_key, action, kbd_e)

            # If no keyboard fallback or it failed too
            screenshot_path_error = await self.capture_screenshot(f"story_{action}_error")
            return f"Error performing {action} action: {e}. Screenshot saved at: {screenshot_path_error}"


    async def simulate_story_viewing_single(self):
        """Simulate viewing a single story for a random duration, potentially pausing."""
        view_time = random.uniform(2, 5) # Adjust timing as needed
        logger.debug("Simulating viewing current story for %.2fs", view_time)

        start_time = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start_time) < view_time:
             # Check if story is paused (Play button visible)
             play_button = await self.page.query_selector(self.selectors['story_play_button'])
             is_paused = play_button and await play_button.is_visible(timeout=100)

             # Randomly pause/resume logic
             if not is_paused and random.random() < 0.05: # Lower chance per check cycle
                 logger.debug("Randomly decided to pause story during viewing simulation.")
                 await self.pause_story()
                 await asyncio.sleep(random.uniform(0.5, 1.5)) # Pause duration
                 await self.resume_story() # Attempt to resume
                 # Add remaining view time after pause/resume cycle
                 remaining_time = view_time - (asyncio.get_event_loop().time() - start_time)
                 if remaining_time > 0:
                     await asyncio.sleep(remaining_time)
                 break # Exit loop after pause cycle for simplicity

             await asyncio.sleep(0.5) # Check periodically

        # Ensure story is playing at the end if it was paused
        play_button_final = await self.page.query_selector(self.selectors['story_play_button'])
        if play_button_final and await play_button_final.is_visible(timeout=100):
            logger.debug("Ensuring story is resumed after viewing simulation.")
            await self.resume_story()


    async def simulate_story_viewing(self, min_stories: int = 3, max_stories: int = 7):
        """Simulate natural story viewing behavior across multiple stories"""
        num_stories_to_view = random.randint(min_stories, max_stories)
        logger.info("Simulating natural story viewing: aiming for %d stories.", num_stories_to_view)
        # Weighted list: more next, some previous, occasional like
        actions = ["next"] * 7 + ["previous"] * 2 + ["like"] * 1

        for i in range(num_stories_to_view):
            logger.info("Viewing simulated story %d/%d...", i+1, num_stories_to_view)

            # Check if story viewer is still open before proceeding
            story_viewer = await self.page.query_selector(self.selectors['story_viewer_dialog'])
            if not story_viewer:
                 logger.warning("Story viewer seems to have closed unexpectedly before viewing story %d. Ending simulation.", i+1)
                 break

            # Simulate viewing the current story
            await self.simulate_story_viewing_single()

            # Randomly choose an action
            action = random.choice(actions)
            logger.debug("Chosen action for story %d: '%s'", i+1, action)

            # Perform the chosen action using the robust story_interaction method
            interaction_result = await self.story_interaction(action)
            logger.debug("Interaction result for action '%s': %s", action, interaction_result)

            # Small delay after action before next loop iteration
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # Check again if viewer closed after interaction (e.g., end of all stories)
            story_viewer_after = await self.page.query_selector(self.selectors['story_viewer_dialog'])
            if not story_viewer_after:
                 logger.warning("Story viewer seems to have closed after interaction on story %d. Ending simulation.", i+1)
                 break

        logger.info("Finished simulating story viewing.")


    async def skip_to_next_user_stories(self) -> bool:
        """DEPRECATED/UNRELIABLE? Use story_interaction('next') instead.
           Attempts to skip to the next user's stories using the 'Next' button.
           Note: The 'Next' button usually handles this, making this function redundant.
        """
        logger.warning("Function 'skip_to_next_user_stories' is likely redundant. Use story_interaction('next').")
        logger.info("Attempting to skip to the next user's stories using 'Next' button...")
        next_button_selector = self.selectors['story_next_button']
        next_user_button = await self.wait_for_selector(next_button_selector, timeout=3000)

        if not next_user_button:
            logger.warning("Could not find 'Next' button to attempt skipping user.")
            return False

        try:
            await next_user_button.click(timeout=2000)
            await asyncio.sleep(random.uniform(0.5, 1)) # Wait for transition
            logger.info("Clicked 'Next', potentially skipped to next user's stories.")
            # TODO: Add verification - did the user actually change? (e.g., check username element)
            return True
        except Exception as e:
            logger.warning("Error clicking 'Next' button to skip user: %s", e)
            # Attempt keyboard fallback
            logger.info("Click failed, attempting keyboard fallback 'ArrowRight' to skip user.")
            try:
                await self.page.keyboard.press("ArrowRight")
                await asyncio.sleep(random.uniform(0.5, 1.0))
                logger.info("Keyboard fallback 'ArrowRight' successful.")
                return True
            except Exception as kbd_e:
                 logger.error("Keyboard fallback 'ArrowRight' also failed: %s", kbd_e)
                 return False


    # --- Natural Interaction Simulation ---

    async def simulate_natural_interaction(self):
        """Perform random 'natural' interactions before taking primary actions."""
        logger.info("Simulating natural interaction before main action...")
        action_taken = False # Track if any sub-action was performed

        # 70% chance to scroll feed
        if random.random() < 0.7:
            logger.info("Natural interaction: Scrolling feed.")
            await self.simulate_human_scroll(1, 3) # Scroll a bit less here
            action_taken = True
        else:
            logger.info("Natural interaction: Skipping feed scroll.")

        # 40% chance to view stories (only if not already in stories)
        story_viewer = await self.page.query_selector(self.selectors['story_viewer_dialog'])
        if not story_viewer and random.random() < 0.4:
            logger.info("Natural interaction: Attempting to view stories.")
            open_result = await self.open_stories()
            if "successfully" in open_result.lower():
                action_taken = True
                await self.simulate_story_viewing(2, 5) # View fewer stories here

                # Ensure returning to feed by closing the story viewer
                logger.info("Natural interaction: Closing story viewer after simulation.")
                close_button_selector = self.selectors['story_close_button']
                if not await self.click_element(close_button_selector, "Story close button", timeout=5000):
                     logger.warning("Could not click story viewer close button. Attempting navigation fallback.")
                     try:
                         await self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
                     except Exception as nav_e:
                         logger.error("Fallback navigation to home failed: %s", nav_e)
            else:
                logger.warning("Natural interaction: Failed to open stories, skipping story viewing simulation.")
        elif story_viewer:
            logger.info("Natural interaction: Skipping story viewing (already in stories?).")
        else:
             logger.info("Natural interaction: Skipping story viewing (random chance).")

        if not action_taken:
             logger.info("Natural interaction: No specific sub-action taken, adding small delay.")
             await asyncio.sleep(random.uniform(0.5, 1.5))

        logger.info("Finished simulating natural interaction.")


# === MCP Tool Definitions ===

mcp = FastMCP("instagram-server")
instagram = InstagramServer() # Instantiate the server class


@mcp.tool()
async def access_instagram() -> str:
    """Access Instagram homepage, ensuring the main feed content is loaded. Uses refresh if needed."""
    logger.info("Tool 'access_instagram' called.")
    await instagram.init()  # Ensures browser/page is ready

    target_url = "https://www.instagram.com/"
    main_content_selector = instagram.selectors['main_feed_content']

    try:
        logger.info("Navigating to Instagram homepage: %s", target_url)
        await instagram.page.goto(target_url, wait_until="domcontentloaded", timeout=20000) # Increased initial timeout
        logger.info("Initial page load attempt done. Checking for main content...")

        # Check if main content is already present
        main_content = await instagram.wait_for_selector(main_content_selector, timeout=15000) # Generous wait first time

        if main_content:
            logger.info("Main content loaded on first try!")
            await asyncio.sleep(random.uniform(0.5, 1.0)) # Tiny pause
            screenshot_path = await instagram.capture_screenshot("homepage_loaded_first_try")
            return f"Opened Instagram homepage successfully. Screenshot: {screenshot_path}"
        else:
            logger.info("Main content not found quickly. Attempting page refresh...")
            await instagram.capture_screenshot("homepage_before_reload")
            await instagram.page.reload(wait_until="domcontentloaded", timeout=45000) # Give reload time
            logger.info("Page reloaded. Waiting for main content again...")

            # Wait for main content after reload
            main_content_after_reload = await instagram.wait_for_selector(main_content_selector, timeout=30000)

            if main_content_after_reload:
                logger.info("Refresh successful, main content loaded!")
                await asyncio.sleep(random.uniform(0.5, 1.5)) # Settle down
                screenshot_path = await instagram.capture_screenshot("homepage_loaded_after_reload")
                return f"Opened Instagram homepage successfully after refresh. Screenshot: {screenshot_path}"
            else:
                logger.error("Main content not found even after refresh.")
                screenshot_path = await instagram.capture_screenshot("homepage_failed_after_reload")
                return f"Failed to load main content after refresh. Screenshot: {screenshot_path}"

    except Exception as e:
        logger.error("Error accessing Instagram homepage: %s", e, exc_info=True)
        screenshot_path = await instagram.capture_screenshot("homepage_load_ERROR")
        return f"Error accessing Instagram homepage: {e}. Screenshot: {screenshot_path}"


@mcp.tool()
async def like_instagram_post(post_url: str) -> str:
    """Likes an Instagram post given its URL. Includes natural interaction simulation."""
    logger.info("Tool 'like_instagram_post' called for URL: %s", post_url)
    await instagram.init()
    result = await instagram.like_post(post_url)
    logger.info("Tool 'like_instagram_post' finished. Result: %s", result)
    return result


@mcp.tool()
async def comment_on_instagram_post(post_url: str, comment: str) -> str:
    """Comments on an Instagram post given its URL and the comment text. Includes natural interaction simulation."""
    logger.info("Tool 'comment_on_instagram_post' called for URL: %s with comment: '%s'", post_url, comment)
    await instagram.init()
    result = await instagram.comment_on_post(post_url, comment)
    logger.info("Tool 'comment_on_instagram_post' finished. Result: %s", result)
    return result


@mcp.tool()
async def view_instagram_stories() -> str:
    """Opens the first Instagram story and simulates viewing several stories, leaving the viewer open."""
    logger.info("Tool 'view_instagram_stories' called.")
    await instagram.init()
    open_result = await instagram.open_stories()

    if "successfully" not in open_result.lower():
        logger.warning("Failed to open stories initially. Aborting viewing simulation.")
        return open_result # Return the error message from open_stories

    logger.info("Stories opened, now simulating viewing...")
    await instagram.simulate_story_viewing(3, 7) # Simulate viewing after opening

    logger.info("Finished story viewing simulation. Story viewer should remain open.")
    logger.info("Tool 'view_instagram_stories' finished.")
    # Return a success message indicating viewer is open
    return f"Successfully opened and simulated viewing stories. Viewer left open."


@mcp.tool()
async def interact_with_story(action: str) -> str:
    """Interacts with the currently open Instagram story.
    Valid actions: 'like', 'next', 'previous', 'reply'.
    Uses keyboard fallbacks for 'next'/'previous' if buttons are hidden."""
    logger.info("Tool 'interact_with_story' called with action: %s", action)
    await instagram.init()

    # Check if story viewer is open before attempting interaction
    story_viewer = await instagram.page.query_selector(instagram.selectors['story_viewer_dialog'])
    if not story_viewer:
        logger.warning("Attempted story interaction ('%s'), but story viewer dialog not found.", action)
        # Optional: Try opening stories first? Or just fail? Let's fail for now.
        # open_attempt = await instagram.open_stories()
        # if "successfully" not in open_attempt.lower():
        #     return f"Cannot interact with story: Story viewer is not open and failed to open stories ({open_attempt})."
        # logger.info("Opened stories before interaction attempt.")
        return "Cannot interact with story: Story viewer is not open."
    else:
        logger.info("Story viewer detected. Proceeding with interaction '%s'.", action)

    result = await instagram.story_interaction(action)
    logger.info("Tool 'interact_with_story' finished. Result: %s", result)
    return result

@mcp.tool()
async def close_story_viewer() -> str:
    """Closes the Instagram story viewer if it is open."""
    logger.info("Tool 'close_story_viewer' called.")
    await instagram.init()

    story_viewer = await instagram.page.query_selector(instagram.selectors['story_viewer_dialog'])
    if not story_viewer:
        logger.info("Story viewer is not currently open.")
        return "Story viewer was not open."

    logger.info("Attempting to close story viewer...")
    close_button_selector = instagram.selectors['story_close_button']
    if await instagram.click_element(close_button_selector, "Story close button", timeout=5000):
        await asyncio.sleep(0.5) # Wait briefly for close animation
        return "Story viewer closed successfully."
    else:
        logger.error("Failed to find or click the story viewer close button.")
        # Attempt fallback navigation just in case
        try:
            await instagram.page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=20000)
            return "Failed to click close button, but navigated back to homepage as fallback."
        except Exception as nav_e:
            logger.error("Fallback navigation to home also failed: %s", nav_e)
            return "Failed to click close button and failed to navigate back to home."


@mcp.tool()
async def scroll_instagram_feed(scrolls: int = 1) -> str:
    """Scrolls down in the Instagram feed a specified number of times."""
    logger.info("Tool 'scroll_instagram_feed' called with scrolls: %d", scrolls)
    await instagram.init()
    # Ensure not in story viewer before scrolling feed
    story_viewer = await instagram.page.query_selector(instagram.selectors['story_viewer_dialog'])
    if story_viewer:
        logger.warning("Attempted to scroll feed while story viewer is open. Closing viewer first.")
        close_result = await close_story_viewer() # Use the dedicated tool/function
        logger.info("Close story viewer result: %s", close_result)
        await asyncio.sleep(0.5) # Give time for UI to settle after closing

    result = await instagram.scroll_feed(scrolls)
    logger.info("Tool 'scroll_instagram_feed' finished. Result: %s", result)
    return result

@mcp.tool()
async def snapshot_instagram_page_tree() -> str:
    """Takes an accessibility snapshot of the *current* Instagram page and saves it to 'page_tree.json'."""
    logger.info("Tool 'snapshot_instagram_page_tree' called.")
    await instagram.init() # Ensure browser is ready

    # Define the default output path here, as the tool doesn't take it as input
    output_path = "page_tree.json"
    current_url = instagram.page.url if instagram.page else "Unknown"

    try:
        success = await instagram.snapshot_page_tree(output_path=output_path)
        if success:
            result = f"Successfully saved accessibility snapshot of current page ({current_url}) to {output_path}."
            logger.info(result)
            return result
        else:
            # The method already logs errors, but we can add context here
            result = f"Failed to take accessibility snapshot for current page ({current_url}). Check logs for details."
            logger.warning(result) # Use warning as the method logs the specific error
            return result
    except Exception as e:
        logger.error("Unexpected error in 'snapshot_instagram_page_tree' tool: %s", e, exc_info=True)
        return f"An unexpected error occurred while trying to take the snapshot: {e}"


@mcp.tool()
async def close_instagram() -> str:
    """Closes the Instagram browser session entirely."""
    logger.info("Tool 'close_instagram' called.")
    await instagram.close() # Calls the class method
    logger.info("Tool 'close_instagram' finished.")
    return "Closed Instagram browser session."


# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Starting Instagram MCP server...")
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
         logger.info("Keyboard interrupt received, stopping server.")
    except Exception as e:
        logger.critical("MCP server failed to run: %s", e, exc_info=True)
    finally:
        # Ensure browser is closed on exit
        async def close_browser_sync():
            if instagram and instagram.browser:
                logger.info("Ensuring browser is closed on server exit...")
                await instagram.close()
        asyncio.run(close_browser_sync()) # Run the async close in a sync context
        logger.info("Instagram MCP server stopped.")

