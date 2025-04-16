import asyncio
import random

# MCP import (assuming this path is correct for your project)
from mcp.server.fastmcp import FastMCP
from instagram import InstagramServer, logger

# === MCP Tool Definitions ===

mcp = FastMCP("instagram-server")
instagram = InstagramServer()  # Instantiate the server class

@mcp.tool()
async def access_instagram() -> str:
    """Access Instagram homepage, ensuring the main feed content is loaded. Uses refresh if needed."""
    logger.info("Tool 'access_instagram' called.")
    await instagram.init()
    page = instagram.page # Ensure page is available after init

    # Handle case where page might not be initialized (though init should raise)
    if not page:
        logger.error("Page object not initialized after init call.")
        return "Error: Page object not initialized."

    target_url = "https://www.instagram.com/"
    main_content_selector = instagram.selectors["feed"]["content"]

    try:
        logger.info("Navigating to Instagram homepage: %s", target_url)
        # Using domcontentloaded is often faster and sufficient for checking initial elements
        await page.goto(target_url, wait_until="domcontentloaded", timeout=20000)
        logger.info("Initial page load attempt done. Checking for main content...")

        # Create locator and wait directly
        main_content = page.locator(main_content_selector)
        try:
            # Use wait_for directly on the locator
            await main_content.wait_for(state="visible", timeout=15000)
            logger.info("Main content loaded on first try!")
            await asyncio.sleep(random.uniform(0.5, 1.0)) # Keep small delay
            return "Opened Instagram homepage successfully."
        except Exception: # Catch timeout or other errors during wait_for
            logger.info("Main content not found quickly. Attempting page refresh...")
            # No screenshot here
            await page.reload(wait_until="domcontentloaded", timeout=45000)
            logger.info("Page reloaded. Waiting for main content again...")

            try:
                # Wait again after reload
                await main_content.wait_for(state="visible", timeout=30000)
                logger.info("Refresh successful, main content loaded!")
                await asyncio.sleep(random.uniform(0.5, 1.5)) # Keep small delay
                return "Opened Instagram homepage successfully after refresh."
            except Exception: # Catch timeout or other errors on second wait
                logger.error("Main content not found even after refresh.")
                # No screenshot here
                return "Failed to load main content after refresh."

    except Exception as e:
        logger.error("Error accessing Instagram homepage: %s", e, exc_info=True)
        # No screenshot here
        return f"Error accessing Instagram homepage: {e}"


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


# Removed scroll_instagram_feed tool


# Removed snapshot_instagram_page_tree tool


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
    # The global instance 'instagram' is already created above
    try:
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received, stopping server.")
    except Exception as e:
        logger.critical("MCP server failed to run: %s", e, exc_info=True)
    finally:
        logger.info("Executing final browser cleanup...")

        async def close_browser_sync():
            # Use the global 'instagram' instance defined above
            if hasattr(instagram, "browser") and instagram.browser:
                logger.info("Ensuring browser is closed on server exit...")
                await instagram.close()
            else:
                logger.info("Browser already closed or not initialized on exit.")

        try:
            # Prefer asyncio.run for simplicity if no loop is guaranteed running
            asyncio.run(close_browser_sync())
        except RuntimeError as e:
            # This can happen if the event loop is already closed
            logger.info(f"Could not run final cleanup (loop likely stopped): {e}")
        logger.info("Instagram MCP server stopped.")
