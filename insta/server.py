from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright, Page, ElementHandle, TimeoutError as PlaywrightTimeoutError # Keep ElementHandle, TimeoutError
import asyncio
from typing import Optional
import os
import json
from datetime import datetime
import random
import logging
import re # Added for filename sanitization
from urllib.parse import urlparse # Added for URL parsing

# --- Set up logging ---
log_file = "instagram_server.log"
logging.basicConfig(
    level=logging.INFO, # Revert back to INFO, DEBUG can be noisy
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
        self.page: Optional[Page] = None # Type hint Page
        self.screenshots_dir = "instagram_screenshots"
        self.snapshots_dir = "page_snapshots"
        self.cookies_path = os.path.join(
            os.path.dirname(__file__), "cookies", "instagram.json"
        )
        # Create directories if they don't exist
        os.makedirs(self.screenshots_dir, exist_ok=True)
        os.makedirs(self.snapshots_dir, exist_ok=True)
        logger.info("InstagramServer instance created. Screenshots dir: %s, Snapshots dir: %s", self.screenshots_dir, self.snapshots_dir)

        # --- Updated Centralized Selectors ---
        self.selectors = {
            # --- Feed ---
            "main_feed_content": "main[role='main']",
            "feed_post_article": "main[role='main'] article", # Added selector for the article element
            "feed_post_more_options_button": 'article div[role="button"]:has(svg[aria-label="More options"])',
            "modal_go_to_post_button": 'button:has-text("Go to post")', # Adjusted for clarity

            # --- Post View ---
            "post_like_button": 'section span button svg[aria-label="Like"]', # Made more specific to common post structure
            "post_unlike_button": 'section span button svg[aria-label="Unlike"]', # Added unlike selector for verification
            "post_comment_button": 'section span button svg[aria-label="Comment"]', # Made more specific
            "post_comment_input": 'textarea[aria-label="Add a comment…"]', # Reverted to ellipsis version which seems common
            "post_comment_submit_button": 'div[role="button"]:has-text("Post")', # Adjusted for clarity

            # --- Stories ---
            "first_story_button": 'div[role="button"][aria-label^="Story by"][tabindex="0"]',
            "story_viewer_dialog": 'div[role="dialog"]:has(button[aria-label="Close"])',
            # Next/Previous buttons often don't have reliable selectors other than aria-label, keep original robust ones
            "story_next_button": 'button[aria-label="Next"]',
            "story_previous_button": 'button[aria-label="Previous"]',
            # Pause/Play selectors updated based on user input structure
            "story_pause_button": 'div[role="dialog"] div[role="button"]:has(svg[aria-label="Pause"])',
            "story_play_button": 'div[role="dialog"] div[role="button"]:has(svg[aria-label="Play"])',
            # Like button selector updated based on user input structure
            "story_like_button": 'div[role="dialog"] span svg[aria-label="Like"]', # Assuming Like is SVG label, not button
            "story_unlike_button": 'div[role="dialog"] span svg[aria-label="Unlike"]', # Added unlike for verification
            "story_reply_input": 'div[role="dialog"] textarea[placeholder^="Reply to"]',
            "story_close_button": 'div[role="dialog"] button[aria-label="Close"]',
        }
        # -----------------------------

    # --- Helper to ensure page exists ---
    def _ensure_page(self) -> Page:
        """Helper to ensure self.page is initialized."""
        if not self.page:
            logger.error("FATAL: self.page is not initialized.")
            raise ValueError("Page object is not initialized. Call init() first.")
        return self.page

    async def load_cookies(self):
        """Load cookies from instagram.json file"""
        if not self.context:
             logger.error("Cannot load cookies, browser context not initialized.")
             return False
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

    def _sanitize_filename(self, name: str) -> str:
        """Removes or replaces characters unsafe for filenames."""
        name = name.strip()
        name = name.replace('/', '_').replace('\\', '_')
        name = re.sub(r'[<>:"|?*]', '', name)
        name = re.sub(r'_+', '_', name)
        name = name.strip('_')
        return name or "unknown"

    async def snapshot_page_tree(self, output_dir: Optional[str] = None) -> Optional[str]:
        """Takes an accessibility snapshot of the current page and saves it."""
        page = self._ensure_page
        target_dir = output_dir or self.snapshots_dir
        os.makedirs(target_dir, exist_ok=True)

        current_url = page.url
        logger.info("Attempting to take accessibility snapshot of current page: %s", current_url)

        identifier = "unknown_page"
        try:
            parsed_url = urlparse(current_url)
            path_parts = [part for part in parsed_url.path.split('/') if part]
            if not path_parts: identifier = "feed"
            elif path_parts[0] == 'p' and len(path_parts) > 1: identifier = f"post_{path_parts[1]}"
            elif path_parts[0] == 'stories' and len(path_parts) > 1: identifier = f"stories_{path_parts[1]}"
            elif path_parts[0] == 'explore': identifier = "explore"
            elif path_parts[0] == 'direct': identifier = "direct"
            elif len(path_parts) == 1: identifier = f"profile_{path_parts[0]}"
            else: identifier = path_parts[0]
        except Exception as parse_e:
            logger.warning("Could not parse URL '%s' for filename identifier: %s. Using default.", current_url, parse_e)
            identifier = "parse_error"

        sanitized_identifier = self._sanitize_filename(identifier)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{sanitized_identifier}_{timestamp}.json"
        full_output_path = os.path.join(target_dir, filename)

        logger.info("Saving snapshot to: %s", full_output_path)
        try:
            snapshot = await page.accessibility.snapshot()
            with open(full_output_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
            logger.info("✅ Accessibility snapshot saved successfully.")
            return full_output_path
        except Exception as e:
            logger.error("Failed to take or save accessibility snapshot to %s: %s", full_output_path, e, exc_info=True)
            return None

    async def init(self):
        if self.browser:
            logger.debug("Browser already initialized.")
            return

        playwright = await async_playwright().start()
        window_width = 900
        window_height = 1000

        # TODO: Move to config/env vars
        chrome_executable_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'

        logger.info("Initializing browser...")
        logger.info("Attempting to launch Chrome from: %s", chrome_executable_path)
        try:
            self.browser = await playwright.chromium.launch(
                executable_path=chrome_executable_path,
                headless=False,
                args=[f"--window-size={window_width},{window_height}", "--disable-blink-features=AutomationControlled"],
            )
            logger.info("Launched successfully using specified Chrome executable.")
        except Exception as e:
            logger.error("Failed to launch Chrome using specified path! Error: %s", e, exc_info=True)
            logger.info("Falling back to default Chromium launch.")
            try:
                 self.browser = await playwright.chromium.launch(
                    headless=False,
                    args=[f"--window-size={window_width},{window_height}", "--disable-gpu", "--disable-blink-features=AutomationControlled"],
                    chromium_sandbox=False,
                 )
                 logger.info("Launched successfully using default Chromium fallback.")
            except Exception as fallback_e:
                 logger.critical("FATAL: Failed to launch browser using fallback Chromium!", exc_info=True)
                 raise fallback_e

        logger.info("Creating browser context...")
        self.context = await self.browser.new_context(
             viewport={"width": window_width, "height": window_height}, user_agent=user_agent
         )
        await self.load_cookies()
        logger.info("Creating new page...")
        self.page = await self.context.new_page()
        logger.info("Setting extra HTTP headers...")
        await self.page.set_extra_http_headers({
             'Accept-Language': 'en-US,en;q=0.9',
             'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
         })

        def handle_page_error(error): logger.error("FATAL PAGE ERROR (JavaScript): %s", error)
        self.page.on("pageerror", handle_page_error)
        def handle_console_message(msg):
            if msg.type.lower() in ['error', 'warning']: logger.warning("BROWSER CONSOLE [%s]: %s", msg.type.upper(), msg.text)
        self.page.on("console", handle_console_message)

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

    # --- Core Interaction Helpers (using Selectors) ---

    async def wait_for_selector(
        self, selector: str, description: str, timeout: int = 15000, state: str = "visible"
    ) -> Optional[ElementHandle]:
        """Waits for a selector to appear and be in the specified state."""
        page = self._ensure_page()
        logger.debug("Waiting for %s ('%s') to be %s (timeout: %dms)...", description, selector, state, timeout)
        try:
            element = await page.wait_for_selector(selector, state=state, timeout=timeout)
            logger.info("Selector for %s ('%s') found and is %s!", description, selector, state)
            return element
        except PlaywrightTimeoutError:
            logger.error("Timeout waiting for %s ('%s') to be %s.", description, selector, state)
            # await self.capture_screenshot(f"wait_fail_{description.replace(' ', '_')}")
            return None
        except Exception as e:
            logger.error("Error waiting for %s ('%s', state: %s): %s", description, selector, state, e, exc_info=True)
            # await self.capture_screenshot(f"wait_error_{description.replace(' ', '_')}")
            return None

    async def click_element(self, selector: str, description: str, timeout: int = 10000, force_click: bool = False, **kwargs) -> bool:
        """Waits for an element and clicks it."""
        element = await self.wait_for_selector(selector, description, timeout=timeout) # Use internal timeout
        if not element:
            # wait_for_selector already logged the error
            await self.capture_screenshot(f"click_fail_notfound_{description.replace(' ', '_')}")
            return False
        try:
            logger.debug("Attempting to click %s ('%s')...", description, selector)
            if force_click:
                 logger.warning("Attempting to force click %s ('%s')", description, selector)
                 await element.click(timeout=5000, force=True, **kwargs) # Shorter click timeout
            else:
                 await element.click(timeout=5000, **kwargs) # Shorter click timeout
            logger.info("Clicked %s successfully.", description)
            return True
        except PlaywrightTimeoutError:
             logger.error("Timeout trying to click %s ('%s').", description, selector)
             await self.capture_screenshot(f"click_timeout_{description.replace(' ', '_')}")
             return False
        except Exception as e:
            logger.error("Error clicking %s ('%s'): %s", description, selector, e, exc_info=True)
            await self.capture_screenshot(f"click_error_{description.replace(' ', '_')}")
            return False

    async def type_into_element(self, selector: str, text: str, description: str, timeout: int = 10000, type_delay: int = 100) -> bool:
        """Waits for an element, focuses, and types text into it character by character."""
        element = await self.wait_for_selector(selector, description, timeout=timeout)
        if not element:
            await self.capture_screenshot(f"type_fail_notfound_{description.replace(' ', '_')}")
            return False
        try:
            logger.debug("Attempting to type into %s ('%s')...", description, selector)
            await element.focus(timeout=3000)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            logger.info("Typing into %s: '%s'", description, text)
            for char in text:
                 await element.type(char, delay=random.uniform(type_delay * 0.5, type_delay * 1.5))
            logger.info("Finished typing into %s.", description)
            return True
        except PlaywrightTimeoutError:
             logger.error("Timeout trying to type into %s ('%s').", description, selector)
             await self.capture_screenshot(f"type_timeout_{description.replace(' ', '_')}")
             return False
        except Exception as e:
            logger.error("Error typing into %s ('%s'): %s", description, selector, e, exc_info=True)
            await self.capture_screenshot(f"type_error_{description.replace(' ', '_')}")
            return False

    async def capture_screenshot(self, prefix: str) -> str:
        """Capture a screenshot with a given prefix and timestamp."""
        page = self._ensure_page()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = os.path.join(self.screenshots_dir, filename)
        try:
            await page.screenshot(path=filepath)
            logger.info("Screenshot captured: %s", filepath)
            return filepath
        except Exception as e:
            logger.error("Failed to capture screenshot %s: %s", filepath, e, exc_info=True)
            return f"Error capturing screenshot: {e}"

    async def simulate_human_scroll(self, min_scrolls: int = 1, max_scrolls: int = 3):
        """Simulate human-like scrolling behavior (reduced default scrolls)."""
        page = self._ensure_page()
        num_scrolls = random.randint(min_scrolls, max_scrolls)
        logger.info("Simulating human scroll: %d scrolls.", num_scrolls)
        try:
            for i in range(num_scrolls):
                scroll_max = await page.evaluate("window.innerHeight")
                scroll_amount = random.randint(100, scroll_max if scroll_max > 100 else 500)
                await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                pause_duration = random.uniform(0.5, 1.5) # Shorter pause
                logger.debug("Scroll %d/%d: Scrolled by %dpx, pausing for %.2fs", i+1, num_scrolls, scroll_amount, pause_duration)
                await asyncio.sleep(pause_duration)
            logger.info("Finished simulating human scroll.")
        except Exception as e:
            logger.error("Error during human scroll simulation: %s", e, exc_info=True)

    # --- Feed Actions ---

    async def open_first_post_from_feed(self) -> str:
        """Clicks 'More options' on the first post in the feed, then 'Go to post'."""
        page = self._ensure_page()
        logger.info("Attempting to open the first post from the feed via 'More options' -> 'Go to post'.")

        # Ensure we are on the feed
        if not await self.wait_for_selector(self.selectors['main_feed_content'], "Main feed content"):
            return "Error: Could not confirm main feed content is loaded."

        # Find the first post's 'More options' button
        more_options_selector = self.selectors['feed_post_more_options_button']
        # We need to target the *first* article's button
        first_article_selector = self.selectors['feed_post_article']
        first_article = await self.wait_for_selector(first_article_selector, "First post article", state="attached")
        if not first_article:
            return "Error: Could not find the first post article element."

        # Locate the button within the first article
        more_options_button = await first_article.query_selector(more_options_selector)
        if not more_options_button:
             logger.error("Could not find 'More options' button within the first post.")
             await self.capture_screenshot("feed_more_options_not_found")
             return "Error: Could not find 'More options' button on the first post."

        logger.info("Found 'More options' button on the first post. Clicking...")
        try:
            await more_options_button.click(timeout=5000)
        except Exception as e:
            logger.error("Error clicking 'More options' button: %s", e, exc_info=True)
            await self.capture_screenshot("feed_more_options_click_error")
            return f"Error clicking 'More options' button: {e}"

        # Click 'Go to post' in the modal
        go_to_post_selector = self.selectors['modal_go_to_post_button']
        if await self.click_element(go_to_post_selector, "'Go to post' button", timeout=5000):
            await page.wait_for_load_state("networkidle", timeout=20000) # Wait for navigation
            current_url = page.url
            logger.info("Successfully navigated to post: %s", current_url)
            screenshot = await self.capture_screenshot("post_opened_from_feed")
            return f"Successfully opened post from feed. Current URL: {current_url}. Screenshot: {screenshot}"
        else:
            # click_element logs error and takes screenshot
            return "Error: Could not click 'Go to post' button in the modal."

    # --- Post Actions ---

    async def like_post(self, post_url: Optional[str] = None) -> str:
        """Likes the currently open post, or navigates to post_url first."""
        page = self._ensure_page()
        action_description = f"like post at {post_url}" if post_url else "like current post"
        logger.info(f"Attempting to {action_description}...")

        if post_url:
            logger.info("Navigating to post URL: %s", post_url)
            try:
                await page.goto(post_url, wait_until="networkidle", timeout=45000)
                logger.info("Page loaded for post: %s", post_url)
            except Exception as e:
                logger.error("Failed to navigate to post URL %s: %s", post_url, e, exc_info=True)
                screenshot_path = await self.capture_screenshot(f"post_nav_fail_{post_url.split('/')[-2] if post_url and '/' in post_url else 'post'}")
                return f"Failed to navigate to post {post_url}. Screenshot: {screenshot_path}"
        else:
            logger.info("Attempting to like the post on the current page.")
            # Optional: Add check to verify we are on a post page?

        await self.simulate_human_scroll(1, 1) # Scroll slightly
        screenshot_path = await self.capture_screenshot(f"post_like_view_{page.url.split('/')[-2] if '/' in page.url else 'post'}")

        like_button_selector = self.selectors['post_like_button']
        unlike_button_selector = self.selectors['post_unlike_button']

        # Check if already liked
        unlike_button = await page.query_selector(unlike_button_selector)
        if unlike_button and await unlike_button.is_visible(timeout=1000):
            logger.warning("Post appears to be already liked (Unlike button found).")
            return f"Post already liked. Screenshot: {screenshot_path}"

        # Find and click the like button
        logger.info("Looking for like button with selector: %s", like_button_selector)
        if await self.click_element(like_button_selector, "Post like button"):
            # Verification
            await asyncio.sleep(random.uniform(0.5, 1.0))
            unlike_button_after = await page.query_selector(unlike_button_selector)
            if unlike_button_after and await unlike_button_after.is_visible(timeout=2000):
                logger.info("Verified post liked successfully (Unlike button appeared).")
                return f"Post liked successfully. Screenshot: {screenshot_path}"
            else:
                logger.warning("Clicked like, but Unlike button did not appear.")
                screenshot_verify_fail = await self.capture_screenshot("post_like_verify_fail")
                return f"Clicked like, but verification failed. Screenshot: {screenshot_verify_fail}"
        else:
            # click_element logs error and takes screenshot
            return f"Could not find or click like button. Screenshot: {screenshot_path}"

    async def comment_on_post(self, comment_text: str, post_url: Optional[str] = None) -> str:
        """Comments on the currently open post, or navigates to post_url first."""
        page = self._ensure_page()
        action_description = f"comment on post at {post_url}" if post_url else "comment on current post"
        logger.info(f"Attempting to {action_description} with text: '{comment_text}'")

        if post_url:
            logger.info("Navigating to post URL: %s", post_url)
            try:
                await page.goto(post_url, wait_until="networkidle", timeout=45000)
                logger.info("Page loaded for post: %s", post_url)
            except Exception as e:
                logger.error("Failed to navigate to post URL %s: %s", post_url, e, exc_info=True)
                screenshot_path = await self.capture_screenshot(f"post_nav_fail_{post_url.split('/')[-2] if post_url and '/' in post_url else 'post'}")
                return f"Failed to navigate to post {post_url}. Screenshot: {screenshot_path}"
        else:
             logger.info("Attempting to comment on the post on the current page.")
             # Optional: Add check to verify we are on a post page?

        await self.simulate_human_scroll(1, 1) # Scroll slightly
        screenshot_path = await self.capture_screenshot(f"comment_post_view_{page.url.split('/')[-2] if '/' in page.url else 'post'}")

        # Click comment button/icon first (optional, sometimes input is directly available)
        comment_button_selector = self.selectors['post_comment_button']
        logger.debug("Attempting to click comment button/icon first (selector: %s)", comment_button_selector)
        # Don't fail if this click doesn't work, input might be visible anyway
        await self.click_element(comment_button_selector, "Post comment button/icon", timeout=3000)

        # Type into the comment input area
        comment_input_selector = self.selectors['post_comment_input']
        if not await self.type_into_element(comment_input_selector, comment_text, "Comment input"):
            # type_into_element logs error and takes screenshot
            return f"Could not find or type into comment input area."

        # Click the Post button
        post_button_selector = self.selectors['post_comment_submit_button']
        if await self.click_element(post_button_selector, "Comment post button", timeout=5000):
            logger.info("Clicked 'Post' button to submit comment.")
            # TODO: Add verification here - check if comment appears?
            await asyncio.sleep(random.uniform(1.5, 2.5)) # Wait for submission
            screenshot_after = await self.capture_screenshot(f"comment_post_submitted_{page.url.split('/')[-2] if '/' in page.url else 'post'}")
            return f"Comment posted successfully. Screenshot saved at: {screenshot_after}"
        else:
            # click_element logs error and takes screenshot
            return f"Could not click 'Post' button to submit comment."

    # --- Story Actions ---

    async def open_stories(self) -> str:
        """Opens the first story from the feed."""
        page = self._ensure_page()
        logger.info("Attempting to open Instagram stories...")

        current_url = page.url
        is_on_feed = "instagram.com" in current_url and "/p/" not in current_url and "/reels/" not in current_url and "/explore/" not in current_url and "/direct/" not in current_url
        if not is_on_feed:
            logger.info("Not on main feed. Navigating to homepage first...")
            try:
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
                if not await self.wait_for_selector(self.selectors['main_feed_content'], "Main feed content", timeout=20000):
                    raise Exception("Main feed content did not load after navigation.")
                logger.info("Successfully navigated to homepage.")
            except Exception as e:
                logger.error("Failed to navigate to homepage before opening stories: %s", e, exc_info=True)
                await self.capture_screenshot("error_nav_to_home_for_stories")
                return f"Failed to navigate to homepage to find stories: {e}"

        first_story_selector = self.selectors['first_story_button']
        logger.info("Looking for the first story ring button...")
        if not await self.click_element(first_story_selector, "First story button", timeout=15000):
            return "Could not find or click the first story element." # click_element logs and screenshots

        logger.info("Waiting for story viewer dialog to appear...")
        story_dialog_selector = self.selectors['story_viewer_dialog']
        if await self.wait_for_selector(story_dialog_selector, "Story viewer dialog", timeout=25000):
            logger.info("Story viewer dialog appeared successfully.")
            screenshot_path = await self.capture_screenshot("story_opened")
            # Maybe navigate one step to ensure it's working
            await self.next_story()
            await asyncio.sleep(0.5)
            return f"Stories opened successfully. Screenshot saved at: {screenshot_path}"
        else:
            logger.error("Clicked story button, but the story viewer dialog did not appear within 25s.")
            screenshot_path = await self.capture_screenshot("story_dialog_fail")
            return f"Clicked story button, but story viewer did not seem to load correctly. Screenshot: {screenshot_path}"

    async def _check_story_viewer_open(self) -> bool:
        """Internal helper to check if the story viewer seems to be open."""
        page = self._ensure_page()
        story_dialog = await page.query_selector(self.selectors['story_viewer_dialog'])
        if story_dialog and await story_dialog.is_visible(timeout=1000):
            return True
        logger.warning("Story viewer does not appear to be open.")
        return False

    async def next_story(self) -> str:
        """Goes to the next story using the keyboard arrow."""
        page = self._ensure_page()
        logger.info("Attempting to go to next story (using ArrowRight)...")
        if not await self._check_story_viewer_open():
            return "Cannot go to next story: Story viewer not open."
        try:
            await page.keyboard.press("ArrowRight")
            await asyncio.sleep(random.uniform(0.5, 1.0)) # Wait for transition
            logger.info("Pressed ArrowRight for next story.")
            # No easy verification here without knowing story IDs/usernames
            return "Navigated to next story (using ArrowRight)."
        except Exception as e:
            logger.error("Error pressing ArrowRight for next story: %s", e, exc_info=True)
            return f"Error navigating to next story: {e}"

    async def previous_story(self) -> str:
        """Goes to the previous story using the keyboard arrow."""
        page = self._ensure_page()
        logger.info("Attempting to go to previous story (using ArrowLeft)...")
        if not await self._check_story_viewer_open():
            return "Cannot go to previous story: Story viewer not open."
        try:
            await page.keyboard.press("ArrowLeft")
            await asyncio.sleep(random.uniform(0.5, 1.0)) # Wait for transition
            logger.info("Pressed ArrowLeft for previous story.")
            return "Navigated to previous story (using ArrowLeft)."
        except Exception as e:
            logger.error("Error pressing ArrowLeft for previous story: %s", e, exc_info=True)
            return f"Error navigating to previous story: {e}"

    async def pause_story(self) -> str:
        """Pauses the current story."""
        logger.info("Attempting to pause story...")
        if not await self._check_story_viewer_open():
            return "Cannot pause story: Story viewer not open."

        pause_selector = self.selectors['story_pause_button']
        play_selector = self.selectors['story_play_button']

        # Check if already paused
        play_button = await self.page.query_selector(play_selector)
        if play_button and await play_button.is_visible(timeout=500):
            logger.info("Story is already paused (Play button visible).")
            return "Story already paused."

        if await self.click_element(pause_selector, "Story pause button", timeout=3000):
            # Verification
            await asyncio.sleep(0.3)
            play_button_after = await self.page.query_selector(play_selector)
            if play_button_after and await play_button_after.is_visible(timeout=1000):
                logger.info("Verified story paused (Play button appeared).")
                return "Story paused successfully."
            else:
                logger.warning("Clicked pause, but Play button did not appear.")
                return "Clicked pause, but verification failed."
        else:
            return "Could not find or click pause button." # click_element logs error

    async def resume_story(self) -> str:
        """Resumes the current story."""
        logger.info("Attempting to resume story...")
        if not await self._check_story_viewer_open():
            return "Cannot resume story: Story viewer not open."

        play_selector = self.selectors['story_play_button']
        pause_selector = self.selectors['story_pause_button']

        # Check if already playing
        pause_button = await self.page.query_selector(pause_selector)
        if pause_button and await pause_button.is_visible(timeout=500):
            logger.info("Story is already playing (Pause button visible).")
            return "Story already playing."

        if await self.click_element(play_selector, "Story play button", timeout=3000):
             # Verification
            await asyncio.sleep(0.3)
            pause_button_after = await self.page.query_selector(pause_selector)
            if pause_button_after and await pause_button_after.is_visible(timeout=1000):
                logger.info("Verified story resumed (Pause button appeared).")
                return "Story resumed successfully."
            else:
                logger.warning("Clicked play, but Pause button did not appear.")
                return "Clicked play, but verification failed."
        else:
            return "Could not find or click play button." # click_element logs error

    async def like_story(self) -> str:
        """Likes the current story."""
        logger.info("Attempting to like current story...")
        if not await self._check_story_viewer_open():
            return "Cannot like story: Story viewer not open."

        like_selector = self.selectors['story_like_button']
        unlike_selector = self.selectors['story_unlike_button']

        # Check if already liked
        unlike_button = await self.page.query_selector(unlike_selector)
        if unlike_button and await unlike_button.is_visible(timeout=1000):
            logger.warning("Story appears to be already liked (Unlike button/icon found).")
            return "Story already liked."

        # Click the like button/icon
        if await self.click_element(like_selector, "Story like button/icon"):
            # Verification
            await asyncio.sleep(random.uniform(0.5, 1.0))
            unlike_button_after = await self.page.query_selector(unlike_selector)
            if unlike_button_after and await unlike_button_after.is_visible(timeout=2000):
                logger.info("Verified story liked successfully (Unlike button/icon appeared).")
                return "Story liked successfully."
            else:
                logger.warning("Clicked like, but Unlike button/icon did not appear.")
                screenshot_verify_fail = await self.capture_screenshot("story_like_verify_fail")
                return f"Clicked like, but verification failed. Screenshot: {screenshot_verify_fail}"
        else:
            return "Could not find or click story like button/icon." # click_element logs error

    async def reply_to_story(self, reply_text: str) -> str:
        """Replies to the current story."""
        logger.info(f"Attempting to reply to current story with text: '{reply_text}'")
        if not await self._check_story_viewer_open():
            return "Cannot reply to story: Story viewer not open."

        reply_input_selector = self.selectors['story_reply_input']

        # Type into the reply input
        if not await self.type_into_element(reply_input_selector, reply_text, "Story reply input"):
            return "Could not find or type into story reply input." # type_into_element logs error

        # Press Enter to send (assuming Enter sends the reply)
        try:
            await asyncio.sleep(random.uniform(0.3, 0.7))
            await self.page.keyboard.press("Enter")
            logger.info("Pressed Enter to send story reply.")
            # No easy verification for replies
            await asyncio.sleep(random.uniform(0.5, 1.0))
            screenshot = await self.capture_screenshot("story_reply_sent")
            return f"Story reply sent. Screenshot: {screenshot}"
        except Exception as e:
            logger.error("Error pressing Enter to send story reply: %s", e, exc_info=True)
            screenshot = await self.capture_screenshot("story_reply_send_error")
            return f"Error sending story reply: {e}. Screenshot: {screenshot}"

    async def close_story_viewer(self) -> str:
        """Closes the Instagram story viewer if it is open."""
        logger.info("Attempting to close story viewer...")
        if not await self._check_story_viewer_open():
            return "Story viewer was not open."

        close_button_selector = self.selectors['story_close_button']
        if await self.click_element(close_button_selector, "Story close button", timeout=5000):
            await asyncio.sleep(0.5) # Wait briefly for close animation
             # Verify closure
            try:
                story_dialog = await self.page.query_selector(self.selectors['story_viewer_dialog'])
                if not story_dialog or not await story_dialog.is_visible(timeout=2000):
                     logger.info("Verified story viewer closed.")
                     return "Story viewer closed successfully."
                else:
                     logger.warning("Clicked close, but story viewer still seems visible.")
                     return "Clicked close button, but viewer may still be open."
            except Exception:
                 logger.info("Story viewer likely closed (verification check failed).")
                 return "Story viewer closed successfully (verification check failed)."
        else:
            logger.error("Failed to find or click the story viewer close button.")
            # Fallback navigation removed as it might be unexpected
            return "Failed to click close button."


# === MCP Tool Definitions ===

mcp = FastMCP("instagram-server")
instagram = InstagramServer() # Instantiate the server class


@mcp.tool()
async def access_instagram() -> str:
    """Access Instagram homepage, ensuring the main feed content is loaded. Uses refresh if needed."""
    logger.info("Tool 'access_instagram' called.")
    await instagram.init()
    page = instagram.page

    target_url = "https://www.instagram.com/"
    main_content_selector = instagram.selectors['main_feed_content']

    try:
        logger.info("Navigating to Instagram homepage: %s", target_url)
        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        logger.info("Initial page load attempt done. Checking for main content...")

        if await instagram.wait_for_selector(main_content_selector, "Main feed content", timeout=15000):
            logger.info("Main content loaded on first try!")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            screenshot_path = await instagram.capture_screenshot("homepage_loaded_first_try")
            return f"Opened Instagram homepage successfully. Screenshot: {screenshot_path}"
        else:
            logger.info("Main content not found quickly. Attempting page refresh...")
            await instagram.capture_screenshot("homepage_before_reload")
            await page.reload(wait_until="domcontentloaded", timeout=45000)
            logger.info("Page reloaded. Waiting for main content again...")

            if await instagram.wait_for_selector(main_content_selector, "Main feed content", timeout=30000):
                logger.info("Refresh successful, main content loaded!")
                await asyncio.sleep(random.uniform(0.5, 1.5))
                screenshot_path = await instagram.capture_screenshot("homepage_loaded_after_reload")
                return f"Opened Instagram homepage successfully after refresh. Screenshot: {screenshot_path}"
            else:
                logger.error("Main content not found even after refresh.")
                screenshot_path = await instagram.capture_screenshot("homepage_failed_after_reload")
                return f"Failed to load main content after refresh. Screenshot: {screenshot_path}"

    except Exception as e:
        logger.error("Error accessing Instagram homepage: %s", e, exc_info=True)
        screenshot_path = "Error capturing screenshot"
        if instagram.page:
             screenshot_path = await instagram.capture_screenshot("homepage_load_ERROR")
        return f"Error accessing Instagram homepage: {e}. Screenshot: {screenshot_path}"

@mcp.tool()
async def open_first_post() -> str:
    """Opens the first post displayed in the main feed."""
    logger.info("Tool 'open_first_post' called.")
    await instagram.init()
    result = await instagram.open_first_post_from_feed()
    logger.info("Tool 'open_first_post' finished. Result: %s", result)
    return result

@mcp.tool()
async def like_current_post() -> str:
    """Likes the post currently displayed on the page."""
    logger.info("Tool 'like_current_post' called.")
    await instagram.init()
    # Call like_post without a URL to like the current page's post
    result = await instagram.like_post(post_url=None)
    logger.info("Tool 'like_current_post' finished. Result: %s", result)
    return result

@mcp.tool()
async def comment_on_current_post(comment: str) -> str:
    """Comments on the post currently displayed on the page."""
    logger.info("Tool 'comment_on_current_post' called with comment: '%s'", comment)
    await instagram.init()
    # Call comment_on_post without a URL
    result = await instagram.comment_on_post(comment_text=comment, post_url=None)
    logger.info("Tool 'comment_on_current_post' finished. Result: %s", result)
    return result

@mcp.tool()
async def view_instagram_stories() -> str:
    """Opens the first Instagram story from the feed."""
    logger.info("Tool 'view_instagram_stories' called.")
    await instagram.init()
    result = await instagram.open_stories()
    logger.info("Tool 'view_instagram_stories' finished. Result: %s", result)
    return result

@mcp.tool()
async def go_to_next_story() -> str:
    """Navigates to the next story using the right arrow key."""
    logger.info("Tool 'go_to_next_story' called.")
    await instagram.init()
    result = await instagram.next_story()
    logger.info("Tool 'go_to_next_story' finished. Result: %s", result)
    return result

@mcp.tool()
async def go_to_previous_story() -> str:
    """Navigates to the previous story using the left arrow key."""
    logger.info("Tool 'go_to_previous_story' called.")
    await instagram.init()
    result = await instagram.previous_story()
    logger.info("Tool 'go_to_previous_story' finished. Result: %s", result)
    return result

@mcp.tool()
async def pause_current_story() -> str:
    """Pauses the currently playing story."""
    logger.info("Tool 'pause_current_story' called.")
    await instagram.init()
    result = await instagram.pause_story()
    logger.info("Tool 'pause_current_story' finished. Result: %s", result)
    return result

@mcp.tool()
async def resume_current_story() -> str:
    """Resumes the currently paused story."""
    logger.info("Tool 'resume_current_story' called.")
    await instagram.init()
    result = await instagram.resume_story()
    logger.info("Tool 'resume_current_story' finished. Result: %s", result)
    return result

@mcp.tool()
async def like_current_story() -> str:
    """Likes the currently displayed story."""
    logger.info("Tool 'like_current_story' called.")
    await instagram.init()
    result = await instagram.like_story()
    logger.info("Tool 'like_current_story' finished. Result: %s", result)
    return result

@mcp.tool()
async def reply_to_current_story(reply: str) -> str:
    """Replies to the currently displayed story with the given text."""
    logger.info("Tool 'reply_to_current_story' called with reply: '%s'", reply)
    await instagram.init()
    result = await instagram.reply_to_story(reply)
    logger.info("Tool 'reply_to_current_story' finished. Result: %s", result)
    return result

@mcp.tool()
async def close_current_story_viewer() -> str:
    """Closes the Instagram story viewer if it is open."""
    logger.info("Tool 'close_current_story_viewer' called.")
    await instagram.init()
    result = await instagram.close_story_viewer()
    logger.info("Tool 'close_current_story_viewer' finished. Result: %s", result)
    return result

@mcp.tool()
async def scroll_instagram_feed(scrolls: int = 1) -> str:
    """Scrolls down in the Instagram feed a specified number of times."""
    logger.info("Tool 'scroll_instagram_feed' called with scrolls: %d", scrolls)
    await instagram.init()
    # Ensure not in story viewer before scrolling feed
    if await instagram._check_story_viewer_open():
        logger.warning("Attempted to scroll feed while story viewer is open. Closing viewer first.")
        close_result = await instagram.close_story_viewer()
        logger.info("Close story viewer result: %s", close_result)
        await asyncio.sleep(0.5)

    result = await instagram.scroll_feed(scrolls)
    logger.info("Tool 'scroll_instagram_feed' finished. Result: %s", result)
    return result

@mcp.tool()
async def snapshot_instagram_page_tree() -> str:
    """
    Takes an accessibility snapshot of the *current* Instagram page and saves it
    to a dynamically named file (e.g., page_snapshots/feed_timestamp.json) in the 'page_snapshots' directory.
    """
    logger.info("Tool 'snapshot_instagram_page_tree' called.")
    await instagram.init()

    current_url = instagram.page.url if instagram.page else "Unknown"

    try:
        snapshot_path = await instagram.snapshot_page_tree()
        if snapshot_path:
            result = f"Successfully saved accessibility snapshot of current page ({current_url}) to {snapshot_path}."
            logger.info(result)
            return result
        else:
            result = f"Failed to take accessibility snapshot for current page ({current_url}). Check logs for details."
            logger.warning(result)
            return result
    except Exception as e:
        logger.error("Unexpected error in 'snapshot_instagram_page_tree' tool: %s", e, exc_info=True)
        return f"An unexpected error occurred while trying to take the snapshot: {e}"

@mcp.tool()
async def close_instagram() -> str:
    """Closes the Instagram browser session entirely."""
    logger.info("Tool 'close_instagram' called.")
    await instagram.close()
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
        async def close_browser_sync():
            if hasattr(instagram, 'browser') and instagram.browser:
                logger.info("Ensuring browser is closed on server exit...")
                await instagram.close()
            else:
                logger.info("Browser already closed or not initialized on exit.")
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                 loop.create_task(close_browser_sync())
            else:
                 asyncio.run(close_browser_sync())
        except RuntimeError:
             asyncio.run(close_browser_sync())
        logger.info("Instagram MCP server stopped.")
