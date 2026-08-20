"""
Digital NTTF AI Automation - Question Parser
Dynamically parses questions from the webpage DOM.
Extracts question statement, question number, total count, answer options,
and automatically identifies the question type (MCQ, True/False, Subjective, Checkbox, Dropdown).
"""

import re
from typing import Dict, Any, List, Optional, Tuple
from playwright.sync_api import Page, Locator

from config import SELECTORS
from browser import BrowserController
from logger import log_event, logger

class QuestionParser:
    def __init__(self, browser_ctrl: BrowserController):
        self.browser = browser_ctrl
        self.page: Page = self.browser.page

    def detect_question(self) -> Optional[Dict[str, Any]]:
        """
        Scan the active page to extract the current question payload.
        Returns:
            {
                "question_number": 1,
                "total_questions": 30,
                "question_text": "What is ...?",
                "question_type": "MCQ", # "MCQ" | "TrueFalse" | "Subjective" | "Checkbox" | "Dropdown"
                "options": ["Option A", "Option B", ...],
                "option_locators": [Locator, Locator, ...],
                "editor_locator": Optional[Locator],
                "container_locator": Optional[Locator]
            }
        """
        # 1. Locate Question Container
        container = self.browser.find_first_element(
            SELECTORS["question"]["container"],
            timeout=3000
        )

        # 2. Extract Question Number and Total Questions if visible
        q_num, total_q = self._extract_question_counter()

        # 3. Extract Question Statement Text
        q_text = self._extract_question_text(container)
        if not q_text:
            log_event("QUESTION_DETECTED", "No question text detected on page currently.")
            return None

        # 4. Check for Subjective Text Area / Rich Text Editor
        editor_loc = self.browser.find_first_element(SELECTORS["question"]["subjective_editors"], timeout=1000)
        if editor_loc and editor_loc.is_visible():
            # Check if there are also radio options; if not, it's subjective
            radios = self.browser.find_all_elements(SELECTORS["question"]["radio_inputs"])
            if len(radios) == 0:
                log_event("QUESTION_DETECTED", f"Q{q_num}: [Subjective] '{q_text[:70]}...'")
                return {
                    "question_number": q_num,
                    "total_questions": total_q,
                    "question_text": q_text,
                    "question_type": "Subjective",
                    "options": [],
                    "option_locators": [],
                    "editor_locator": editor_loc,
                    "container_locator": container
                }

        # 5. Extract Answer Options (Radio, Checkbox, List items)
        options, option_locators, q_type = self._extract_options(container)

        # Detect True/False
        if len(options) == 2:
            lower_opts = [o.lower() for o in options]
            if "true" in lower_opts and "false" in lower_opts:
                q_type = "TrueFalse"

        log_event("QUESTION_DETECTED", 
                  f"Q{q_num}/{total_q or '?'}: [{q_type}] '{q_text[:70]}...' ({len(options)} options)")

        return {
            "question_number": q_num,
            "total_questions": total_q,
            "question_text": q_text,
            "question_type": q_type,
            "options": options,
            "option_locators": option_locators,
            "editor_locator": None,
            "container_locator": container
        }

    def _extract_question_counter(self) -> Tuple[int, Optional[int]]:
        """Extract Question X of Y counter."""
        counter_elem = self.browser.find_first_element(
            SELECTORS["question"]["counter"], 
            timeout=1000
        )
        if counter_elem:
            try:
                text = counter_elem.inner_text().strip()
                # Matches "Question 12 of 60" or "Q12/60" or "12 / 60"
                match = re.search(r'(?:question|q)?\s*(\d+)\s*(?:of|\/)\s*(\d+)', text, re.IGNORECASE)
                if match:
                    return int(match.group(1)), int(match.group(2))
                
                # Matches "Question 12"
                single_match = re.search(r'(?:question|q)?\s*(\d+)', text, re.IGNORECASE)
                if single_match:
                    return int(single_match.group(1)), None
            except Exception:
                pass
        return 1, None

    def _extract_question_text(self, container: Optional[Locator]) -> str:
        """Find question prompt/statement text."""
        # Try specific question text selectors first
        q_elem = self.browser.find_first_element(
            SELECTORS["question"]["text"], 
            parent=container, 
            timeout=1500
        )
        if q_elem:
            try:
                text = q_elem.inner_text().strip()
                if len(text) > 3:
                    return self._clean_question_text(text)
            except Exception:
                pass

        # Fallback: Check headers or paragraphs in container
        if container:
            for tag in ["h2", "h3", "h4", "p", ".statement", "div[class*='text']"]:
                loc = container.locator(tag).first
                if loc.count() > 0 and loc.is_visible():
                    txt = loc.inner_text().strip()
                    if len(txt) > 10:
                        return self._clean_question_text(txt)

        return ""

    def _extract_options(self, container: Optional[Locator]) -> Tuple[List[str], List[Locator], str]:
        """Extract visible options strictly scoped within the question container."""
        options = []
        locators = []
        q_type = "MCQ"

        # If no container was passed, search within specific question wrapper
        scope = container
        if not scope:
            scope = self.browser.find_first_element(SELECTORS["question"]["container"], timeout=1000)

        # Look for option item elements within scope
        items = self.browser.find_all_elements(SELECTORS["question"]["option_items"], parent=scope)
        
        # If not found, look for radio/checkbox labels strictly within scope
        if not items and scope:
            items = self.browser.find_all_elements(["label[class*='option']", "label[class*='choice']", "div[role='radio']", "div[role='checkbox']"], parent=scope)

        for item in items:
            try:
                if not item.is_visible():
                    continue

                text = item.inner_text().strip()
                if not text or len(text) > 400: # Filter out entire card dumps
                    continue

                # Filter out obvious navigation / button text
                lower_t = text.lower()
                if lower_t in ("next", "previous", "prev", "submit", "submit test", "submit assignment", "save & next", "clear"):
                    continue

                # Clean option prefix (e.g. "A.", "1.", radio symbols)
                cleaned_text = re.sub(r'^[A-Da-d0-9][\.\)\-\:\s]+', '', text).strip()
                if not cleaned_text:
                    cleaned_text = text

                # Check if checkbox vs radio
                chk = item.locator("input[type='checkbox']").first
                if chk.count() > 0:
                    q_type = "Checkbox"

                options.append(cleaned_text)
                locators.append(item)
            except Exception:
                continue

        # If options are still empty, try finding radio/checkbox inputs directly within scope
        if not options:
            radios = self.browser.find_all_elements(SELECTORS["question"]["radio_inputs"], parent=scope)
            for idx, r in enumerate(radios):
                try:
                    if not r.is_visible():
                        continue
                    parent = r.locator("..")
                    txt = parent.inner_text().strip() or f"Option {idx+1}"
                    # Clean option text
                    cleaned = re.sub(r'^[A-Da-d0-9][\.\)\-\:\s]+', '', txt).strip() or txt
                    options.append(cleaned)
                    locators.append(r)
                except Exception:
                    pass

        return options, locators, q_type

    @staticmethod
    def _clean_question_text(text: str) -> str:
        """Strip extraneous question prefixes like 'Q.12'."""
        cleaned = re.sub(r'^(?:Question|Q|Q\.)\s*\d+[\.\:\-\s]*', '', text, flags=re.IGNORECASE).strip()
        return cleaned or text
