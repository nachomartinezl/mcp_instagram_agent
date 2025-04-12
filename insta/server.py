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

    async def wait_for_selector(
        self, selector: str, timeout: int = 30000
    ) -> Optional[any]:  # Default 30 secs now!
        logger.debug("Waiting for selector '%s' to be visible (timeout: %dms)...", selector, timeout)
        try:
            # Waiting for 'visible' is usually a good bet for interactable elements
            element = await self.page.wait_for_selector(
                selector, state="visible", timeout=timeout
            )
            logger.info("Selector '%s' found and visible!", selector)
            return element
        except Exception as e:
            logger.error("Timeout or error waiting for selector '%s': %s", selector, e)
            # Consider taking screenshot on error
            # await self.capture_screenshot(f"error_wait_for_{selector.replace(':', '_').replace(' ', '_')}")
            return None

    async def capture_screenshot(self, prefix: str) -> str:
        """Capture a screenshot with a given prefix"""
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


    async def like_post(self, post_url: str) -> str:
        """Like a post given its URL with natural behavior"""
        logger.info("Attempting to like post: %s", post_url)
        # First perform some natural interactions
        await self.simulate_natural_interaction()

        logger.info("Navigating to post URL: %s", post_url)
        await self.page.goto(post_url)
        await self.page.wait_for_load_state("networkidle")
        logger.info("Page loaded for post: %s", post_url)

        # Scroll the post into view naturally
        await self.simulate_human_scroll(1, 2)
        screenshot_path = await self.capture_screenshot(f"post_{post_url.split('/')[-2] if '/' in post_url else 'post'}") # More specific name

        like_button_selector = 'article svg[aria-label="Like"]'
        logger.info("Looking for like button with selector: %s", like_button_selector)
        like_button = await self.wait_for_selector(like_button_selector)

        if like_button:
            # Random delay before liking (0.5 to 2 seconds)
            delay = random.uniform(0.5, 2)
            logger.info("Like button found. Waiting %.2f seconds before clicking.", delay)
            await asyncio.sleep(delay)
            try:
                await like_button.click()
                logger.info("Like button clicked successfully for post: %s", post_url)
                return f"Post liked successfully. Screenshot saved at: {screenshot_path}"
            except Exception as e:
                 logger.error("Error clicking like button for post %s: %s", post_url, e, exc_info=True)
                 return f"Error clicking like button: {e}. Screenshot saved at: {screenshot_path}"
        else:
            logger.warning("Could not find like button for post: %s", post_url)
            return f"Could not find like button. Screenshot saved at: {screenshot_path}"

    async def comment_on_post(self, post_url: str, comment_text: str) -> str:
        """Comment on a post with natural behavior"""
        logger.info("Attempting to comment on post: %s", post_url)
        # First perform some natural interactions
        await self.simulate_natural_interaction()

        logger.info("Navigating to post URL: %s", post_url)
        await self.page.goto(post_url)
        await self.page.wait_for_load_state("networkidle")
        logger.info("Page loaded for post: %s", post_url)

        # Scroll the post into view naturally
        await self.simulate_human_scroll(1, 2)
        screenshot_path = await self.capture_screenshot(f"comment_post_{post_url.split('/')[-2] if '/' in post_url else 'post'}")

        # Click comment button to open comment section
        comment_button_selector = 'svg[aria-label="Comment"]'
        logger.info("Looking for comment button: %s", comment_button_selector)
        comment_button = await self.wait_for_selector(comment_button_selector)
        if comment_button:
            delay = random.uniform(0.5, 1.5)
            logger.info("Comment button found. Waiting %.2f seconds before clicking.", delay)
            await asyncio.sleep(delay)
            try:
                await comment_button.click()
                logger.info("Comment button clicked.")
            except Exception as e:
                logger.error("Error clicking comment button for post %s: %s", post_url, e, exc_info=True)
                return f"Error clicking comment button: {e}. Screenshot saved at: {screenshot_path}"
        else:
            logger.warning("Could not find comment button for post: %s", post_url)
            return f"Could not find comment button to open input. Screenshot saved at: {screenshot_path}"


        # Find and fill comment textarea
        comment_input_selector = 'textarea[aria-label="Add a comment…"]'
        logger.info("Looking for comment input area: %s", comment_input_selector)
        comment_input = await self.wait_for_selector(comment_input_selector)

        if comment_input:
            # Random delay before typing (0.5 to 2 seconds)
            delay = random.uniform(0.5, 2)
            logger.info("Comment input found. Waiting %.2f seconds before typing.", delay)
            await asyncio.sleep(delay)
            # Type comment with random delays between characters
            logger.info("Typing comment: '%s'", comment_text)
            try:
                for char in comment_text:
                    await comment_input.type(char, delay=random.uniform(50, 200))

                await asyncio.sleep(random.uniform(0.5, 1.5))
                await comment_input.press("Enter")
                logger.info("Comment posted successfully for post: %s", post_url)
                return (
                    f"Comment posted successfully. Screenshot saved at: {screenshot_path}"
                )
            except Exception as e:
                logger.error("Error typing or submitting comment for post %s: %s", post_url, e, exc_info=True)
                return f"Error typing or submitting comment: {e}. Screenshot saved at: {screenshot_path}"
        else:
            logger.warning("Could not find comment input area for post: %s", post_url)
            return f"Could not find comment input area. Screenshot saved at: {screenshot_path}"

    async def open_stories(self) -> str:
        """Opens the first story from the feed, verifying by finding the 'Next' button."""
        logger.info("Attempting to open Instagram stories...")
        # --- Smart Navigation (Checks if already on feed) ---
        current_url = self.page.url
        logger.debug("Current URL: %s", current_url)
        if not (
            "instagram.com" in current_url
            and "/p/" not in current_url
            and "/reels/" not in current_url
        ):
            logger.info("Not on main feed or known non-feed page. Navigating to homepage first...")
            try:
                await self.page.goto(
                    "https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000
                )
                await self.wait_for_selector(
                    "main[role='main']", timeout=20000
                )  # Wait for feed
                logger.info("Successfully navigated to homepage.")
            except Exception as e:
                logger.error("Failed to navigate to homepage before opening stories: %s", e, exc_info=True)
                await self.capture_screenshot("error_nav_to_home_for_stories")
                return f"Failed to navigate to homepage to find stories: {e}"

        logger.info("Looking for the first story ring button using aria-label...")
        # Targets the clickable div based on role, tabindex, and partial aria-label
        first_story_button_selector = (
            'div[role="button"][aria-label^="Story by"][tabindex="0"]'
        )
        stories_button = await self.wait_for_selector(
            first_story_button_selector, timeout=15000
        )  # Wait 15 secs

        if stories_button:
            logger.info("Found story button matching selector: '%s'! Clicking...", first_story_button_selector)
            try:
                # Maybe add a tiny hover first?
                await stories_button.hover(timeout=3000)
                await asyncio.sleep(random.uniform(0.2, 0.5))
                await stories_button.click(timeout=5000)
                logger.info("Story button clicked.")

                # *** NEW: Wait for the 'Next' button inside stories ***
                logger.info("Waiting for story 'Next' button to appear as confirmation...")
                next_button_selector = 'button[aria-label="Next"]'
                story_viewer_selector = 'div[role="dialog"]:has(button[aria-label="Close"])' # Keep for fallback check

                # Give it a generous timeout, as story loading can vary
                next_button_element = await self.wait_for_selector(next_button_selector, timeout=25000)

                if next_button_element:
                    logger.info("Story 'Next' button found! Story viewer likely opened successfully.")
                    # REMOVED: await asyncio.sleep(random.uniform(0.5, 1.5)) # Let story fully render
                    screenshot_path = await self.capture_screenshot("story_opened_via_next_btn")
                    return f"Stories opened successfully (verified by next button). Screenshot saved at: {screenshot_path}"
                else:
                    logger.error("Clicked story button, but the 'Next' story button did not appear within 25s.")
                    screenshot_path = await self.capture_screenshot("story_next_button_fail")
                    # Check for the dialog element just in case, for logging
                    dialog_present = await self.page.query_selector(story_viewer_selector)
                    logger.warning(f"Story viewer dialog element present after timeout? {dialog_present is not None}")
                    return f"Clicked story button, but story viewer did not seem to load correctly (Next button missing). Screenshot: {screenshot_path}"

            except Exception as e:
                logger.error("Error clicking story button or waiting for story view: %s", e, exc_info=True)
                screenshot_path = await self.capture_screenshot("story_click_or_wait_error")
                return f"Error clicking story button or waiting for view: {e}. Screenshot: {screenshot_path}"
        else:
            logger.warning("Could not find the story button using selector: '%s'. Did the feed load correctly?", first_story_button_selector)
            screenshot_path = await self.capture_screenshot("story_button_not_found")
            return f"Could not find the first story element to click. Screenshot: {screenshot_path}"


    async def story_interaction(self, action: str) -> str:
        """Interact with current story with natural behavior"""
        logger.info("Attempting story interaction: '%s'", action)

        # Define valid actions and their selectors
        actions = {
            "like": 'svg[aria-label="Like"]', # Note: This might toggle like/unlike
            "next": 'button[aria-label="Next"]',
            "previous": 'button[aria-label="Previous"]',
            "reply": 'textarea[placeholder^="Reply to"]', # Changed selector for reply
        }

        if action not in actions:
            logger.warning("Unknown story action requested: '%s'", action)
            # Still capture screenshot even for unknown action attempt
            screenshot_path = await self.capture_story_screenshot()
            return f"Unknown action: {action}. Screenshot saved at: {screenshot_path}"

        # Simulate viewing time only if not an immediate action like like/reply
        if action in ["next", "previous"]:
             # Add natural viewing behavior before navigating
             await self.simulate_story_viewing_single() # Simulate viewing current story briefly

        # Capture the current story state *before* the action (unless it's reply)
        screenshot_path = "N/A"
        if action != "reply": # Don't screenshot before trying to find reply box
             screenshot_path = await self.capture_story_screenshot()

        selector = actions[action]
        logger.info("Looking for element for action '%s' with selector: %s", action, selector)
        element = await self.wait_for_selector(selector, timeout=5000) # Shorter timeout for interaction elements

        if element:
            # Add random delay before action
            delay = random.uniform(0.3, 1)
            logger.info("Element for action '%s' found. Waiting %.2f seconds before interacting.", action, delay)
            await asyncio.sleep(delay)
            try:
                if action == "reply":
                    # Special handling for reply: just focus it? Or type something?
                    # For now, just click (focus) it. A separate tool might be needed for actual replying.
                    await element.click()
                    logger.info("Reply input area focused.")
                    # Capture screenshot *after* focusing reply
                    screenshot_path = await self.capture_story_screenshot()
                    return f"Story reply input focused. Screenshot saved at: {screenshot_path}"
                else:
                    await element.click()
                    logger.info("Story action '%s' performed successfully.", action)
                    # Wait a tiny bit for UI to potentially update after click (e.g., next story loads)
                    await asyncio.sleep(random.uniform(0.2, 0.5))
                    # Capture screenshot *after* action if not reply
                    screenshot_path_after = await self.capture_screenshot(f"story_{action}_done")
                    return f"Story {action} action performed successfully. Screenshot saved at: {screenshot_path_after}"

            except Exception as e:
                 logger.error("Error performing story action '%s': %s", action, e, exc_info=True)
                 # Capture screenshot on error
                 screenshot_path_error = await self.capture_screenshot(f"story_{action}_error")
                 return f"Error performing {action} action: {e}. Screenshot saved at: {screenshot_path_error}"
        else:
            logger.warning("Could not find element for story action '%s'.", action)
            # Capture screenshot on failure to find element
            screenshot_path_notfound = await self.capture_screenshot(f"story_{action}_notfound")
            return f"Could not find element for {action} action. Screenshot saved at: {screenshot_path_notfound}"


    async def scroll_feed(self, amount: int = 1) -> str:
        """Scroll down in the feed"""
        logger.info("Scrolling feed %d time(s).", amount)
        try:
            for i in range(amount):
                scroll_height = await self.page.evaluate("window.innerHeight")
                await self.page.evaluate(f"window.scrollBy(0, {scroll_height})")
                logger.debug("Scrolled down by %d pixels (iteration %d/%d).", scroll_height, i+1, amount)
                await self.page.wait_for_timeout(random.uniform(750, 1500)) # Wait for content to potentially load
            logger.info("Finished scrolling feed %d time(s).", amount)
            return f"Scrolled {amount} times"
        except Exception as e:
            logger.error("Error during scrolling feed: %s", e, exc_info=True)
            return f"Error scrolling feed: {e}"

    async def pause_story(self) -> bool:
        """Pause the current story using the pause button"""
        logger.debug("Attempting to pause story...")
        pause_button_selector = 'button[aria-label="Pause"]'
        # Use a shorter timeout as the button should be immediately visible if story is playing
        pause_button = await self.wait_for_selector(pause_button_selector, timeout=2000)
        if pause_button:
            try:
                await pause_button.click()
                # Wait a moment to ensure the story is paused
                await asyncio.sleep(0.5)
                logger.info("Story paused.")
                return True
            except Exception as e:
                # Element might have disappeared if story ended right before click
                logger.warning("Could not click pause button (maybe story ended?): %s", e)
                return False
        else:
            logger.debug("Pause button not found (story might already be paused or not loaded).")
            return False # Assume not paused or button not available

    async def resume_story(self):
        """Resume the story playback"""
        logger.debug("Attempting to resume story...")
        play_button_selector = 'button[aria-label="Play"]'
        # Use a shorter timeout
        play_button = await self.wait_for_selector(play_button_selector, timeout=2000)
        if play_button:
            try:
                await play_button.click()
                logger.info("Story resumed.")
            except Exception as e:
                 logger.warning("Could not click play button: %s", e)
        else:
            logger.debug("Play button not found (story might already be playing or not loaded).")


    async def capture_story_screenshot(self) -> str:
        """Capture a screenshot of the current story, attempting to pause first."""
        logger.info("Attempting to capture screenshot of current story...")
        is_paused = await self.pause_story()
        screenshot_path = "Error" # Default
        try:
            # Capture screenshot regardless of pause success, but log if pause failed
            if not is_paused:
                logger.warning("Could not pause story before taking screenshot. Capturing anyway.")
            screenshot_path = await self.capture_screenshot("story_view") # Use a consistent prefix
            logger.info("Story screenshot captured successfully.")
        except Exception as e:
             logger.error("Error capturing story screenshot: %s", e, exc_info=True)
             screenshot_path = f"Error capturing story screenshot: {e}"
        finally:
            # Resume story playback only if we successfully paused it
            if is_paused:
                await self.resume_story()
        return screenshot_path


    async def simulate_human_scroll(self, min_scrolls: int = 2, max_scrolls: int = 5):
        """Simulate human-like scrolling behavior"""
        num_scrolls = random.randint(min_scrolls, max_scrolls)
        logger.info("Simulating human scroll: %d scrolls.", num_scrolls)
        try:
            for i in range(num_scrolls):
                # Random scroll amount between 100 and full viewport height
                scroll_max = await self.page.evaluate("window.innerHeight")
                scroll_amount = random.randint(100, scroll_max if scroll_max > 100 else 500) # Ensure positive range
                await self.page.evaluate(f"window.scrollBy(0, {scroll_amount})")
                # Random pause between scrolls (0.5 to 2 seconds)
                pause_duration = random.uniform(0.5, 2)
                logger.debug("Scroll %d/%d: Scrolled by %dpx, pausing for %.2fs", i+1, num_scrolls, scroll_amount, pause_duration)
                await asyncio.sleep(pause_duration)

                # Sometimes pause for a bit longer (20% chance)
                if random.random() < 0.2:
                    long_pause = random.uniform(1, 3)
                    logger.debug("Performing additional random pause for %.2fs", long_pause)
                    await asyncio.sleep(long_pause)
            logger.info("Finished simulating human scroll.")
        except Exception as e:
            logger.error("Error during human scroll simulation: %s", e, exc_info=True)

    async def simulate_story_viewing_single(self):
        """Simulate viewing a single story for a random duration, potentially pausing."""
        view_time = random.uniform(2, 5)
        logger.debug("Simulating viewing current story for %.2fs", view_time)
        await asyncio.sleep(view_time)

        # Sometimes pause the story (15% chance)
        if random.random() < 0.15:
            logger.debug("Randomly decided to pause story during viewing simulation.")
            if await self.pause_story():
                pause_duration = random.uniform(1, 3)
                logger.debug("Paused story, waiting for %.2fs", pause_duration)
                await asyncio.sleep(pause_duration)
                await self.resume_story()


    async def simulate_story_viewing(self, min_stories: int = 3, max_stories: int = 7):
        """Simulate natural story viewing behavior across multiple stories"""
        num_stories_to_view = random.randint(min_stories, max_stories)
        logger.info("Simulating natural story viewing: aiming for %d stories.", num_stories_to_view)
        # Weight towards moving forward, occasional previous
        actions = ["next"] * 7 + ["previous"] * 2 + ["like"] * 1 # Weighted list

        for i in range(num_stories_to_view):
            logger.info("Viewing simulated story %d/%d...", i+1, num_stories_to_view)

            # Simulate viewing the current story
            await self.simulate_story_viewing_single()

            # Randomly choose an action
            action = random.choice(actions)
            logger.debug("Chosen action for story %d: '%s'", i+1, action)

            # Perform the chosen action
            interaction_result = await self.story_interaction(action)
            logger.debug("Interaction result for action '%s': %s", action, interaction_result)

            # Small delay after action before next loop iteration
            await asyncio.sleep(random.uniform(0.3, 0.8))

            # Check if story viewer might have closed unexpectedly (e.g., end of stories)
            # Check for the close button as a proxy for the viewer being open
            close_button_selector = 'button[aria-label="Close"]'
            close_button = await self.page.query_selector(close_button_selector)
            if not close_button:
                 logger.warning("Story viewer seems to have closed during simulation (after %d stories). Ending simulation.", i+1)
                 break # Exit the loop if viewer closed

        logger.info("Finished simulating story viewing.")


    async def skip_to_next_user_stories(self):
        """Skip to the next user's stories using the dedicated button if available."""
        logger.info("Attempting to skip to the next user's stories...")
        # Instagram often uses a chevron or similar icon button positioned top-right
        # Let's try a selector targeting a button within the story header area
        # This might need refinement based on actual inspection
        next_user_button_selector = 'div[role="dialog"] button:not([aria-label="Pause"]):not([aria-label="Play"]):not([aria-label="Volume off"]):not([aria-label="Volume on"]):not([aria-label="More options"])'
        # This is very generic, might need a more specific attribute if available
        # Alternative: 'button[aria-label="Next"]' might work if it doubles for next user at the end? Let's try the generic one first.

        # Let's stick to the reliable 'Next' button for now, it often handles user skipping too.
        next_user_button_selector = 'button[aria-label="Next"]'
        logger.debug("Using selector '%s' to attempt skipping to next user.", next_user_button_selector)


        next_user_button = await self.wait_for_selector(next_user_button_selector, timeout=3000) # Short timeout

        if next_user_button:
            try:
                await next_user_button.click()
                await asyncio.sleep(random.uniform(0.5, 1)) # Wait for transition
                logger.info("Clicked 'Next', potentially skipped to next user's stories.")
                return True
            except Exception as e:
                logger.warning("Error clicking 'Next' button to skip user: %s", e)
                return False
        else:
            logger.warning("Could not find 'Next' button to attempt skipping user.")
            return False

    async def simulate_natural_interaction(self):
        """Perform random natural interactions before taking primary actions"""
        logger.info("Simulating natural interaction before main action...")

        # 70% chance to scroll feed
        if random.random() < 0.7:
            logger.info("Natural interaction: Scrolling feed.")
            await self.simulate_human_scroll(1, 3) # Scroll a bit less here
        else:
            logger.info("Natural interaction: Skipping feed scroll.")

        # 40% chance to view stories
        if random.random() < 0.4:
            logger.info("Natural interaction: Attempting to view stories.")
            open_result = await self.open_stories()
            if "successfully" in open_result.lower():
                await self.simulate_story_viewing(2, 5) # View fewer stories here
                # 30% chance to skip to next user's stories if viewing happened
                if random.random() < 0.3:
                    logger.info("Natural interaction: Attempting to skip to next user's stories.")
                    await self.skip_to_next_user_stories()

                # Ensure returning to feed by closing the story viewer
                logger.info("Natural interaction: Closing story viewer.")
                exit_button_selector = 'button[aria-label="Close"]'
                exit_button = await self.wait_for_selector(exit_button_selector, timeout=5000)
                if exit_button:
                    try:
                        await exit_button.click()
                        logger.info("Story viewer closed.")
                    except Exception as e:
                        logger.warning("Could not click story viewer close button: %s", e)
                        # Attempt navigation back to home as fallback
                        await self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                else:
                    logger.warning("Could not find story viewer close button.")
                    # Attempt navigation back to home as fallback
                    await self.page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            else:
                logger.warning("Natural interaction: Failed to open stories, skipping story viewing simulation.")
        else:
             logger.info("Natural interaction: Skipping story viewing.")

        logger.info("Finished simulating natural interaction.")


# Create a FastMCP server
mcp = FastMCP("instagram-server")
instagram = InstagramServer()


@mcp.tool()
async def access_instagram() -> str:
    """Access Instagram homepage quickly, using a refresh if needed."""
    logger.info("Tool 'access_instagram' called.")
    await instagram.init()  # Ensures browser/page is ready
    logger.info("Quickly navigating to Insta homepage...")
    target_url = "https://www.instagram.com/"
    try:
        # SUPER FAST Initial navigation attempt - just check if it loads DOM quickly
        await instagram.page.goto(
            target_url, wait_until="domcontentloaded", timeout=10000
        )  # 10 secs MAX for first attempt
        logger.info("Initial page load attempt done. Quick check for main content...")

        # Check VERY briefly if the main content magically appeared (low timeout)
        main_content = await instagram.wait_for_selector(
            "main[role='main']", timeout=2000
        )  # Only wait 2 seconds!

        if main_content:
            logger.info("Main content loaded on first try!")
            await asyncio.sleep(0.5)  # Tiny pause
            screenshot_path = await instagram.capture_screenshot("homepage_loaded_first_try_fast")
            return f"Opened Instagram homepage successfully on first try! Screenshot: {screenshot_path}"

        else:
            logger.info("Main content not found quickly. Hitting refresh now...")
            # await instagram.capture_screenshot("homepage_before_reload_fast") # Optional
            # **** THE REFRESH ****
            await instagram.page.reload(
                wait_until="domcontentloaded", timeout=60000
            )  # Give reload time
            logger.info("Page reloaded! Waiting for the main content properly this time...")

            # Wait for the main content with a reasonable timeout AFTER reload
            main_content_after_reload = await instagram.wait_for_selector(
                "main[role='main']", timeout=30000
            )  # 30 secs should be plenty

            if main_content_after_reload:
                logger.info("Refresh successful, page main content is loaded!")
                await asyncio.sleep(random.uniform(0.5, 1.5))  # Settle down
                screenshot_path = await instagram.capture_screenshot("homepage_loaded_after_reload")
                return f"Opened Instagram homepage successfully after a quick refresh! Screenshot: {screenshot_path}"
            else:
                logger.error("Main content not found even after refresh.")
                screenshot_path = await instagram.capture_screenshot("homepage_failed_after_reload")
                return f"Failed to load main content after refresh. Screenshot: {screenshot_path}"

    except Exception as e:
        logger.error("Error accessing Instagram homepage: %s", e, exc_info=True)
        try:
            screenshot_path = await instagram.capture_screenshot("homepage_load_ERROR")
            return f"Error accessing Instagram homepage: {e}. Screenshot: {screenshot_path}"
        except Exception as screen_err:
            logger.error("Failed to take screenshot during homepage load error: %s", screen_err)
            return f"Error accessing Instagram homepage: {e}. Also failed to take error screenshot."


@mcp.tool()
async def like_instagram_post(post_url: str) -> str:
    """Like an Instagram post given its URL"""
    logger.info("Tool 'like_instagram_post' called for URL: %s", post_url)
    await instagram.init()
    result = await instagram.like_post(post_url)
    logger.info("Tool 'like_instagram_post' finished. Result: %s", result)
    return result


@mcp.tool()
async def comment_on_instagram_post(post_url: str, comment: str) -> str:
    """Comment on an Instagram post"""
    logger.info("Tool 'comment_on_instagram_post' called for URL: %s", post_url)
    await instagram.init()
    result = await instagram.comment_on_post(post_url, comment)
    logger.info("Tool 'comment_on_instagram_post' finished. Result: %s", result)
    return result


@mcp.tool()
async def view_instagram_stories() -> str:
    """Open and view Instagram stories, leaving the viewer open."""
    logger.info("Tool 'view_instagram_stories' called.")
    await instagram.init()
    result = await instagram.open_stories()
    # Optionally add simulation here if 'view' implies more than just opening
    if "successfully" in result.lower():
        logger.info("Stories opened, now simulating viewing...")
        await instagram.simulate_story_viewing(3, 7) # Simulate viewing after opening
        # REMOVED: Closing stories after viewing simulation to allow further interaction
        # logger.info("Closing stories after viewing simulation.")
        # exit_button = await instagram.wait_for_selector('button[aria-label="Close"]', timeout=5000)
        # if exit_button:
        #     try:
        #         await exit_button.click()
        #         logger.info("Story viewer closed after simulation.")
        #     except Exception as e:
        #          logger.warning("Could not click story viewer close button after simulation: %s", e)
        # else:
        #     logger.warning("Could not find story viewer close button after simulation.")
        logger.info("Finished story viewing simulation. Story viewer remains open.")

    logger.info("Tool 'view_instagram_stories' finished. Result: %s", result)
    # Modify the return message slightly to indicate the viewer is left open
    if "successfully" in result.lower():
        return f"{result} Viewer left open after simulation."
    else:
        return result


@mcp.tool()
async def interact_with_story(action: str) -> str:
    """Interact with current story. Actions: 'like', 'next', 'previous', 'reply'"""
    logger.info("Tool 'interact_with_story' called with action: %s", action)
    await instagram.init()
    # Check if stories are actually open first? Might be safer.
    story_viewer_selector = 'div[role="dialog"]:has(button[aria-label="Close"])'
    story_viewer = await instagram.page.query_selector(story_viewer_selector)
    if not story_viewer:
        logger.warning("Attempted story interaction ('%s'), but story viewer doesn't seem to be open.", action)
        return "Cannot interact with story: Story viewer is not open."

    result = await instagram.story_interaction(action)
    logger.info("Tool 'interact_with_story' finished. Result: %s", result)
    return result


@mcp.tool()
async def scroll_instagram_feed(scrolls: int = 1) -> str:
    """Scroll down in the Instagram feed"""
    logger.info("Tool 'scroll_instagram_feed' called with scrolls: %d", scrolls)
    await instagram.init()
    result = await instagram.scroll_feed(scrolls)
    logger.info("Tool 'scroll_instagram_feed' finished. Result: %s", result)
    return result


@mcp.tool()
async def close_instagram() -> str:
    """Close Instagram browser session"""
    logger.info("Tool 'close_instagram' called.")
    await instagram.close()
    logger.info("Tool 'close_instagram' finished.")
    return "Closed Instagram session"


if __name__ == "__main__":
    logger.info("Starting Instagram MCP server...")
    try:
        mcp.run(transport="stdio")
    except Exception as e:
        logger.critical("MCP server failed to run: %s", e, exc_info=True)
    finally:
        logger.info("Instagram MCP server stopped.")

