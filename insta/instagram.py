import json
import os
import asyncio
import random
import logging
from typing import Optional

# Playwright imports
from playwright.async_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
    Locator,
    async_playwright,
)

# --- Set up logging ---
log_file = "instagram_server.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file),
    ],
)
logger = logging.getLogger(__name__)
# ---------------------

class InstagramServer:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page: Optional[Page] = None
        self.cookies_path = os.path.join(
            os.path.dirname(__file__), "cookies", "instagram.json"
        )
        logger.info("InstagramServer instance created.")
        self.selectors = {
            'feed': {
                'content': "main[role='main']",
                'first_article': "main[role='main'] article:first-of-type",
                'more_options': 'internal:role=button[name="More options"i]',
                'modal': {
                    'go_to_post': 'button:has-text("Go to post")'
                }
            },
            'post': {
                'like': 'internal:role=button[name="Like"i][exact=true]', # Updated selector
                'unlike': 'internal:role=button[name="Unlike"i][exact=true]', # Updated selector
                'comment_button': 'article div[role="button"]:has(svg[aria-label="Comment"]), main div[role="button"]:has(svg[aria-label="Comment"])',
                'comment_input': 'textarea[aria-label="Add a comment…"]',
                'submit': 'div[role="button"]:text-is("Post")'
            },
            'stories': {
                'first': 'div[role="button"][aria-label^="Story by"][tabindex="0"]',
                'next': 'div[role="dialog"] button[aria-label="Next"]',
                'previous': 'div[role="dialog"] button[aria-label="Previous"]',
                'pause': 'div[role="dialog"] div[role="button"]:has(svg[aria-label="Pause"])',
                'play': 'div[role="dialog"] div[role="button"]:has(svg[aria-label="Play"])',
                'like': 'div[role="dialog"] svg[aria-label="Like"]',
                'unlike': 'div[role="dialog"] svg[aria-label="Unlike"]',
                'reply_input': 'div[role="dialog"] textarea[placeholder^="Reply to"]',
                'close': 'internal:role=button[name="Close"i][exact=true]', # Updated selector
                'viewer': 'div[role="dialog"]'
            }
        }

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
                # Keep json import for this
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

    async def init(self):
        # This method remains largely the same, just logging adjusted slightly
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

    # --- Helper Methods ---

    async def _wait_for_post_content(self, page: Page) -> None:
        """Wait for critical post elements to be present."""
        logger.debug("Waiting for post content to stabilize (like button or comment input)...")
        post_like_btn = page.locator(self.selectors["post"]["like"])
        post_comment_input = page.locator(self.selectors["post"]["comment_input"])
        # Wait for either the like button OR the comment input to be visible
        await post_like_btn.or_(post_comment_input).first.wait_for(state="visible", timeout=30000) # Already uses "visible"
        await asyncio.sleep(0.5)  # Short stabilization period
        logger.debug("Post content stabilized.")


    # --- Feed Actions ---

    async def open_first_post_from_feed(self) -> str:
        # Replaced with provided implementation
        page = self._ensure_page()
        logger.info("Attempting to open the first post from the feed...")
        try:
            # Wait for main feed content directly
            main_feed = page.locator(self.selectors["feed"]["content"])
            await main_feed.wait_for(state="visible", timeout=15000)
            logger.debug("Main feed content visible.")

            # Get first post article
            first_article = page.locator(self.selectors["feed"]["first_article"])
            await first_article.wait_for(state="visible", timeout=10000)
            logger.debug("First post article visible.")

            # Click more options
            more_options = first_article.locator(self.selectors["feed"]["more_options"])
            await more_options.wait_for(state="visible", timeout=7000)
            logger.debug("More options button visible. Clicking...")
            await more_options.click(timeout=5000)

            # Click go to post
            go_to_post = page.locator(self.selectors["feed"]["modal"]["go_to_post"])
            await go_to_post.wait_for(state="visible", timeout=5000) # Added wait_for visible
            logger.debug("'Go to post' button visible. Clicking...")
            await go_to_post.click(timeout=5000)

            # --- MODIFIED WAIT LOGIC ---
            logger.debug("Waiting for post content to load after clicking 'Go to post'...")
            await self._wait_for_post_content(page) # Use helper method
            # --- END MODIFIED WAIT LOGIC ---

            logger.info("Post content loaded successfully. Current URL: %s", page.url)
            return f"Successfully opened post from feed. Current URL: {page.url}"
        except PlaywrightTimeoutError as e:
            logger.error("Timeout error opening post from feed: %s", e)
            # Removed screenshot call
            return f"Error: Timeout opening post from feed - {e}"
        except Exception as e:
            logger.error("Error opening post from feed: %s", e, exc_info=True)
            # Removed screenshot call
            return f"Error: Could not open post from feed - {e}"

    # --- Post Actions ---

    async def like_post(self, post_url: Optional[str] = None) -> str:
        # Updated method based on user request
        page = self._ensure_page()
        action_description = f"like post at {post_url}" if post_url else "like current post"
        logger.info(f"Attempting to {action_description}...")

        try:
            if post_url:
                logger.info("Navigating to post URL: %s", post_url)
                # Use domcontentloaded and helper wait
                await page.goto(post_url, wait_until="domcontentloaded", timeout=45000)
                await self._wait_for_post_content(page)

            # Use get_by_role as requested
            like_btn = page.get_by_role("button", name="Like", exact=True)
            unlike_btn = page.get_by_role("button", name="Unlike", exact=True)

            # Check if already liked using .first and is_visible
            if await unlike_btn.first.is_visible(timeout=2000):
                logger.info("Post already liked")
                return "Post already liked."

            # Wait for first like button
            logger.info("Waiting for like button...")
            await like_btn.first.wait_for(state="visible", timeout=10000)

            # Hover and click with precise positioning
            logger.debug("Hovering and clicking like button...")
            await like_btn.first.hover()
            await asyncio.sleep(0.3)

            # Click with position and force to avoid overlays
            await like_btn.first.click(
                position={"x": 5, "y": 5},
                timeout=5000,
                force=True # Added force=True
            )

            # Verify with unlike button
            logger.debug("Verifying like action...")
            await unlike_btn.first.wait_for(state="visible", timeout=3000)
            logger.info("Post liked successfully")
            return "Post liked successfully."

        except Exception as e:
            logger.error("Like failed. Current URL: %s", page.url)
            # Diagnostic screenshot
            screenshot_path = "like_error.png"
            try:
                await page.screenshot(path=screenshot_path, full_page=True)
                logger.info(f"Screenshot saved to {screenshot_path}")
            except Exception as ss_e:
                logger.error(f"Failed to save screenshot: {ss_e}")
            logger.error("Full error details: %s", str(e), exc_info=True)
            return f"Like failed: {str(e)}"


    async def comment_on_post(
        self, comment_text: str, post_url: Optional[str] = None
    ) -> str:
        # Replaced with provided implementation, added try/except and logging
        page = self._ensure_page()
        action_description = (
            f"comment on post at {post_url}" if post_url else "comment on current post"
        )
        logger.info(f"Attempting to {action_description} with text: '{comment_text}'")

        try:
            if post_url:
                logger.info("Navigating to post URL: %s", post_url)
                # Use domcontentloaded and helper wait
                await page.goto(post_url, wait_until="domcontentloaded", timeout=45000)
                await self._wait_for_post_content(page)
                logger.info("Page loaded for post: %s", post_url)

            # Optional click on comment icon (attempt, but don't fail)
            try:
                comment_button = page.locator(self.selectors["post"]["comment_button"])
                await comment_button.click(timeout=3000)
                logger.debug("Clicked comment icon (optional step).")
            except Exception:
                logger.debug("Could not click comment icon or it wasn't necessary.")

            comment_input = page.locator(self.selectors["post"]["comment_input"])
            await comment_input.wait_for(state="visible", timeout=10000)
            logger.debug("Comment input visible. Filling text...")
            # Use fill() as requested
            await comment_input.fill(comment_text)
            logger.info("Filled comment text.")

            # Add delay before posting
            post_delay = random.uniform(0.6, 1.4)
            logger.debug("Pausing for %.2fs before clicking Post button...", post_delay)
            await asyncio.sleep(post_delay)

            post_btn = page.locator(self.selectors["post"]["submit"])
            await post_btn.wait_for(state="visible", timeout=5000) # Wait for button
            logger.debug("Post button visible. Clicking...")
            await post_btn.click(timeout=5000)

            # Add delay after posting
            await asyncio.sleep(random.uniform(1.5, 2.5))
            logger.info("Comment posted successfully.")
            return "Comment posted successfully."

        except PlaywrightTimeoutError as e:
            logger.error("Timeout error during comment action: %s", e)
            # Removed screenshot call
            return f"Error: Timeout during comment action - {e}"
        except Exception as e:
            logger.error("Error commenting on post: %s", e, exc_info=True)
            # Removed screenshot call
            return f"Error: Could not comment on post - {e}"

    # --- Story Actions ---

    async def open_stories(self) -> str:
        # Replaced with provided implementation, added try/except and logging
        page = self._ensure_page()
        logger.info("Attempting to open Instagram stories...")

        # --- Navigate to feed if needed (Simplified check) ---
        current_url = page.url
        is_on_feed = "/p/" not in current_url and "/stories/" not in current_url
        if not is_on_feed:
            logger.info("Not on main feed, navigating to Instagram base URL.")
            try:
                # Use domcontentloaded and wait for feed content
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
                await page.locator(self.selectors["feed"]["content"]).wait_for(state="visible", timeout=15000)
                logger.info("Navigated to feed and confirmed content.")
            except Exception as nav_e:
                logger.error("Failed to navigate to feed: %s", nav_e)
                return f"Error: Failed to navigate to feed - {nav_e}"
        # --- End Navigation Logic ---

        try:
            story_btn_locator = self.selectors["stories"]["first"]
            logger.info("Looking for the first story ring button using selector: %s", story_btn_locator)
            story_btn = page.locator(story_btn_locator)

            # Wait for the first story button to be visible
            await story_btn.first.wait_for(state="visible", timeout=15000)
            logger.debug("First story button visible. Clicking...")
            await asyncio.sleep(random.uniform(0.1, 0.3))
            await story_btn.first.click(timeout=5000)
            logger.info("Clicked the first story element.")

            # Wait for story viewer using close button presence
            close_btn_locator = self.selectors["stories"]["close"]
            logger.debug("Waiting for story viewer to open (checking for close button)...")
            close_btn = page.locator(close_btn_locator)
            await close_btn.wait_for(state="visible", timeout=35000) # Generous timeout

            logger.info("Stories opened successfully (close button found).")
            return "Stories opened successfully."

        except PlaywrightTimeoutError as e:
            logger.error("Timeout error opening stories: %s", e)
            # Removed screenshot call
            return f"Error: Timeout opening stories - {e}"
        except Exception as e:
            logger.error("Error opening stories: %s", e, exc_info=True)
            # Removed screenshot call
            return f"Error: Could not open stories - {e}"

    async def _check_story_viewer_open(self) -> bool:
        # Replaced with provided implementation
        page = self._ensure_page() # Ensure page exists
        logger.debug("Checking if story viewer is open...")
        try:
            close_btn = page.locator(self.selectors["stories"]["close"])
            # Use wait_for with a short timeout to check presence
            await close_btn.wait_for(state="visible", timeout=1500)
            logger.debug("Story viewer check: Close button found. Assuming open.")
            return True
        except PlaywrightTimeoutError:
            logger.debug("Story viewer check: Close button not found within timeout. Assuming closed.")
            return False
        except Exception as e:
            # Catch other potential errors during check
            logger.warning("Error checking story viewer state: %s", e)
            return False # Assume closed on error

    async def next_story(self) -> str:
        # Uses keyboard, largely unchanged but uses updated check method
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
        # Uses keyboard, largely unchanged but uses updated check method
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
        # Refactored to use direct Playwright calls
        page = self._ensure_page()
        logger.info("Attempting to pause story...")
        if not await self._check_story_viewer_open():
            return "Cannot pause story: Story viewer not open."

        pause_selector = self.selectors["stories"]["pause"]
        play_selector = self.selectors["stories"]["play"]

        try:
            play_locator = page.locator(play_selector)
            if await play_locator.is_visible(timeout=500):
                logger.info("Story is already paused (Play button visible).")
                return "Story already paused."

            logger.debug("Looking for pause button...")
            pause_locator = page.locator(pause_selector)
            await pause_locator.wait_for(state="visible", timeout=3000)
            logger.debug("Pause button visible. Clicking...")
            await pause_locator.click(timeout=3000)

            await asyncio.sleep(0.3) # Wait for UI update

            # Verify by checking if play button appeared
            logger.debug("Verifying pause by looking for play button...")
            await play_locator.wait_for(state="visible", timeout=1000)
            logger.info("Verified story paused (Play button appeared).")
            return "Story paused successfully."

        except PlaywrightTimeoutError as e:
            logger.error("Timeout error during pause action: %s", e)
            # Check if verification failed but action might have succeeded
            try:
                play_locator = page.locator(play_selector)
                if await play_locator.is_visible(timeout=500):
                    logger.warning("Pause confirmation timed out, but play button IS visible now.")
                    return "Story likely paused, but confirmation timed out."
            except: pass
            return "Could not pause story or verify pause (Timeout)."
        except Exception as e:
            logger.error("Error pausing story: %s", e, exc_info=True)
            return f"Error pausing story: {e}"

    async def resume_story(self) -> str:
        # Refactored to use direct Playwright calls
        page = self._ensure_page()
        logger.info("Attempting to resume story...")
        if not await self._check_story_viewer_open():
            return "Cannot resume story: Story viewer not open."

        play_selector = self.selectors["stories"]["play"]
        pause_selector = self.selectors["stories"]["pause"]

        try:
            pause_locator = page.locator(pause_selector)
            if await pause_locator.is_visible(timeout=500):
                logger.info("Story is already playing (Pause button visible).")
                return "Story already playing."

            logger.debug("Looking for play button...")
            play_locator = page.locator(play_selector)
            await play_locator.wait_for(state="visible", timeout=3000)
            logger.debug("Play button visible. Clicking...")
            await play_locator.click(timeout=3000)

            await asyncio.sleep(0.3) # Wait for UI update

            # Verify by checking if pause button appeared
            logger.debug("Verifying resume by looking for pause button...")
            await pause_locator.wait_for(state="visible", timeout=1000)
            logger.info("Verified story resumed (Pause button appeared).")
            return "Story resumed successfully."

        except PlaywrightTimeoutError as e:
            logger.error("Timeout error during resume action: %s", e)
             # Check if verification failed but action might have succeeded
            try:
                pause_locator = page.locator(pause_selector)
                if await pause_locator.is_visible(timeout=500):
                    logger.warning("Resume confirmation timed out, but pause button IS visible now.")
                    return "Story likely resumed, but confirmation timed out."
            except: pass
            return "Could not resume story or verify resume (Timeout)."
        except Exception as e:
            logger.error("Error resuming story: %s", e, exc_info=True)
            return f"Error resuming story: {e}"

    async def like_story(self) -> str:
        # Refactored to use direct Playwright calls
        page = self._ensure_page()
        logger.info("Attempting to like current story...")
        if not await self._check_story_viewer_open():
            return "Cannot like story: Story viewer not open."

        like_selector = self.selectors["stories"]["like"]
        unlike_selector = self.selectors["stories"]["unlike"]

        try:
            unlike_locator = page.locator(unlike_selector)
            if await unlike_locator.is_visible(timeout=1000):
                logger.warning(
                    "Story appears to be already liked (Unlike button/icon found)."
                )
                return "Story already liked."

            logger.debug("Looking for like button/icon...")
            like_locator = page.locator(like_selector)
            await like_locator.wait_for(state="visible", timeout=5000) # Wait for it
            logger.debug("Like button/icon visible. Clicking...")
            await like_locator.click(timeout=3000) # Click it

            await asyncio.sleep(random.uniform(0.5, 1.0)) # Wait for UI update

            # Verify by checking if unlike button appeared
            logger.debug("Verifying like by looking for unlike button/icon...")
            await unlike_locator.wait_for(state="visible", timeout=2000)
            logger.info(
                "Verified story liked successfully (Unlike button/icon appeared)."
            )
            return "Story liked successfully."

        except PlaywrightTimeoutError as e:
            logger.error("Timeout error during story like action: %s", e)
            # Check if verification failed but action might have succeeded
            try:
                unlike_locator = page.locator(unlike_selector)
                if await unlike_locator.is_visible(timeout=500):
                    logger.warning("Story like confirmation timed out, but unlike button IS visible now.")
                    return "Story likely liked, but confirmation timed out."
            except: pass
            # Removed screenshot call
            return "Could not like story or verify like (Timeout)."
        except Exception as e:
            logger.error("Error liking story: %s", e, exc_info=True)
            # Removed screenshot call
            return f"Error liking story: {e}"

    async def reply_to_story(self, reply_text: str) -> str:
        # Replaced with provided implementation, added try/except and logging
        page = self._ensure_page()
        logger.info(f"Attempting to reply to current story with text: '{reply_text}'")
        if not await self._check_story_viewer_open():
            return "Cannot reply to story: Story viewer not open."

        try:
            reply_input_selector = self.selectors["stories"]["reply_input"]
            reply_input = page.locator(reply_input_selector)

            await reply_input.wait_for(state="visible", timeout=10000)
            logger.debug("Story reply input visible. Filling text...")
            await reply_input.fill(reply_text) # Use fill()
            logger.info("Filled story reply text.")

            await asyncio.sleep(random.uniform(0.3, 0.7))
            await page.keyboard.press("Enter")
            logger.info("Pressed Enter to send story reply.")
            await asyncio.sleep(random.uniform(0.5, 1.0)) # Short delay after sending

            # Removed screenshot call
            return "Story reply sent."
        except PlaywrightTimeoutError as e:
             logger.error("Timeout error during story reply action: %s", e)
             # Removed screenshot call
             return f"Error: Timeout during story reply - {e}"
        except Exception as e:
            logger.error(
                "Error replying to story: %s", e, exc_info=True
            )
            # Removed screenshot call
            return f"Error sending story reply: {e}"

    async def close_story_viewer(self) -> str:
        # Refactored to use direct Playwright calls
        page = self._ensure_page()
        logger.info("Attempting to close story viewer...")
        if not await self._check_story_viewer_open():
            # Log slightly differently if check returns false vs button not found later
            logger.info("Story viewer check indicated it was already closed.")
            return "Story viewer was not open."

        close_button_selector = self.selectors["stories"]["close"]
        try:
            close_locator = page.locator(close_button_selector)
            logger.debug("Looking for close button...")
            await close_locator.wait_for(state="visible", timeout=5000)
            logger.debug("Close button visible. Clicking...")
            await close_locator.click(timeout=3000)

            await asyncio.sleep(0.5) # Wait for close animation/state change

            # Verify by checking if the viewer is NOT open anymore
            if not await self._check_story_viewer_open():
                 logger.info("Verified story viewer closed.")
                 return "Story viewer closed successfully."
            else:
                 logger.warning("Clicked close, but story viewer still seems open.")
                 # Attempt click again? Or just report failure.
                 return "Clicked close button, but viewer may still be open."

        except PlaywrightTimeoutError:
            logger.error("Failed to find or click the story viewer close button (Timeout).")
            # Removed screenshot call
            return "Failed to click close button (Timeout)."
        except Exception as e:
            logger.error("Error closing story viewer: %s", e, exc_info=True)
            # Removed screenshot call
            return f"Error closing story viewer: {e}"
