"""
Digital NTTF Auto Solver - Playwright Browser Controller
Handles browser lifecycle, resilient navigation, element detection, visual highlighting,
and smooth element interaction for live user observation.
"""

import time
import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Locator

from config import Config, SELECTORS
from logger import log_event, logger

class BrowserController:
    def __init__(self, headless: Optional[bool] = None, channel: Optional[str] = None):
        self.headless = Config.HEADLESS if headless is None else headless
        self.channel = Config.BROWSER_CHANNEL if channel is None else channel
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.is_running = False

    def start(self) -> Page:
        """Launch Playwright Chromium/Chrome browser."""
        if self.is_running and self.page:
            return self.page

        log_event("START", "Launching Chrome browser...")
        log_event("START", f"Headless: {self.headless}")
        log_event("START", f"Visual mode: {Config.VISUAL_MODE}")
        log_event("START", f"Browser channel: {self.channel if self.channel else 'default chromium'}")

        self.playwright = sync_playwright().start()
        
        launch_args = [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
            "--start-maximized",
        ]
        
        slow_mo_val = Config.BROWSER_SLOW_MO if not self.headless else 0

        # Try launching real Google Chrome if channel is configured
        launched = False
        if self.channel:
            try:
                self.browser = self.playwright.chromium.launch(
                    channel=self.channel,
                    headless=self.headless,
                    slow_mo=slow_mo_val,
                    args=launch_args
                )
                launched = True
            except Exception as e:
                if not self.headless:
                    log_event("WARNING", f"Could not launch channel='{self.channel}' ({e}). Attempting Playwright Chromium in visible mode...")
                else:
                    log_event("WARNING", f"Could not launch channel='{self.channel}' ({e}).")

        # Standard Chromium launch
        if not launched:
            try:
                self.browser = self.playwright.chromium.launch(
                    headless=self.headless,
                    slow_mo=slow_mo_val,
                    args=launch_args
                )
                launched = True
            except Exception as launch_err:
                if not self.headless and Config.IS_RENDER:
                    # Only fallback on Render/cloud containers if display server is missing
                    log_event("WARNING", f"Visible display unavailable on cloud container ({launch_err}). Switching to headless cloud mode...")
                    self.headless = True
                    self.browser = self.playwright.chromium.launch(
                        headless=True,
                        slow_mo=0,
                        args=launch_args
                    )
                else:
                    if not self.headless:
                        log_event("ERROR", f"Could not launch visible Google Chrome ({launch_err}). Make sure Google Chrome is installed.")
                        raise RuntimeError(f"Could not launch visible Google Chrome ({launch_err}). Make sure Google Chrome is installed on your Windows PC.")
                    raise launch_err

        self.context = self.browser.new_context(
            viewport={"width": 1400, "height": 850},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            ignore_https_errors=True
        )

        self.page = self.context.new_page()
        self.page.set_default_navigation_timeout(Config.NAV_TIMEOUT)
        self.page.set_default_timeout(Config.ACTION_TIMEOUT)
        self.is_running = True

        if not self.headless:
            log_event("BROWSER_OPENED", "Visible Chrome browser launched successfully.")
        else:
            log_event("BROWSER_OPENED", "Headless browser launched successfully (Cloud mode).")

        return self.page

    def stop(self, force: bool = False):
        """Close browser and teardown resources cleanly."""
        if not force and Config.KEEP_BROWSER_OPEN and not self.headless:
            delay_sec = int(Config.BROWSER_CLOSE_DELAY / 1000)
            log_event("BROWSER_PERSIST", f"Keeping Chrome browser open for inspection for {delay_sec}s...")
            try:
                time.sleep(delay_sec)
            except KeyboardInterrupt:
                pass

        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
        self.is_running = False
        log_event("BROWSER_CLOSED", "Browser session ended.")

    def navigate_to(self, url: str, wait_until: str = "domcontentloaded") -> bool:
        """Navigate to URL with error capture."""
        if not self.page:
            self.start()

        log_event("NAVIGATION", f"Opening {url}")
        try:
            self.page.goto(url, wait_until=wait_until, timeout=Config.NAV_TIMEOUT)
            self.wait_for_idle(500)
            return True
        except Exception as e:
            log_event("ERROR", f"Failed to navigate to {url}: {e}")
            self.take_screenshot("nav_error")
            return False

    def wait_for_idle(self, ms: int = 400):
        """Wait for page load stability and visual pacing."""
        try:
            self.page.wait_for_load_state("networkidle", timeout=1500)
        except Exception:
            pass
        delay = max(ms, Config.VISUAL_DELAY if Config.VISUAL_MODE and not self.headless else 100)
        self.page.wait_for_timeout(delay)

    def highlight_element(self, locator: Locator, color: str = "#ff5722", duration_ms: int = 250):
        """Visually highlights an element before clicking/interacting in visible Chrome mode."""
        if self.headless or not Config.VISUAL_MODE:
            return
        try:
            locator.evaluate(f"""(el) => {{
                const originalOutline = el.style.outline;
                const originalTransition = el.style.transition;
                el.style.transition = 'all 0.15s ease-in-out';
                el.style.outline = '3px solid {color}';
                el.style.boxShadow = '0 0 10px {color}';
                setTimeout(() => {{
                    el.style.outline = originalOutline;
                    el.style.boxShadow = '';
                    el.style.transition = originalTransition;
                }}, {duration_ms});
            }}""")
            self.page.wait_for_timeout(duration_ms)
        except Exception:
            pass

    def find_first_element(self, selector_list: List[str], parent: Optional[Locator] = None, timeout: int = 3000) -> Optional[Locator]:
        """Find the first matching visible element across selector fallbacks."""
        root = parent if parent is not None else self.page
        for sel in selector_list:
            try:
                loc = root.locator(sel).first
                if loc.is_visible(timeout=timeout):
                    return loc
            except Exception:
                continue
        return None

    def find_all_elements(self, selector_list: List[str], parent: Optional[Locator] = None) -> List[Locator]:
        """Find all matching elements from selector fallbacks."""
        root = parent if parent is not None else self.page
        for sel in selector_list:
            try:
                locs = root.locator(sel)
                count = locs.count()
                if count > 0:
                    return [locs.nth(i) for i in range(count)]
            except Exception:
                continue
        return []

    def safe_click(self, locator_or_selectors, highlight_color: str = "#2563eb", timeout: int = 4000) -> bool:
        """Click element safely with visual highlight and smooth alignment."""
        try:
            if isinstance(locator_or_selectors, list):
                loc = self.find_first_element(locator_or_selectors, timeout=timeout)
                if not loc:
                    return False
            else:
                loc = locator_or_selectors

            # Scroll into view gently
            self.scroll_to_element(loc)
            
            # Visual highlight before clicking
            self.highlight_element(loc, color=highlight_color, duration_ms=250)

            # Perform click
            try:
                loc.click(timeout=timeout)
            except Exception:
                loc.click(force=True, timeout=timeout)

            self.wait_for_idle(300)
            return True
        except Exception as e:
            log_event("ERROR", f"Safe click failed: {e}")
            return False

    def safe_fill(self, locator_or_selectors, value: str, timeout: int = 4000) -> bool:
        """Fill input element safely with visual highlight."""
        try:
            if isinstance(locator_or_selectors, list):
                loc = self.find_first_element(locator_or_selectors, timeout=timeout)
                if not loc:
                    return False
            else:
                loc = locator_or_selectors

            self.scroll_to_element(loc)
            self.highlight_element(loc, color="#10b981", duration_ms=200)

            try:
                loc.fill(value, timeout=timeout)
            except Exception:
                loc.fill(value, force=True, timeout=timeout)

            return True
        except Exception as e:
            log_event("ERROR", f"Safe fill failed: {e}")
            return False

    def scroll_to_element(self, locator: Locator):
        """Gently scrolls target element into viewport center."""
        try:
            locator.evaluate("el => el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' })")
        except Exception:
            pass

    def take_screenshot(self, name_prefix: str) -> str:
        """Capture screenshot for error auditing."""
        if not self.page:
            return ""
        try:
            Config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{name_prefix}_{int(time.time())}.png"
            filepath = Config.SCREENSHOTS_DIR / filename
            self.page.screenshot(path=str(filepath), full_page=True)
            return str(filepath)
        except Exception:
            return ""

    def check_for_captcha(self) -> bool:
        """Check for CAPTCHA or verification challenge and allow user to solve."""
        captcha_loc = self.find_first_element(SELECTORS["login"]["captcha_markers"], timeout=1000)
        if captcha_loc and captcha_loc.is_visible():
            log_event("SECURITY_CHECK", "CAPTCHA detected. Solve in browser window.")
            self.wait_for_idle(2000)
            return True
        return False

    def read_timer(self) -> Optional[Dict[str, Any]]:
        """Read active test countdown timer if present."""
        timer_loc = self.find_first_element(SELECTORS["question"]["timer"], timeout=1000)
        if not timer_loc:
            return None

        try:
            text = timer_loc.inner_text().strip()
            match = re.search(r'(\d+):(\d+)(?::(\d+))?', text)
            if match:
                parts = [p for p in match.groups() if p is not None]
                if len(parts) == 2:
                    total_sec = int(parts[0]) * 60 + int(parts[1])
                elif len(parts) == 3:
                    total_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
                else:
                    total_sec = 0
                return {"text": text, "seconds": total_sec}
        except Exception:
            pass
        return None
