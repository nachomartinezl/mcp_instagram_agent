import json
import os
import re
import asyncio
import random
import logging
from typing import Optional
from urllib.parse import urlparse
from datetime import datetime

# Playwright imports
from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Locator,
    ElementHandle,  # Although ElementHandle is less used with Locators, keep if needed for specific cases
    async_playwright,
)

# MCP import (assuming this path is correct for your project)
from mcp.server.fastmcp import FastMCP

# --- Set up logging ---
log_file = "instagram_server.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
        # logging.StreamHandler() # Optional: Log to console
    ],
)
logger = logging.getLogger(__name__)
# ---------------------


class InstagramServer:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page: Optional[Page] = None
        self.screenshots_dir = "instagram_screenshots"
        self.snapshots_dir = "page_snapshots"
        self.cookies_path = os.path.join(
            os.path.dirname(__file__), "cookies", "instagram.json"
        )
        os.makedirs(self.screenshots_dir, exist_ok=True)
        os.makedirs(self.snapshots_dir, exist_ok=True)
        logger.info(
            "InstagramServer instance created. Screenshots dir: %s, Snapshots dir: %s",
            self.screenshots_dir,
            self.snapshots_dir,
        )

        # --- Centralized Selectors (Refined) ---
        self.selectors = {
            # --- Feed ---
            "main_feed_content": "main[role='main']",
            "feed_first_post_article": "main[role='main'] article:first-of-type",  # More specific start point
            "feed_post_more_options_button_relative": 'internal:role=button[name="More options"i]',  # Relative selector for within article
            "modal_go_to_post_button": 'button:has-text("Go to post")',  # Use has-text for robustness
            # --- Post View (Scoped within article or main for single post view) ---
            # Target the button DIV containing the Like SVG
            "post_like_button": 'article div[role="button"]:has(svg[aria-label="Like"]), main div[role="button"]:has(svg[aria-label="Like"])',
             # Target the button DIV containing the Unlike SVG
            "post_unlike_button": 'article div[role="button"]:has(svg[aria-label="Unlike"]), main div[role="button"]:has(svg[aria-label="Unlike"])',
            "post_comment_button": 'article div[role="button"]:has(svg[aria-label="Comment"]), main div[role="button"]:has(svg[aria-label="Comment"])',
            "post_comment_input": 'textarea[aria-label="Add a comment…"]',
            "post_comment_submit_button": 'div[role="button"]:text-is("Post")',
            # --- Stories ---
            "first_story_button": 'div[role="button"][aria-label^="Story by"][tabindex="0"]',
            "story_next_button": 'div[role="dialog"] button[aria-label="Next"]',  # Scoped
            "story_previous_button": 'div[role="dialog"] button[aria-label="Previous"]',  # Scoped
            "story_pause_button": 'div[role="dialog"] div[role="button"]:has(svg[aria-label="Pause"])',
            "story_play_button": 'div[role="dialog"] div[role="button"]:has(svg[aria-label="Play"])',
            "story_like_button": 'div[role="dialog"] svg[aria-label="Like"]',  # Target SVG directly within dialog
            "story_unlike_button": 'div[role="dialog"] svg[aria-label="Unlike"]',
            "story_reply_input": 'div[role="dialog"] textarea[placeholder^="Reply to"]',
            "story_close_button": 'div[role="dialog"] button[aria-label="Close"]',
        }
        # -----------------------------

    def _ensure_page(self) -> Page:
        if not self.page:
            logger.error("FATAL: self.page is not initialized.")
            raise ValueError("Page object is not initialized. Call init() first.")
        return self.page

    async def load_cookies(self):
        if not self.context:
            logger.error("Cannot load cookies, browser context not initialized.")
            return False
        if os.path.exists(self.cookies_path):
            try:
                with open(self.cookies_path, "r") as f:
                    cookies = json.load(f)
                await self.context.add_cookies(cookies)
                logger.info("Cookies loaded successfully from %s", self.cookies_path)
                return True
            except Exception as e:
                logger.error(
                    "Failed to load or add cookies from %s",
                    self.cookies_path,
                    exc_info=True,
                )
                return False
        logger.warning("Cookie file not found at %s", self.cookies_path)
        return False

    def _sanitize_filename(self, name: str) -> str:
        name = name.strip()
        name = name.replace("/", "_").replace("\\", "_")
        name = re.sub(r'[<>:"|?*]', "", name)
        name = re.sub(r"_+", "_", name)
        name = name.strip("_")
        return name or "unknown"

    async def snapshot_page_tree(
        self, output_dir: Optional[str] = None
    ) -> Optional[str]:
        page = self._ensure_page()  # Corrected: Call the method
        target_dir = output_dir or self.snapshots_dir
        os.makedirs(target_dir, exist_ok=True)

        current_url = page.url
        logger.info(
            "Attempting to take accessibility snapshot of current page: %s", current_url
        )

        identifier = "unknown_page"
        try:
            parsed_url = urlparse(current_url)
            path_parts = [part for part in parsed_url.path.split("/") if part]
            if not path_parts:
                identifier = "feed"
            elif path_parts[0] == "p" and len(path_parts) > 1:
                identifier = f"post_{path_parts[1]}"
            elif path_parts[0] == "stories" and len(path_parts) > 1:
                identifier = f"stories_{path_parts[1]}"
            elif path_parts[0] == "explore":
                identifier = "explore"
            elif path_parts[0] == "direct":
                identifier = "direct"
            elif len(path_parts) == 1:
                identifier = f"profile_{path_parts[0]}"
            else:
                identifier = (
                    path_parts[0] if path_parts else "root"
                )  # Handle root case better
        except Exception as parse_e:
            logger.warning(
                "Could not parse URL '%s' for filename identifier: %s. Using default.",
                current_url,
                parse_e,
            )
            identifier = "parse_error"

        sanitized_identifier = self._sanitize_filename(identifier)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{sanitized_identifier}_{timestamp}.json"
        full_output_path = os.path.join(target_dir, filename)

        logger.info("Saving snapshot to: %s", full_output_path)
        try:
            # Consider adding waits here if needed before snapshotting
            snapshot = await page.accessibility.snapshot()
            if snapshot is None:
                logger.error("Failed to get snapshot data (snapshot is None).")
                return None
            with open(full_output_path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
            logger.info("✅ Accessibility snapshot saved successfully.")
            return full_output_path
        except Exception as e:
            logger.error(
                "Failed to take or save accessibility snapshot to %s: %s",
                full_output_path,
                e,
                exc_info=True,
            )
            return None

    async def init(self):
        # This method looks complex but generally okay, no changes needed based on selectors
        if self.browser:
            logger.debug("Browser already initialized.")
            return

        playwright = await async_playwright().start()
        window_width = 900
        window_height = 1000

        chrome_executable_path = (
            r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        )
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"

        logger.info("Initializing browser...")
        logger.info("Attempting to launch Chrome from: %s", chrome_executable_path)
        try:
            self.browser = await playwright.chromium.launch(
                executable_path=chrome_executable_path,
                headless=False,
                args=[
                    f"--window-size={window_width},{window_height}",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            logger.info("Launched successfully using specified Chrome executable.")
        except Exception as e:
            logger.error(
                "Failed to launch Chrome using specified path! Error: %s",
                e,
                exc_info=True,
            )
            logger.info("Falling back to default Chromium launch.")
            try:
                self.browser = await playwright.chromium.launch(
                    headless=False,
                    args=[
                        f"--window-size={window_width},{window_height}",
                        "--disable-gpu",
                        "--disable-blink-features=AutomationControlled",
                    ],
                    chromium_sandbox=False,
                )
                logger.info("Launched successfully using default Chromium fallback.")
            except Exception as fallback_e:
                logger.critical(
                    "FATAL: Failed to launch browser using fallback Chromium!",
                    exc_info=True,
                )
                raise fallback_e

        logger.info("Creating browser context...")
        self.context = await self.browser.new_context(
            viewport={"width": window_width, "height": window_height},
            user_agent=user_agent,
        )
        await self.load_cookies()
        logger.info("Creating new page...")
        self.page = await self.context.new_page()
        logger.info("Setting extra HTTP headers...")
        await self.page.set_extra_http_headers(
            {
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            }
        )

        def handle_page_error(error):
            logger.error("FATAL PAGE ERROR (JavaScript): %s", error)

        self.page.on("pageerror", handle_page_error)

        def handle_console_message(msg):
            if msg.type.lower() in ["error", "warning"]:
                logger.warning("BROWSER CONSOLE [%s]: %s", msg.type.upper(), msg.text)

        self.page.on("console", handle_console_message)

        logger.info("Browser and page initialization complete.")

    async def close(self):
        # This method is fine
        if self.browser:
            logger.info("Closing browser...")
            await self.browser.close()
            self.browser = None
            self.context = None
            self.page = None
            logger.info("Browser closed.")
        else:
            logger.info("Browser already closed or not initialized.")

    # --- Core Interaction Helpers (using Locators) ---
    async def _get_locator(self, selector: str, description: str) -> Optional[Locator]:
        """Gets a Playwright Locator."""
        page = self._ensure_page()
        try:
            locator = page.locator(selector)
            logger.debug("Created locator for %s ('%s')", description, selector)
            return locator
        except Exception as e:
            logger.error(
                "Error creating locator for %s ('%s'): %s",
                description,
                selector,
                e,
                exc_info=True,
            )
            return None

    async def wait_for_locator(
        self,
        locator: Locator,
        description: str,
        timeout: int = 15000,
        state: str = "visible",
    ) -> bool:
        """Waits for a locator to be in the specified state."""
        logger.debug(
            "Waiting for %s to be %s (timeout: %dms)...", description, state, timeout
        )
        try:
            await locator.wait_for(state=state, timeout=timeout)
            logger.info("%s found and is %s!", description, state)
            return True
        except PlaywrightTimeoutError:
            logger.error("Timeout waiting for %s to be %s.", description, state)
            return False
        except Exception as e:
            logger.error(
                "Error waiting for %s (state: %s): %s",
                description,
                state,
                e,
                exc_info=True,
            )
            return False

    async def click_element(
        self,
        selector: str,
        description: str,
        timeout: int = 10000,
        force_click: bool = False,
        **kwargs,
    ) -> bool:
        """Gets a locator, waits for it, and clicks it."""
        locator = await self._get_locator(selector, description)
        if not locator:
            return False

        # Use wait_for_locator for better logging/control
        if not await self.wait_for_locator(locator, description, timeout=timeout):
            await self.capture_screenshot(
                f"click_fail_notfound_{description.replace(' ', '_')}"
            )
            return False

        try:
            logger.debug("Attempting to click %s ('%s')...", description, selector)
            click_args = {"timeout": 5000, **kwargs}  # Shorter click timeout
            if force_click:
                logger.warning(
                    "Attempting to force click %s ('%s')", description, selector
                )
                click_args["force"] = True
            await locator.click(**click_args)
            logger.info("Clicked %s successfully.", description)
            return True
        except PlaywrightTimeoutError:
            logger.error("Timeout trying to click %s ('%s').", description, selector)
            await self.capture_screenshot(
                f"click_timeout_{description.replace(' ', '_')}"
            )
            return False
        except Exception as e:
            logger.error(
                "Error clicking %s ('%s'): %s", description, selector, e, exc_info=True
            )
            await self.capture_screenshot(
                f"click_error_{description.replace(' ', '_')}"
            )
            return False

    async def type_into_element(
        self,
        selector: str,
        text: str,
        description: str,
        timeout: int = 10000,
        type_delay: int = 100,
    ) -> bool:
        """Gets a locator, waits, focuses, and types into it."""
        locator = await self._get_locator(selector, description)
        if not locator:
            return False

        if not await self.wait_for_locator(locator, description, timeout=timeout):
            await self.capture_screenshot(
                f"type_fail_notfound_{description.replace(' ', '_')}"
            )
            return False

        try:
            logger.debug("Attempting to type into %s ('%s')...", description, selector)
            await locator.focus(timeout=3000)
            await asyncio.sleep(random.uniform(0.1, 0.3))
            logger.info("Typing into %s: '%s'", description, text)
            # Using fill might be faster and more reliable for textareas sometimes
            # await locator.fill(text, timeout=5000)
            # Sticking with char by char for simulation
            for char in text:
                await locator.type(
                    char, delay=random.uniform(type_delay * 0.5, type_delay * 1.5)
                )
            logger.info("Finished typing into %s.", description)
            return True
        except PlaywrightTimeoutError:
            logger.error(
                "Timeout trying to type into %s ('%s').", description, selector
            )
            await self.capture_screenshot(
                f"type_timeout_{description.replace(' ', '_')}"
            )
            return False
        except Exception as e:
            logger.error(
                "Error typing into %s ('%s'): %s",
                description,
                selector,
                e,
                exc_info=True,
            )
            await self.capture_screenshot(f"type_error_{description.replace(' ', '_')}")
            return False

    async def capture_screenshot(self, prefix: str) -> str:
        # Method looks fine
        page = self._ensure_page()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.png"
        filepath = os.path.join(self.screenshots_dir, filename)
        try:
            await page.screenshot(path=filepath)
            logger.info("Screenshot captured: %s", filepath)
            return filepath
        except Exception as e:
            logger.error(
                "Failed to capture screenshot %s: %s", filepath, e, exc_info=True
            )
            return f"Error capturing screenshot: {e}"

    async def simulate_human_scroll(self, min_scrolls: int = 1, max_scrolls: int = 3):
        # Method looks fine
        page = self._ensure_page()
        num_scrolls = random.randint(min_scrolls, max_scrolls)
        logger.info("Simulating human scroll: %d scrolls.", num_scrolls)
        try:
            for i in range(num_scrolls):
                scroll_max = await page.evaluate("window.innerHeight")
                scroll_amount = random.randint(
                    100, scroll_max if scroll_max > 100 else 500
                )
                await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                pause_duration = random.uniform(0.5, 1.5)
                logger.debug(
                    "Scroll %d/%d: Scrolled by %dpx, pausing for %.2fs",
                    i + 1,
                    num_scrolls,
                    scroll_amount,
                    pause_duration,
                )
                await asyncio.sleep(pause_duration)
            logger.info("Finished simulating human scroll.")
        except Exception as e:
            logger.error("Error during human scroll simulation: %s", e, exc_info=True)

    # --- Feed Actions ---

    async def open_first_post_from_feed(self) -> str:
        """Clicks 'More options' on the first post in the feed, then 'Go to post'."""
        page = self._ensure_page()
        logger.info(
            "Attempting to open the first post from the feed via 'More options' -> 'Go to post'."
        )

        # --- CORRECTED Check for Main Feed Content ---
        main_feed_locator = await self._get_locator(
            self.selectors["main_feed_content"], "Main feed content"
        )
        if not main_feed_locator or not await self.wait_for_locator(
            main_feed_locator, "Main feed content", timeout=15000 # Increased timeout slightly
        ):
            logger.error("Main feed content locator not found or timed out.")
            await self.capture_screenshot("main_feed_content_not_found") # Capture screenshot on failure
            return "Error: Could not confirm main feed content is loaded."
        # --- End Correction ---

        # --- Logic Using Locators ---
        first_article_locator = await self._get_locator(
            self.selectors["feed_first_post_article"], "First post article"
        )
        if not first_article_locator:
            # This check might be redundant if _get_locator handles errors, but safe to keep
            logger.error("Could not create locator for the first post article.")
            return "Error: Could not create locator for the first post article."

        # Wait for the article itself first using wait_for_locator
        if not await self.wait_for_locator(
            first_article_locator, "First post article", timeout=10000, state="visible" # Wait for visible
        ):
            await self.capture_screenshot("feed_first_article_not_found")
            return "Error: Could not find the first post article element."

        # Get the locator for the button *within* the article locator
        more_options_locator = first_article_locator.locator(
            self.selectors["feed_post_more_options_button_relative"]
        )
        logger.info("Locating 'More options' button on the first post.")

        # Wait for the button to be visible within the article
        if not await self.wait_for_locator(
            more_options_locator, "More options button (within article)", timeout=7000
        ):
            logger.error("Could not find 'More options' button within the first post.")
            await self.capture_screenshot("feed_more_options_not_found")
            return "Error: Could not find 'More options' button on the first post."

        # Click the button locator
        logger.info("Found 'More options' button. Clicking...")
        try:
            # Click the locator directly
            await more_options_locator.click(timeout=5000)
        except Exception as e:
            logger.error("Error clicking 'More options' button: %s", e, exc_info=True)
            await self.capture_screenshot("feed_more_options_click_error")
            return f"Error clicking 'More options' button: {e}"
        # --- End Logic Using Locators ---

        # Click 'Go to post' in the modal (using the existing click_element helper)
        go_to_post_selector = self.selectors["modal_go_to_post_button"]
        if await self.click_element(
            go_to_post_selector, "'Go to post' button", timeout=5000
        ):
            try:
                await page.wait_for_load_state("networkidle", timeout=20000)
            except Exception as load_e:
                logger.warning(
                    "Network idle wait timed out after clicking 'Go to post', proceeding anyway: %s",
                    load_e,
                )

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
        action_description = (
            f"like post at {post_url}" if post_url else "like current post"
        )
        logger.info(f"Attempting to {action_description}...")

        post_identifier = "post" # Default identifier
        if post_url:
            logger.info("Navigating to post URL: %s", post_url)
            try:
                await page.goto(post_url, wait_until="networkidle", timeout=45000)
                logger.info("Page loaded for post: %s", post_url)
                post_identifier = self._sanitize_filename(post_url.split('/')[-2]) if '/p/' in post_url else 'post'
            except Exception as e:
                logger.error(
                    "Failed to navigate to post URL %s: %s", post_url, e, exc_info=True
                )
                screenshot_path = await self.capture_screenshot(f"post_nav_fail_{self._sanitize_filename(post_url.split('/')[-2]) if post_url and '/p/' in post_url else 'post'}")
                return f"Failed to navigate to post {post_url}. Screenshot: {screenshot_path}"
        else:
            logger.info("Attempting to like the post on the current page.")
            post_identifier = self._sanitize_filename(page.url.split('/')[-2]) if '/p/' in page.url else 'post'


        await self.simulate_human_scroll(1, 1)
        screenshot_before_like = await self.capture_screenshot(f"post_like_view_{post_identifier}") # Capture state before attempting like

        like_button_selector = self.selectors["post_like_button"]
        unlike_button_selector = self.selectors["post_unlike_button"]

        unlike_locator = await self._get_locator(
            unlike_button_selector, "Post unlike button"
        )
        # Increase visibility check timeout slightly
        if unlike_locator and await unlike_locator.is_visible(timeout=1500):
            logger.warning("Post appears to be already liked (Unlike button found).")
            return f"Post already liked. Screenshot: {screenshot_before_like}"

        logger.info("Looking for like button using selector: %s", like_button_selector)
        # Use the updated click_element helper which uses the correct locator internally
        if await self.click_element(like_button_selector, "Post like button"):
            # INCREASED delay for UI update and potential animation
            logger.debug("Waiting after click for UI to potentially update...")
            await asyncio.sleep(random.uniform(1.5, 2.5)) # Longer delay
            # Re-fetch locator for verification, use the CORRECT unlike selector
            unlike_locator_after = await self._get_locator(
                unlike_button_selector, "Post unlike button (verify)"
            )
            # Increase verification timeout
            logger.debug("Verifying if Unlike button appeared...")
            if unlike_locator_after and await unlike_locator_after.is_visible(
                timeout=3000
            ):
                logger.info(
                    "Verified post liked successfully (Unlike button appeared)."
                )
                # Capture screenshot after successful like
                screenshot_path = await self.capture_screenshot(f"post_liked_success_{post_identifier}")
                return f"Post liked successfully. Screenshot: {screenshot_path}"
            else:
                logger.warning("Clicked like, but Unlike button did not appear or timed out.")
                screenshot_verify_fail = await self.capture_screenshot("post_like_verify_fail")
                return f"Clicked like, but verification failed. Screenshot: {screenshot_verify_fail}"
        else:
            # Error logged by click_element
            # Capture screenshot if click failed (screenshot_before_like might be more useful)
            await self.capture_screenshot(f"post_like_click_failed_{post_identifier}")
            return f"Could not find or click like button. Screenshot: {screenshot_before_like}"

    async def comment_on_post(
        self, comment_text: str, post_url: Optional[str] = None
    ) -> str:
        page = self._ensure_page()
        action_description = (
            f"comment on post at {post_url}" if post_url else "comment on current post"
        )
        logger.info(f"Attempting to {action_description} with text: '{comment_text}'")

        post_identifier = "post" # Default identifier
        if post_url:
            logger.info("Navigating to post URL: %s", post_url)
            try:
                await page.goto(post_url, wait_until="networkidle", timeout=45000)
                logger.info("Page loaded for post: %s", post_url)
                post_identifier = self._sanitize_filename(post_url.split('/')[-2]) if '/p/' in post_url else 'post'
            except Exception as e:
                logger.error(
                    "Failed to navigate to post URL %s: %s", post_url, e, exc_info=True
                )
                screenshot_path = await self.capture_screenshot(f"post_nav_fail_{self._sanitize_filename(post_url.split('/')[-2]) if post_url and '/p/' in post_url else 'post'}")
                return f"Failed to navigate to post {post_url}. Screenshot: {screenshot_path}"
        else:
            logger.info("Attempting to comment on the post on the current page.")
            post_identifier = self._sanitize_filename(page.url.split('/')[-2]) if '/p/' in page.url else 'post'


        await self.simulate_human_scroll(1, 1)
        # Optional click on comment icon (keep as is)
        comment_button_selector = self.selectors["post_comment_button"]
        logger.debug(
            "Attempting to click comment button/icon first (selector: %s)",
            comment_button_selector,
        )
        await self.click_element(
            comment_button_selector, "Post comment button/icon", timeout=3000
        )  # Optional click, don't fail if it doesn't work

        comment_input_selector = self.selectors["post_comment_input"]
        # Use type_into_element (which now uses fill by default unless you changed it back)
        if not await self.type_into_element(
            comment_input_selector, comment_text, "Comment input"
        ):
             # Screenshot taken inside type_into_element on failure
            return f"Could not find or type into comment input area."

        # *** ADDED Delay before clicking Post ***
        post_delay = random.uniform(0.6, 1.4)
        logger.debug("Pausing for %.2fs before clicking Post button...", post_delay)
        await asyncio.sleep(post_delay)

        post_button_selector = self.selectors["post_comment_submit_button"]
        if await self.click_element(
            post_button_selector, "Comment post button", timeout=5000
        ):
            logger.info("Clicked 'Post' button to submit comment.")
            # Keep existing delay after posting
            await asyncio.sleep(random.uniform(1.5, 2.5))
            screenshot_after = await self.capture_screenshot(f"comment_post_submitted_{post_identifier}")
            return (
                f"Comment posted successfully. Screenshot saved at: {screenshot_after}"
            )
        else:
             # Screenshot taken inside click_element on failure
            return f"Could not click 'Post' button to submit comment."

    # --- Story Actions ---

    async def open_stories(self) -> str:
        """Opens the first Instagram story from the feed."""
        page = self._ensure_page()
        logger.info("Attempting to open Instagram stories...")

        # --- Navigate to feed if needed (Keep this logic) ---
        # [ ... navigation logic ... ]
        current_url = page.url
        is_on_feed = (
            "instagram.com" in current_url
            and "/p/" not in current_url
            and "/stories/" not in current_url
            and "/reels/" not in current_url
            and "/explore/" not in current_url
            and "/direct/" not in current_url
        )
        if not is_on_feed:
             # [ ... navigation logic ... ]
             pass # Assume navigation happens correctly
        # --- End Navigation Logic ---


        first_story_selector = self.selectors["first_story_button"]
        logger.info("Looking for the first story ring button using selector: %s", first_story_selector)

        first_story_locator = await self._get_locator(first_story_selector, "First story button (matches multiple)")
        if not first_story_locator:
            return "Error: Could not create locator for story buttons."

        first_story_target_locator = first_story_locator.first
        logger.debug("Specifically targeting the .first() instance of the story button locator.")

        try:
            logger.debug("Waiting for the first story button to be visible...")
            if await self.wait_for_locator(first_story_target_locator, "First story button", timeout=15000):
                logger.debug("First story button is visible. Clicking...")
                await asyncio.sleep(random.uniform(0.1, 0.3))
                await first_story_target_locator.click(timeout=5000)
                logger.info("Clicked the first story element.")
                await asyncio.sleep(0.5) # Small pause after click for transition start
            else:
                await self.capture_screenshot("first_story_click_fail_notfound")
                return "Could not find the first story element after getting locator."
        except Exception as e:
            logger.error("Error clicking the first story button: %s", e, exc_info=True)
            await self.capture_screenshot("first_story_click_error")
            return f"Error clicking first story element: {e}"

        # --- REVISED WAIT: Wait for ANY essential story element with asyncio.wait ---
        # Elements that indicate the story UI is interactive and loaded
        essential_selectors = {
            "Pause": self.selectors['story_pause_button'],
            "Next": self.selectors['story_next_button'],
            "Reply": self.selectors['story_reply_input'],
            # Optional: Add Like button if it appears reliably early
            # "Like": self.selectors['story_like_button'],
        }
        wait_tasks = []
        description_map = {}

        logger.info("Creating wait tasks for essential story elements...")
        for desc, selector in essential_selectors.items():
            locator = await self._get_locator(selector, f"Story {desc} element")
            if locator:
                # Create a task for the wait_for call
                task = asyncio.create_task(locator.wait_for(state="visible", timeout=35000)) # Generous 35s timeout for the wait itself
                wait_tasks.append(task)
                description_map[task] = desc # Map task back to description
            else:
                logger.warning("Could not create locator for Story %s element ('%s')", desc, selector)

        if not wait_tasks:
             logger.error("Could not create any locators for essential story elements.")
             return "Error: Failed to create locators for story verification."

        story_loaded = False
        found_element_desc = "None"
        overall_wait_timeout = 35.0 # Total time to wait for *any* task to complete

        logger.info(f"Waiting up to {overall_wait_timeout}s for ANY essential story element to become visible...")
        try:
            # Wait for the *first* task to complete
            done, pending = await asyncio.wait(
                wait_tasks,
                timeout=overall_wait_timeout,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks to avoid resource leaks
            for task in pending:
                task.cancel()
                try:
                    await task # Allow cancellation to propagate
                except asyncio.CancelledError:
                    pass # Expected

            if done:
                # Check if the completed task finished without error
                completed_task = done.pop() # Get the first completed task
                found_element_desc = description_map.get(completed_task, "Unknown Element")
                try:
                    await completed_task # Raise exception if wait_for failed internally
                    story_loaded = True
                    logger.info(f"Detected story load via: {found_element_desc}")
                except PlaywrightTimeoutError:
                     logger.warning(f"Wait task for {found_element_desc} completed but timed out internally (should not happen with FIRST_COMPLETED unless timeout is very short).")
                except Exception as task_e:
                     logger.warning(f"Wait task for {found_element_desc} completed with an error: {task_e}")

            else: # No tasks completed, asyncio.wait timed out
                 logger.error(f"Timeout ({overall_wait_timeout}s) waiting for any essential story element.")

        except asyncio.TimeoutError: # Should be caught by the check on 'done' set, but belt-and-suspenders
             logger.error(f"Overall asyncio.wait timed out ({overall_wait_timeout}s) waiting for any essential story element.")
        except Exception as e:
             logger.error(f"Unexpected error during asyncio.wait for story elements: {e}", exc_info=True)

        # --- Final Result ---
        if story_loaded:
            logger.info(f"Story viewer content appeared successfully (confirmed by {found_element_desc}).")
            await asyncio.sleep(random.uniform(0.2, 0.5)) # Tiny delay for UI to settle fully
            screenshot_path = await self.capture_screenshot("story_opened_confirmed")
            return f"Stories opened successfully (confirmed by {found_element_desc}). Screenshot saved at: {screenshot_path}"
        else:
            logger.error(
                "Clicked story button, but essential story content did not appear within timeout."
            )
            screenshot_path = await self.capture_screenshot("story_content_final_fail")
            # Check close button as last resort
            close_button_visible = False
            close_locator = await self._get_locator(self.selectors['story_close_button'], "Story close button (fallback check)")
            if close_locator:
                 try:
                    close_button_visible = await close_locator.is_visible(timeout=500)
                 except Exception: pass
            logger.warning(f"Close button check after content failure: {'Visible' if close_button_visible else 'Not Visible'}")
            return f"Clicked story button, but story content did not load correctly. Screenshot: {screenshot_path}"
        # --- End Revised Wait ---
        
    async def _check_story_viewer_open(self) -> bool:
        """Internal helper to check if the story viewer seems to be open by looking for ANY key interactive element."""
        page = self._ensure_page()
        logger.debug("Checking if story viewer is open...")

        # Selectors to check for presence
        check_selectors = {
            "Pause": self.selectors['story_pause_button'],
            "Next": self.selectors['story_next_button'],
            "Reply": self.selectors['story_reply_input'],
            "Close": self.selectors['story_close_button'], # Include close button in check
            # Optional: Add Like button
            # "Like": self.selectors['story_like_button'],
        }
        wait_tasks = []

        for desc, selector in check_selectors.items():
            locator = await self._get_locator(selector, f"Story {desc} element (check open)")
            if locator:
                # Use is_visible() check - note: is_visible doesn't wait long inherently
                # We rely on asyncio.wait for the overall short timeout
                task = asyncio.create_task(locator.is_visible()) # is_visible itself has negligible wait
                wait_tasks.append(task)

        if not wait_tasks:
             logger.warning("Could not create any locators for story viewer check.")
             return False # Cannot check

        overall_check_timeout = 1.5 # Short overall timeout (seconds)

        found_visible = False
        try:
            # Wait for the *first* task to complete successfully (returning True)
            done, pending = await asyncio.wait(
                wait_tasks,
                timeout=overall_check_timeout,
                return_when=asyncio.FIRST_COMPLETED
            )

            # Cancel pending tasks
            for task in pending:
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass

            if done:
                completed_task = done.pop()
                try:
                    if await completed_task: # Check if is_visible returned True
                         found_visible = True
                         # Find description - requires iterating through original map or tasks if needed
                         # logger.debug("Story viewer check: An essential element is visible.")
                except Exception:
                    pass # Ignore errors from is_visible, just means that one wasn't found

        except asyncio.TimeoutError:
             pass # Timeout means none were found quickly
        except Exception as e:
             logger.warning(f"Unexpected error during asyncio.wait for story check: {e}")


        if found_visible:
            logger.debug("Story viewer check: An essential element was found. Assuming open.")
            return True
        else:
             logger.debug(f"Story viewer check: No essential elements found within {overall_check_timeout}s. Assuming closed.")
             return False

    async def next_story(self) -> str:
        # Logic looks okay (uses keyboard)
        page = self._ensure_page()
        logger.info("Attempting to go to next story (using ArrowRight)...")
        if not await self._check_story_viewer_open():
            return "Cannot go to next story: Story viewer not open."
        try:
            await page.keyboard.press("ArrowRight")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            logger.info("Pressed ArrowRight for next story.")
            return "Navigated to next story (using ArrowRight)."
        except Exception as e:
            logger.error(
                "Error pressing ArrowRight for next story: %s", e, exc_info=True
            )
            return f"Error navigating to next story: {e}"

    async def previous_story(self) -> str:
        # Logic looks okay (uses keyboard)
        page = self._ensure_page()
        logger.info("Attempting to go to previous story (using ArrowLeft)...")
        if not await self._check_story_viewer_open():
            return "Cannot go to previous story: Story viewer not open."
        try:
            await page.keyboard.press("ArrowLeft")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            logger.info("Pressed ArrowLeft for previous story.")
            return "Navigated to previous story (using ArrowLeft)."
        except Exception as e:
            logger.error(
                "Error pressing ArrowLeft for previous story: %s", e, exc_info=True
            )
            return f"Error navigating to previous story: {e}"

    async def pause_story(self) -> str:
        # Logic looks okay, ensure selector usage is correct
        logger.info("Attempting to pause story...")
        if not await self._check_story_viewer_open():
            return "Cannot pause story: Story viewer not open."

        pause_selector = self.selectors["story_pause_button"]
        play_selector = self.selectors["story_play_button"]

        play_locator = await self._get_locator(
            play_selector, "Story play button (check pause)"
        )
        if play_locator and await play_locator.is_visible(timeout=500):
            logger.info("Story is already paused (Play button visible).")
            return "Story already paused."

        if await self.click_element(pause_selector, "Story pause button", timeout=3000):
            await asyncio.sleep(0.3)
            # Re-fetch locator for verification
            play_locator_after = await self._get_locator(
                play_selector, "Story play button (verify pause)"
            )
            if play_locator_after and await play_locator_after.is_visible(timeout=1000):
                logger.info("Verified story paused (Play button appeared).")
                return "Story paused successfully."
            else:
                logger.warning("Clicked pause, but Play button did not appear.")
                return "Clicked pause, but verification failed."
        else:
            return "Could not find or click pause button."

    async def resume_story(self) -> str:
        # Logic looks okay, ensure selector usage is correct
        logger.info("Attempting to resume story...")
        if not await self._check_story_viewer_open():
            return "Cannot resume story: Story viewer not open."

        play_selector = self.selectors["story_play_button"]
        pause_selector = self.selectors["story_pause_button"]

        pause_locator = await self._get_locator(
            pause_selector, "Story pause button (check resume)"
        )
        if pause_locator and await pause_locator.is_visible(timeout=500):
            logger.info("Story is already playing (Pause button visible).")
            return "Story already playing."

        if await self.click_element(play_selector, "Story play button", timeout=3000):
            await asyncio.sleep(0.3)
            # Re-fetch locator for verification
            pause_locator_after = await self._get_locator(
                pause_selector, "Story pause button (verify resume)"
            )
            if pause_locator_after and await pause_locator_after.is_visible(
                timeout=1000
            ):
                logger.info("Verified story resumed (Pause button appeared).")
                return "Story resumed successfully."
            else:
                logger.warning("Clicked play, but Pause button did not appear.")
                return "Clicked play, but verification failed."
        else:
            return "Could not find or click play button."

    async def like_story(self) -> str:
        # Logic looks okay, ensure selector usage is correct
        logger.info("Attempting to like current story...")
        if not await self._check_story_viewer_open():
            return "Cannot like story: Story viewer not open."

        like_selector = self.selectors["story_like_button"]
        unlike_selector = self.selectors["story_unlike_button"]

        unlike_locator = await self._get_locator(
            unlike_selector, "Story unlike button (check like)"
        )
        if unlike_locator and await unlike_locator.is_visible(timeout=1000):
            logger.warning(
                "Story appears to be already liked (Unlike button/icon found)."
            )
            return "Story already liked."

        if await self.click_element(like_selector, "Story like button/icon"):
            await asyncio.sleep(random.uniform(0.5, 1.0))
            # Re-fetch locator for verification
            unlike_locator_after = await self._get_locator(
                unlike_selector, "Story unlike button (verify like)"
            )
            if unlike_locator_after and await unlike_locator_after.is_visible(
                timeout=2000
            ):
                logger.info(
                    "Verified story liked successfully (Unlike button/icon appeared)."
                )
                return "Story liked successfully."
            else:
                logger.warning("Clicked like, but Unlike button/icon did not appear.")
                screenshot_verify_fail = await self.capture_screenshot(
                    "story_like_verify_fail"
                )
                return f"Clicked like, but verification failed. Screenshot: {screenshot_verify_fail}"
        else:
            return "Could not find or click story like button/icon."

    async def reply_to_story(self, reply_text: str) -> str:
        # Logic looks okay, ensure selector usage is correct
        logger.info(f"Attempting to reply to current story with text: '{reply_text}'")
        if not await self._check_story_viewer_open():
            return "Cannot reply to story: Story viewer not open."

        reply_input_selector = self.selectors["story_reply_input"]

        if not await self.type_into_element(
            reply_input_selector, reply_text, "Story reply input"
        ):
            return "Could not find or type into story reply input."

        try:
            await asyncio.sleep(random.uniform(0.3, 0.7))
            await self.page.keyboard.press("Enter")
            logger.info("Pressed Enter to send story reply.")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            screenshot = await self.capture_screenshot("story_reply_sent")
            return f"Story reply sent. Screenshot: {screenshot}"
        except Exception as e:
            logger.error(
                "Error pressing Enter to send story reply: %s", e, exc_info=True
            )
            screenshot = await self.capture_screenshot("story_reply_send_error")
            return f"Error sending story reply: {e}. Screenshot: {screenshot}"

    async def close_story_viewer(self) -> str:
        # Logic looks okay, ensure selector usage is correct
        logger.info("Attempting to close story viewer...")
        if not await self._check_story_viewer_open():
            return "Story viewer was not open."

        close_button_selector = self.selectors["story_close_button"]
        if await self.click_element(
            close_button_selector, "Story close button", timeout=5000
        ):
            await asyncio.sleep(0.5)
            try:
                # Re-fetch locator for verification
                story_dialog_locator = await self._get_locator(
                    self.selectors["story_viewer_dialog"],
                    "Story viewer dialog (verify close)",
                )
                if (
                    not story_dialog_locator
                    or not await story_dialog_locator.is_visible(timeout=2000)
                ):
                    logger.info("Verified story viewer closed.")
                    return "Story viewer closed successfully."
                else:
                    logger.warning(
                        "Clicked close, but story viewer still seems visible."
                    )
                    return "Clicked close button, but viewer may still be open."
            except Exception:
                # If locator check fails after clicking close, assume it closed successfully
                logger.info(
                    "Story viewer likely closed (verification check failed/element detached)."
                )
                return "Story viewer closed successfully."
        else:
            logger.error("Failed to find or click the story viewer close button.")
            return "Failed to click close button."


# === MCP Tool Definitions ===

mcp = FastMCP("instagram-server")
instagram = InstagramServer()  # Instantiate the server class


@mcp.tool()
async def access_instagram() -> str:
    """Access Instagram homepage, ensuring the main feed content is loaded. Uses refresh if needed."""
    logger.info("Tool 'access_instagram' called.")
    await instagram.init()
    page = instagram.page  # Assuming init sets self.page correctly

    target_url = "https://www.instagram.com/"
    main_content_selector = instagram.selectors["main_feed_content"]

    # --- Get Locator using helper ---
    main_content_locator = await instagram._get_locator(
        main_content_selector, "Main feed content"
    )
    if not main_content_locator:
        return "Error: Could not even create locator for main feed content."

    try:
        logger.info("Navigating to Instagram homepage: %s", target_url)
        # Using domcontentloaded is often faster and sufficient for checking initial elements
        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        logger.info("Initial page load attempt done. Checking for main content...")

        # --- Use locator-based wait ---
        if await instagram.wait_for_locator(
            main_content_locator, "Main feed content", timeout=15000
        ):
            logger.info("Main content loaded on first try!")
            await asyncio.sleep(random.uniform(0.5, 1.0))
            screenshot_path = await instagram.capture_screenshot(
                "homepage_loaded_first_try"
            )
            return (
                f"Opened Instagram homepage successfully. Screenshot: {screenshot_path}"
            )
        else:
            logger.info("Main content not found quickly. Attempting page refresh...")
            await instagram.capture_screenshot("homepage_before_reload")
            await page.reload(wait_until="domcontentloaded", timeout=45000)
            logger.info("Page reloaded. Waiting for main content again...")

            # --- Use locator-based wait again ---
            if await instagram.wait_for_locator(
                main_content_locator, "Main feed content", timeout=30000
            ):
                logger.info("Refresh successful, main content loaded!")
                await asyncio.sleep(random.uniform(0.5, 1.5))
                screenshot_path = await instagram.capture_screenshot(
                    "homepage_loaded_after_reload"
                )
                return f"Opened Instagram homepage successfully after refresh. Screenshot: {screenshot_path}"
            else:
                logger.error("Main content not found even after refresh.")
                screenshot_path = await instagram.capture_screenshot(
                    "homepage_failed_after_reload"
                )
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
    result = await instagram.like_post(post_url=None)
    logger.info("Tool 'like_current_post' finished. Result: %s", result)
    return result


@mcp.tool()
async def comment_on_current_post(comment: str) -> str:
    """Comments on the post currently displayed on the page."""
    logger.info("Tool 'comment_on_current_post' called with comment: '%s'", comment)
    await instagram.init()
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
    """Scrolls down in the Instagram feed a specified number of times (approx 1-3 times by default)."""
    actual_scrolls = max(1, min(scrolls, 5))  # Example clamping
    logger.info(
        "Tool 'scroll_instagram_feed' called with scrolls: %d (using %d)",
        scrolls,
        actual_scrolls,
    )
    await instagram.init()

    if await instagram._check_story_viewer_open():
        logger.warning(
            "Attempted to scroll feed while story viewer is open. Closing viewer first."
        )
        close_result = await instagram.close_story_viewer()
        logger.info("Close story viewer result: %s", close_result)
        await asyncio.sleep(0.5)

    try:
        await instagram.simulate_human_scroll(
            min_scrolls=actual_scrolls, max_scrolls=actual_scrolls
        )
        result = f"Simulated {actual_scrolls} scroll(s) on the feed."
        logger.info("Tool 'scroll_instagram_feed' finished. Result: %s", result)
        return result
    except Exception as e:
        logger.error("Error during scroll simulation tool call: %s", e, exc_info=True)
        return f"Error during scroll: {e}"


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
        logger.error(
            "Unexpected error in 'snapshot_instagram_page_tree' tool: %s",
            e,
            exc_info=True,
        )
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
    # Ensure instagram instance is created before running MCP
    instagram = InstagramServer()
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, stopping server.")
    except Exception as e:
        logger.critical("MCP server failed to run: %s", e, exc_info=True)
    finally:
        logger.info("Executing final browser cleanup...")

        async def close_browser_sync():
            # Use the global 'instagram' instance defined in __main__
            if hasattr(instagram, "browser") and instagram.browser:
                logger.info("Ensuring browser is closed on server exit...")
                await instagram.close()
            else:
                logger.info("Browser already closed or not initialized on exit.")

        try:
            # Prefer asyncio.run for simplicity if no loop is guaranteed running
            asyncio.run(close_browser_sync())
        except RuntimeError as e:
            logger.info(f"Could not run final cleanup (loop likely stopped): {e}")
        logger.info("Instagram MCP server stopped.")
