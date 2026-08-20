"""
Digital NTTF Auto Solver - Robust Authentication State Machine
Implements a resilient, condition-based login state machine with dynamic DOM polling,
strict error detection, and progressive retry backoff.
"""

import time
from enum import Enum
from typing import Optional, Dict, Any
from playwright.sync_api import Page, Locator

from config import Config, SELECTORS
from browser import BrowserController
from logger import log_event, logger


class LoginState(str, Enum):
    LOGIN_OPENING = "LOGIN_OPENING"
    LOGIN_PAGE_READY = "LOGIN_PAGE_READY"
    USERNAME_READY = "USERNAME_READY"
    PASSWORD_READY = "PASSWORD_READY"
    SUBMITTING = "SUBMITTING"
    AUTHENTICATING = "AUTHENTICATING"
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILED = "LOGIN_FAILED"
    LOGIN_RETRY = "LOGIN_RETRY"
    LOGIN_ERROR = "LOGIN_ERROR"


class LoginManager:
    def __init__(self, browser_ctrl: BrowserController):
        self.browser = browser_ctrl
        self.page: Page = self.browser.page
        self.state = LoginState.LOGIN_OPENING

    def set_state(self, state: LoginState, message: str = ""):
        self.state = state
        if message:
            log_event(state.value, message)

    def login(self, max_retries: int = Config.MAX_LOGIN_ATTEMPTS) -> bool:
        """
        Execute automated login using a robust state machine.
        Retries ONLY on transient timeouts / network delays, NOT on invalid credentials.
        """
        if not Config.USERNAME or not Config.PASSWORD:
            log_event("ERROR", "Credentials missing. Set DIGITAL_NTTF_USERNAME and DIGITAL_NTTF_PASSWORD.")
            return False

        retry_delay = Config.RETRY_DELAY / 1000.0  # 3.0 seconds

        for attempt in range(1, max_retries + 1):
            log_event("LOGIN_ATTEMPT", f"Authentication attempt {attempt}/{max_retries} for '{Config.USERNAME}'")
            start_attempt_time = time.time()

            try:
                # Step 1: Open Login Page & Wait until ready
                self.set_state(LoginState.LOGIN_OPENING, f"Opening login page: {Config.LOGIN_URL}")
                log_event("LOGIN", "Opening login page")
                log_event("LOGIN", "Waiting for login UI...")

                nav_ok = self.browser.navigate_to(Config.LOGIN_URL)
                if not nav_ok:
                    log_event("WARNING", f"Navigation to {Config.LOGIN_URL} failed on attempt {attempt}.")
                    self._handle_retry(attempt, max_retries, retry_delay)
                    retry_delay *= 2
                    continue

                # Step 2: Check Existing Authenticated Session
                if self.is_logged_in():
                    self.set_state(LoginState.LOGIN_SUCCESS, "Existing authenticated session detected")
                    return True

                # Wait for login page UI to mount (username input, password input, or login button)
                page_ready = self._wait_for_login_page_ready(timeout_ms=Config.LOGIN_PAGE_TIMEOUT)
                if not page_ready:
                    # Check again if page redirected to authenticated session
                    if self.is_logged_in():
                        self.set_state(LoginState.LOGIN_SUCCESS, "Existing authenticated session detected")
                        return True

                    log_event("WARNING", f"Login UI did not render within {Config.LOGIN_PAGE_TIMEOUT/1000}s.")
                    self.browser.take_screenshot(f"login_timeout_attempt_{attempt}")
                    self._handle_retry(attempt, max_retries, retry_delay)
                    retry_delay *= 2
                    continue

                self.set_state(LoginState.LOGIN_PAGE_READY, "Login page ready")

                # Step 3: Find Username Field & Fill
                user_input = self._wait_for_field(SELECTORS["login"]["username_inputs"], timeout_ms=Config.USERNAME_FIELD_TIMEOUT)
                if not user_input or not user_input.is_visible():
                    log_event("ERROR", "Username field not found or not visible.")
                    self.browser.take_screenshot(f"no_username_field_attempt_{attempt}")
                    self._handle_retry(attempt, max_retries, retry_delay)
                    retry_delay *= 2
                    continue

                self.set_state(LoginState.USERNAME_READY, "Username field ready")
                self.browser.safe_fill(user_input, Config.USERNAME)

                # Verify username is populated
                try:
                    current_val = user_input.input_value()
                    if current_val.strip() != Config.USERNAME.strip():
                        log_event("WARNING", "Username input value mismatch, refilling...")
                        user_input.fill(Config.USERNAME)
                except Exception:
                    pass

                # Step 4: Find Password Field & Fill
                pass_input = self._wait_for_field(SELECTORS["login"]["password_inputs"], timeout_ms=Config.PASSWORD_FIELD_TIMEOUT)
                if not pass_input or not pass_input.is_visible():
                    log_event("ERROR", "Password field not found or not visible.")
                    self.browser.take_screenshot(f"no_password_field_attempt_{attempt}")
                    self._handle_retry(attempt, max_retries, retry_delay)
                    retry_delay *= 2
                    continue

                self.set_state(LoginState.PASSWORD_READY, "Password field ready")
                self.browser.safe_fill(pass_input, Config.PASSWORD)

                # Verify password is populated (do NOT log password content)
                try:
                    pass_val = pass_input.input_value()
                    if not pass_val:
                        log_event("WARNING", "Password input empty, refilling...")
                        pass_input.fill(Config.PASSWORD)
                except Exception:
                    pass

                # Step 5: Submit Credentials
                self.set_state(LoginState.SUBMITTING, "Credentials submitted")
                log_event("LOGIN", "Credentials submitted")
                log_event("LOGIN", "Waiting for authentication...")

                submit_btn = self._wait_for_field(SELECTORS["login"]["submit_buttons"], timeout_ms=Config.LOGIN_BUTTON_TIMEOUT)
                if submit_btn and submit_btn.is_visible():
                    self.browser.safe_click(submit_btn, highlight_color="#2563eb")
                else:
                    pass_input.press("Enter")

                # Step 6: Poll Authentication State
                self.set_state(LoginState.AUTHENTICATING)
                auth_result, auth_elapsed = self._poll_authentication_state(timeout_ms=Config.AUTHENTICATION_TIMEOUT)

                if auth_result == "SUCCESS":
                    self.set_state(LoginState.LOGIN_SUCCESS, f"Authentication successful after {auth_elapsed:.1f}s")
                    # Allow brief settle for post-login scripts
                    self._settle_post_login()
                    return True
                elif auth_result == "INVALID_CREDENTIALS":
                    self.set_state(LoginState.LOGIN_FAILED, "Server rejected credentials")
                    self.browser.take_screenshot("login_rejected")
                    log_event("ERROR", "Authentication failed: Server rejected credentials. Halting retries.")
                    return False
                elif auth_result == "CAPTCHA":
                    self.set_state(LoginState.LOGIN_FAILED, "Human verification required")
                    log_event("LOGIN_BLOCKED", "Human verification required (CAPTCHA). Keep browser open.")
                    return False
                else:
                    # Timeout / Unresolved
                    log_event("WARNING", f"Authentication timed out after {Config.AUTHENTICATION_TIMEOUT/1000}s on attempt {attempt}.")
                    self.browser.take_screenshot(f"auth_timeout_attempt_{attempt}")
                    self._handle_retry(attempt, max_retries, retry_delay)
                    retry_delay *= 2

            except Exception as e:
                self.set_state(LoginState.LOGIN_ERROR, f"Exception during login attempt {attempt}: {e}")
                self.browser.take_screenshot(f"login_exception_attempt_{attempt}")
                self._handle_retry(attempt, max_retries, retry_delay)
                retry_delay *= 2

        self.set_state(LoginState.LOGIN_FAILED, f"Login failed after {max_retries} attempts.")
        return False

    def is_logged_in(self) -> bool:
        """
        Check if browser currently holds a valid authenticated student session.
        Uses strong authenticated markers (assignments link, practice test link, dashboard content, student profile).
        Strictly does NOT rely on a generic header element alone.
        """
        if not self.page:
            return False

        try:
            current_url = self.page.url.lower()
            # 1. URL check
            if any(path in current_url for path in ["/assignments", "/practice-test", "/dashboard", "/library", "/classroom"]):
                if "/login" not in current_url:
                    return True

            # 2. Strong Navigation & Content Markers
            strong_markers = [
                "a[href*='/assignments']",
                "a[href*='/practice-test']",
                "a[href*='/dashboard']",
                "div[role='button']:has-text('Assignments')",
                "div[role='button']:has-text('Practice Test')",
                "span:has-text('Assignments')",
                "span:has-text('Practice Test')",
                "button:has-text('Logout')",
                "a:has-text('Logout')",
                ".user-profile",
                ".avatar",
                "div:has-text('LMS Points')",
                "div:has-text('Subject Progress')",
                "div:has-text('Semester')",
            ]

            for sel in strong_markers:
                loc = self.page.locator(sel).first
                if loc.count() > 0 and loc.is_visible():
                    return True

            # 3. Check if login inputs are gone and main dashboard structure is present
            has_user_input = self.page.locator("input[name='username'], input[type='password']").first.count() > 0
            if not has_user_input:
                dashboard_content = self.page.locator("main, div#root, div.app").first
                if dashboard_content.count() > 0 and dashboard_content.is_visible():
                    text = self.page.locator("body").inner_text()
                    if ("Assignments" in text or "Practice Test" in text or "Course" in text) and "Sign in" not in text:
                        return True

        except Exception:
            pass

        return False

    def _wait_for_login_page_ready(self, timeout_ms: int = 45000) -> bool:
        """Wait dynamically for login elements or existing authenticated session."""
        start_t = time.time()
        timeout_sec = timeout_ms / 1000.0

        while time.time() - start_t < timeout_sec:
            if self.is_logged_in():
                return True

            # Check for login inputs
            for sel in SELECTORS["login"]["username_inputs"] + SELECTORS["login"]["password_inputs"]:
                try:
                    loc = self.page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        return True
                except Exception:
                    pass

            time.sleep(0.3)

        return False

    def _wait_for_field(self, selector_list: list, timeout_ms: int = 20000) -> Optional[Locator]:
        """Wait for any selector in the list to become visible within timeout."""
        start_t = time.time()
        timeout_sec = timeout_ms / 1000.0

        while time.time() - start_t < timeout_sec:
            for sel in selector_list:
                try:
                    loc = self.page.locator(sel).first
                    if loc.count() > 0 and loc.is_visible():
                        return loc
                except Exception:
                    pass
            time.sleep(0.2)

        return None

    def _poll_authentication_state(self, timeout_ms: int = 45000) -> tuple[str, float]:
        """
        Poll DOM every 300-500ms to detect login success, error, or challenge.
        Returns (result_status, elapsed_seconds).
        """
        start_t = time.time()
        timeout_sec = timeout_ms / 1000.0

        while time.time() - start_t < timeout_sec:
            elapsed = time.time() - start_t

            # 1. Check Login Success
            if self.is_logged_in():
                return "SUCCESS", elapsed

            # 2. Check for Explicit Error Markers
            for err_sel in SELECTORS["login"]["error_markers"]:
                try:
                    err_loc = self.page.locator(err_sel).first
                    if err_loc.count() > 0 and err_loc.is_visible():
                        err_text = err_loc.inner_text().strip()
                        log_event("ERROR", f"Portal login error message: '{err_text}'")
                        return "INVALID_CREDENTIALS", elapsed
                except Exception:
                    pass

            # Body text error checks
            try:
                body_text = self.page.locator("body").inner_text().lower()
                if "invalid credentials" in body_text or "incorrect password" in body_text or "invalid username" in body_text:
                    return "INVALID_CREDENTIALS", elapsed
                if "account locked" in body_text or "too many attempts" in body_text:
                    return "INVALID_CREDENTIALS", elapsed
                if "captcha" in body_text or "human verification" in body_text:
                    return "CAPTCHA", elapsed
            except Exception:
                pass

            # 3. Check for CAPTCHA
            if self.browser.check_for_captcha():
                return "CAPTCHA", elapsed

            time.sleep(0.4)

        return "TIMEOUT", time.time() - start_t

    def _settle_post_login(self):
        """Allow post-login React state and token cookies to settle smoothly."""
        start_t = time.time()
        timeout_sec = Config.POST_LOGIN_SETTLE_TIMEOUT / 1000.0

        while time.time() - start_t < min(timeout_sec, 3.0):
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=1000)
                break
            except Exception:
                time.sleep(0.3)

    def _handle_retry(self, attempt: int, max_retries: int, delay_sec: float):
        """Log retry state with exponential backoff delay."""
        if attempt < max_retries:
            self.set_state(LoginState.LOGIN_RETRY, f"Retrying login in {delay_sec:.0f}s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(delay_sec)
