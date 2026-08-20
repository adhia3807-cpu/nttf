"""
Digital NTTF Auto Solver - Practice Test Automation
Handles Practice Test execution: detects timers, answers questions via Gemini,
submits test, and extracts score results.
"""

import time
import re
from typing import Dict, Any, Optional
from playwright.sync_api import Page

from config import Config, SELECTORS
from browser import BrowserController
from question_engine import QuestionEngine
from database import Database
from logger import log_event, logger

class PracticeTestAutomation:
    def __init__(self, browser_ctrl: BrowserController, question_engine: Optional[QuestionEngine] = None):
        self.browser = browser_ctrl
        self.page: Page = self.browser.page
        self.engine = question_engine or QuestionEngine(browser_ctrl)
        self.db = Database()

    def run_practice_test(self, test_title: str = "Practice Test") -> Dict[str, Any]:
        """Execute full Practice Test automation."""
        log_event("PRACTICE_TEST_STARTED", f"Starting Practice Test: '{test_title}'")
        
        activity_id = self.db.create_activity(test_title, "practice_test")
        
        # 1. Start Test button
        start_btn = self.browser.find_first_element(SELECTORS["question"]["start_buttons"], timeout=3000)
        if start_btn and start_btn.is_visible():
            start_btn.click()
            self.browser.wait_for_idle(2000)

        # 2. Check initial timer
        timer_info = self.browser.read_timer()
        if timer_info:
            log_event("TIMER_DETECTED", f"Active Test Timer: {timer_info['text']}")

        # 3. Question Loop
        answered_count = 0
        unresolved_count = 0
        max_questions = 150
        last_question_text = ""
        stuck_counter = 0

        for iteration in range(1, max_questions + 1):
            q_res = self.engine.process_current_question(activity_id, "practice_test")
            current_q_text = q_res.get("question_text", "").strip()
            
            # Loop protection: detect if question didn't change
            if current_q_text and current_q_text == last_question_text:
                stuck_counter += 1
                if stuck_counter >= 3:
                    log_event("WARNING", f"Detected state loop at question '{current_q_text[:40]}...'. Breaking loop.")
                    break
            else:
                stuck_counter = 0
                last_question_text = current_q_text

            if q_res["success"]:
                answered_count += 1
            else:
                unresolved_count += 1

            q_num = q_res.get("question_number", iteration)
            self.db.update_activity_progress(activity_id, answered_count, q_res.get("total_questions"))

            # Check for Submit or Next
            submit_btn = self.browser.find_first_element(SELECTORS["question"]["submit_buttons"], timeout=1000)
            next_btn = self.browser.find_first_element(SELECTORS["question"]["next_buttons"], timeout=2000)

            if not next_btn and submit_btn:
                log_event("SUBMISSION_STARTED", f"Final question reached (Q{q_num}). Submitting test...")
                break

            if next_btn:
                log_event("NEXT_CLICKED", f"Advancing from Q{q_num} to next question...")
                self.browser.safe_click(next_btn)
                self.browser.wait_for_idle(800)
                if self._check_if_completed():
                    break
            else:
                if self._check_if_completed():
                    break
                time.sleep(1)

        # 4. Submit
        if Config.AUTO_SUBMIT:
            log_event("SUBMISSION_STARTED", "Submitting Practice Test...")
            self._execute_submit()
        else:
            log_event("SUBMISSION_PAUSED", "AUTO_SUBMIT=false. Review in browser.")

        # 5. Extract Score / Result
        results = self._extract_results(activity_id, test_title, answered_count)
        self.db.mark_session_completed(activity_id)
        return results

    def _check_if_completed(self) -> bool:
        """Check if test reached result view."""
        res_elem = self.browser.find_first_element(SELECTORS["question"]["result"], timeout=1000)
        return bool(res_elem and res_elem.is_visible())

    def _execute_submit(self):
        """Submit test and click confirmation dialog."""
        submit_btn = self.browser.find_first_element(SELECTORS["question"]["submit_buttons"], timeout=3000)
        if submit_btn and submit_btn.is_visible():
            submit_btn.click()
            self.browser.wait_for_idle(1000)

            confirm_btn = self.browser.find_first_element(SELECTORS["question"]["confirm_submit_buttons"], timeout=3000)
            if confirm_btn and confirm_btn.is_visible():
                confirm_btn.click()
                self.browser.wait_for_idle(2500)
        log_event("SUBMISSION_COMPLETED", "Practice Test submitted.")

    def _extract_results(self, activity_id: int, test_title: str, answered_count: int) -> Dict[str, Any]:
        """Extract score and metrics from result page."""
        self.browser.wait_for_idle(2000)
        result_loc = self.browser.find_first_element(SELECTORS["question"]["result"], timeout=3000)
        score = None
        percentage = None
        status = "completed"

        if result_loc:
            try:
                res_text = result_loc.inner_text()
                score_match = re.search(r'score\s*[\:\-]?\s*(\d+(?:\.\d+)?)\s*(?:\/|\s*out of\s*)\s*(\d+(?:\.\d+)?)', res_text, re.IGNORECASE)
                if score_match:
                    score = float(score_match.group(1))
                    max_score = float(score_match.group(2))
                    if max_score > 0:
                        percentage = (score / max_score) * 100

                pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%', res_text)
                if pct_match and percentage is None:
                    percentage = float(pct_match.group(1))
            except Exception:
                pass

        self.db.complete_activity(activity_id, score=score, percentage=percentage, status=status)
        log_event("RESULT_DETECTED", f"Test: '{test_title}' | Answered: {answered_count} | Score: {score} | Percentage: {percentage}%")

        return {
            "activity_id": activity_id,
            "title": test_title,
            "answered": answered_count,
            "score": score,
            "percentage": percentage,
            "status": status
        }
