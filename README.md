## 📡 `server.py` – Instagram Automation MCP Server

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10+-blue?logo=python&style=flat-square)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Automation-Playwright-45ba63?logo=microsoft&style=flat-square)](https://playwright.dev/)
[![FastMCP](https://img.shields.io/badge/Agent-FastMCP-FFD700?style=flat-square)](https://github.com/juand-r/playwright-mcp)
[![Gemini](https://img.shields.io/badge/LLM-Gemini-4285F4?logo=google&style=flat-square)](https://ai.google.dev/)
[![Instagram](https://img.shields.io/badge/Automates-Instagram-E4405F?logo=instagram&style=flat-square)](https://instagram.com/)
[![Logging Enabled](https://img.shields.io/badge/Logs-Enabled-brightgreen?style=flat-square)](instagram_server.log)
[![Screenshots](https://img.shields.io/badge/Screenshots-Enabled-blueviolet?style=flat-square)](instagram_screenshots/)

### 🔧 What it does
Runs a Playwright-based FastMCP server to control Instagram through a visible browser:
- Opens stories and simulates viewing
- Likes and comments on posts
- Scrolls feed
- Loads cookies from `cookies/instagram.json`
- Takes screenshots for every action
- Handles UI failures gracefully with logging and fallbacks

### 🛠️ How to run
```bash
python server.py
```

### 💻 Available Tools
- `access_instagram()`: Open homepage (refreshes if needed)
- `like_instagram_post(post_url)`
- `comment_on_instagram_post(post_url, comment)`
- `scroll_instagram_feed(scrolls=1)`
- `view_instagram_stories()`: Opens and simulates story view
- `interact_with_story(action)`: One of `"next"`, `"previous"`, `"like"`, `"reply"`
- `close_instagram()`

### 📁 Logs & Screenshots
- Logs: `instagram_server.log`
- Screenshots: `instagram_screenshots/`

---

## 🧠 `client.py` – Gemini + MCP Client

### 🔧 What it does
Connects to your MCP server via `stdio`, then uses Gemini to:
- Decide which tool to use based on a plain-text user query
- Call the tool and display the result

### 🛠️ How to run
```bash
python client.py path/to/server.py
```

### 🔁 Usage Flow
- You type: `like this post https://www.instagram.com/p/xxxxx/`
- Gemini picks the best tool and fills in arguments
- The client parses Gemini’s response and executes it via MCP
- You get the tool result or a Gemini parse error

### ✅ Dependencies
- Requires `.env` with:
  ```
  GEMINI_API_KEY=your-key-here
  ```

---

## 🔧 Pending Fixes

- [ ] **Story interaction buttons sometimes invisible or hidden (`tabindex=-1`)** — fallback via `keyboard.press("ArrowRight")` works but needs more robustness.
- [ ] **Story viewer detection** (`div[role="dialog"]`) is unreliable post-first interaction.
- [ ] **Like/comment on feed posts** hasn't been validated end-to-end recently.
- [ ] **Pause button in stories often times out** — fallback logic works but may miss timing.

---

## 🚀 Future Steps

- [ ] Add detection of whether the story viewer is *still open* using multiple fallback methods (DOM + pixel check).
- [ ] Add **auto-follow**, **unfollow**, **view profile**, and **save post** interactions.
- [ ] Add a session tracker (e.g. track what posts were already interacted with).
- [ ] Add Instagram **DM tool** (optional).
- [ ] Add real-time debugging commands via a dev tool.
- [ ] Introduce **screenshot diffing or pixel analysis** to detect visual success (e.g. next story loaded).
- [ ] Enable headless mode with optional video recording for CI/debug.

---
