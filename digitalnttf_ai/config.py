"""
Digital NTTF Auto Solver - Configuration Module
Single unified configuration source for Playwright, Groq AI, and portal selectors.
Supports real visible Google Chrome on local Windows and headless Chromium on Cloud (Render).
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

def parse_bool(value, default=False):
    """Safely parse string/env values into booleans."""
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")

class Config:
    # Detect Environment
    IS_RENDER = parse_bool(os.getenv("RENDER"), default=False) or bool(os.getenv("RENDER_SERVICE_ID"))
    IS_WINDOWS = sys.platform.startswith("win")
    IS_MAC = sys.platform.startswith("darwin")

    # Portal URLs (Based on real Digital NTTF routes)
    BASE_URL = os.getenv("DIGITAL_NTTF_BASE_URL", "https://digitalnttf.com")
    LOGIN_URL = os.getenv("DIGITAL_NTTF_LOGIN_URL", "https://digitalnttf.com/login")
    DASHBOARD_URL = os.getenv("DIGITAL_NTTF_DASHBOARD_URL", "https://digitalnttf.com/dashboard")
    ASSIGNMENTS_URL = os.getenv("DIGITAL_NTTF_ASSIGNMENTS_URL", "https://digitalnttf.com/assignments")
    PRACTICE_TEST_URL = os.getenv("DIGITAL_NTTF_PRACTICE_TEST_URL", "https://digitalnttf.com/practice-test")
    LIBRARY_URL = os.getenv("DIGITAL_NTTF_LIBRARY_URL", "https://digitalnttf.com/assignments")

    # Credentials (passed securely at runtime / environment from UI)
    USERNAME = os.getenv("DIGITAL_NTTF_USERNAME", "")
    PASSWORD = os.getenv("DIGITAL_NTTF_PASSWORD", "")

    # Groq AI Settings
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_REQUEST_DELAY = float(os.getenv("GROQ_REQUEST_DELAY", "0.2"))
    AI_CONFIDENCE_THRESHOLD = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.60"))
    MAX_AI_RETRIES = int(os.getenv("MAX_AI_RETRIES", "2"))

    # Automation Behavior & Visual Mode
    # Local Windows defaults to Headless=False (Visible Chrome window). Cloud (Render) defaults to Headless=True.
    _default_headless = True if IS_RENDER or (not IS_WINDOWS and not IS_MAC and not os.getenv("DISPLAY")) else False
    HEADLESS = parse_bool(os.getenv("HEADLESS"), default=_default_headless)
    
    VISUAL_MODE = parse_bool(os.getenv("VISUAL_MODE"), default=not HEADLESS)
    VISUAL_DELAY = int(os.getenv("VISUAL_DELAY", "400")) # ms
    KEEP_BROWSER_OPEN = parse_bool(os.getenv("KEEP_BROWSER_OPEN"), default=True)
    BROWSER_CLOSE_DELAY = int(os.getenv("BROWSER_CLOSE_DELAY", "30000")) # ms to keep browser open after completion
    AUTO_SUBMIT = parse_bool(os.getenv("AUTO_SUBMIT"), default=False)
    RESUME_ENABLED = parse_bool(os.getenv("RESUME_ENABLED"), default=True)
    CONTINUE_ON_ERROR = parse_bool(os.getenv("CONTINUE_ON_ERROR"), default=False)
    BROWSER_SLOW_MO = int(os.getenv("BROWSER_SLOW_MO", "500"))
    BROWSER_CHANNEL = os.getenv("BROWSER_CHANNEL", "chrome" if IS_WINDOWS else "").strip()

    # Target Activity Filter
    TARGET_SUBJECT = os.getenv("TARGET_SUBJECT", "all").strip()
    AUTOMATION_MODE = os.getenv("AUTOMATION_MODE", "all").strip().lower() # 'all' | 'assignments_only' | 'tests_only'

    # Storage Paths
    DATABASE_PATH = BASE_DIR / "digitalnttf.db"
    LOGS_DIR = BASE_DIR / "logs"
    SCREENSHOTS_DIR = BASE_DIR / "screenshots"
    LOG_FILE = LOGS_DIR / "automation.log"

    # Timeouts (ms)
    NAV_TIMEOUT = 30000
    ACTION_TIMEOUT = 10000
    CRITICAL_TIMER_SECONDS = 180

    # Specific State-Machine Timeouts (ms)
    LOGIN_PAGE_TIMEOUT = 45000
    USERNAME_FIELD_TIMEOUT = 20000
    PASSWORD_FIELD_TIMEOUT = 20000
    LOGIN_BUTTON_TIMEOUT = 20000
    AUTHENTICATION_TIMEOUT = 45000
    POST_LOGIN_SETTLE_TIMEOUT = 20000
    TOTAL_LOGIN_ATTEMPT_TIMEOUT = 90000
    MAX_LOGIN_ATTEMPTS = 3
    RETRY_DELAY = 3000

    ASSIGNMENTS_PAGE_TIMEOUT = 30000
    ASSIGNMENT_LIST_TIMEOUT = 30000
    INSTRUCTIONS_MODAL_TIMEOUT = 20000
    QUESTION_LIST_TIMEOUT = 30000
    QUESTION_START_TIMEOUT = 30000
    FULLSCREEN_TIMEOUT = 10000
    QUESTION_TEXT_TIMEOUT = 10000
    TEXTAREA_TIMEOUT = 15000
    SUBMIT_TIMEOUT = 30000
    SUBMISSION_VERIFICATION_TIMEOUT = 30000
    PRACTICE_TEST_PAGE_TIMEOUT = 30000

    @classmethod
    def validate(cls) -> bool:
        """Check for mandatory runtime configuration."""
        missing = []
        if not cls.USERNAME:
            missing.append("DIGITAL_NTTF_USERNAME")
        if not cls.PASSWORD:
            missing.append("DIGITAL_NTTF_PASSWORD")
        if not cls.GROQ_API_KEY:
            missing.append("GROQ_API_KEY")
        
        if missing:
            print("\n[!] Missing required credentials / API keys:")
            for m in missing:
                print(f"    - {m}")
            return False
        return True


SELECTORS = {
    "login": {
        "username_inputs": [
            "input[name='username']",
            "input[name='email']",
            "input[type='email']",
            "input[placeholder*='Username' i]",
            "input[placeholder*='Email' i]",
            "input[placeholder*='Roll' i]",
            "input[placeholder*='ID' i]",
            "#username",
            "#email",
            "input[type='text']",
        ],
        "password_inputs": [
            "input[name='password']",
            "input[type='password']",
            "input[placeholder*='Password' i]",
            "#password",
        ],
        "submit_buttons": [
            "button[type='submit']",
            "button:has-text('Login')",
            "button:has-text('Sign In')",
            "button:has-text('Log In')",
            "input[type='submit']",
            ".login-btn",
            "#login-button",
        ],
        "auth_success_markers": [
            "a[href*='/assignments']",
            "a[href*='/practice-test']",
            "a[href*='/dashboard']",
            "a[href*='/library']",
            "div:has-text('Assignments')",
            "div:has-text('Practice Tests')",
            "button:has-text('Logout')",
            ".user-profile",
            ".avatar",
            "header",
        ],
        "error_markers": [
            ".error-message",
            ".alert-danger",
            ".invalid-feedback",
            "div:has-text('Invalid credentials')",
            "div:has-text('Incorrect password')",
        ],
        "captcha_markers": [
            "iframe[src*='recaptcha']",
            "iframe[src*='hcaptcha']",
            ".g-recaptcha",
            "#captcha",
            "div:has-text('verification')",
        ]
    },
    "nav": {
        "assignments": [
            "a[href*='/assignments']",
            "div[role='button']:has-text('Assignments')",
            "button:has-text('Assignments')",
            "span:has-text('Assignments')",
        ],
        "practice_test": [
            "a[href*='/practice-test']",
            "div[role='button']:has-text('Practice Test')",
            "button:has-text('Practice Test')",
            "span:has-text('Practice Test')",
        ],
        "dashboard": [
            "a[href*='/dashboard']",
            "span:has-text('Dashboard')",
        ]
    },
    "subjects": {
        "cards": [
            "div:has-text('Viewing')",
            "div[class*='SubjectCard']",
            "div[class*='subject-card']",
            ".subject-card",
            "div:has(h4)",
            "div:has(h3)",
        ],
        "names": [
            "Advanced PLC",
            "Robotics",
            "CNC Technology",
            "Product Design & Development"
        ]
    },
    "assignments": {
        "table": [
            "table",
            "div[class*='Table']",
            "div[class*='assignment-list']",
            "div:has-text('ASSIGNMENT')",
        ],
        "rows": [
            "tbody tr",
            "tr:has-text('Assignment-')",
            "tr:has-text('Assignment')",
            "div[class*='row']:has-text('Assignment')",
        ],
        "start_buttons": [
            "button:has-text('Start')",
            "a:has-text('Start')",
            ".btn-start",
            "button:has-text('Open')",
            "button:has-text('Resume')",
            "button:has-text('Attempt')",
        ]
    },
    "practice_test": {
        "table": [
            "table",
            "div[class*='Table']",
            "div[class*='test-list']",
            "div:has-text('TEST NAME')",
        ],
        "rows": [
            "tbody tr",
            "tr:has-text('Practice Test')",
            "tr:has-text('Take Test')",
            "div[class*='row']:has-text('Practice Test')",
        ],
        "take_test_buttons": [
            "button:has-text('Take Test')",
            "a:has-text('Take Test')",
            "button:has-text('Start Test')",
            "button:has-text('Take Test >')",
            ".btn-take-test",
        ]
    },
    "question": {
        "container": [
            ".question-container",
            ".question-card",
            "div[class*='QuestionWrapper']",
            "div[class*='QuestionBox']",
            ".question-content",
            "#question-area",
            "form.test-form",
            "div:has-text('Question')",
        ],
        "text": [
            ".question-text",
            ".question-title",
            "div[class*='QuestionText']",
            "h3.question-heading",
            "h4.question-heading",
            ".question-statement",
            "p.question",
            "div[class*='statement']",
        ],
        "counter": [
            ".question-counter",
            ".question-number",
            "div:has-text('Question ')",
            "span[class*='count']",
            "div[class*='QuestionNumber']",
            "span:has-text('Qs')",
        ],
        "option_items": [
            ".option-item",
            ".option-card",
            "label.option-label",
            "div[class*='OptionItem']",
            "div[class*='AnswerChoice']",
            "li.option",
            "label[class*='radio']",
            "label[class*='checkbox']",
            "div[role='radio']",
            "div[role='checkbox']",
        ],
        "radio_inputs": [
            "input[type='radio']",
            "input[type='checkbox']",
        ],
        "subjective_editors": [
            "textarea",
            "div[contenteditable='true']",
            ".ql-editor",
            ".DraftEditor-root",
            ".ProseMirror",
            ".rich-text-editor",
            "textarea[name='answer']",
        ],
        "next_buttons": [
            "button:has-text('Next')",
            "button:has-text('Save & Next')",
            "button:has-text('Next Question')",
            "button[class*='next']",
            "button#next-btn",
            "button:has-text('Save and Next')",
        ],
        "submit_buttons": [
            "button:has-text('Submit Test')",
            "button:has-text('Submit Assignment')",
            "button:has-text('Submit')",
            "button:has-text('Finish Test')",
            "button:has-text('Final Submit')",
            "button#submit-test-btn",
        ],
        "confirm_submit_buttons": [
            "button:has-text('Confirm Submit')",
            "button:has-text('Yes, Submit')",
            "button:has-text('Yes')",
            "button.btn-primary:has-text('Submit')",
            "button:has-text('Confirm')",
        ],
        "start_buttons": [
            "button:has-text('Start Test')",
            "button:has-text('Start Practice Test')",
            "button:has-text('Start Assignment')",
            "button:has-text('Begin Test')",
            "button:has-text('Start')",
            "button:has-text('Take Test')",
            "button:has-text('Open Assignment')",
            "button:has-text('Attempt Assignment')",
            "a:has-text('Start Test')",
            "a:has-text('Start Assignment')",
        ],
        "timer": [
            ".timer",
            ".test-timer",
            "div[class*='Timer']",
            "span[class*='timer']",
            "div:has-text('Time Remaining')",
            "div:has-text('Time Left')",
            "[data-testid='timer']",
            "span:has-text('30m')",
        ],
        "result": [
            ".test-result",
            ".result-card",
            "div[class*='ResultSummary']",
            ".score-card",
            "div:has-text('Score')",
            "div:has-text('Result')",
            "div:has-text('Submitted')",
            "div:has-text('submitted successfully')",
        ]
    }
}

# Compatibility aliases
SELECTORS["library"] = {
    "nav_library_link": SELECTORS["nav"]["assignments"],
    "cards": SELECTORS["subjects"]["cards"]
}
SELECTORS["test"] = SELECTORS["question"]
