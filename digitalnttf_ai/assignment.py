"""
Digital NTTF Auto Solver - Assignment Automation
Handles end-to-end Assignment execution. Automatically detects Long Answer assignments
(Instructions modal -> Question table -> Textarea submission) and MCQ assignments.
"""

import time
from typing import Dict, Any, Optional
from playwright.sync_api import Page

from config import Config, SELECTORS
from browser import BrowserController
from question_engine import QuestionEngine
from assignment_long_answer import LongAnswerAssignmentAutomation
from database import Database
from logger import log_event, logger

class AssignmentAutomation:
    def __init__(self, browser_ctrl: BrowserController, question_engine: Optional[QuestionEngine] = None):
        self.browser = browser_ctrl
        self.page: Page = self.browser.page
        self.engine = question_engine or QuestionEngine(browser_ctrl)
        self.long_answer_handler = LongAnswerAssignmentAutomation(browser_ctrl, groq_client=self.engine.groq)
        self.db = Database()

    def run_assignment(self, assignment_title: str = "Assignment") -> Dict[str, Any]:
        """Execute full Assignment automation with dynamic layout detection."""
        log_event("ASSIGNMENT_STARTED", f"Starting Assignment: '{assignment_title}'")
        
        # Check if Instructions modal, Question Table, or Long Answer elements are present
        self.browser.wait_for_idle(1000)
        is_long_answer = self._detect_long_answer_structure()

        if is_long_answer:
            log_event("STATUS", f"Detected Long-Answer Assignment workflow for '{assignment_title}'.")
            return self.long_answer_handler.run_assignment(assignment_title)

        # Standard Sequential Assignment Flow
        activity_id = self.db.create_activity(assignment_title, "assignment")

        # 1. Click Start / Open Assignment button if on intro page
        start_btn = self.browser.find_first_element(SELECTORS["question"]["start_buttons"], timeout=3000)
        if start_btn and start_btn.is_visible():
            start_btn.click()
            self.browser.wait_for_idle(2000)

        # 2. Question Processing Loop
        answered_count = 0
        unresolved_count = 0
        max_questions = 100
        last_question_text = ""
        stuck_counter = 0

        for iteration in range(1, max_questions + 1):
            q_res = self.engine.process_current_question(activity_id, "assignment")
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

            # Check for Next Button or Submit Button
            next_btn = self.browser.find_first_element(SELECTORS["question"]["next_buttons"], timeout=1500)
            submit_btn = self.browser.find_first_element(SELECTORS["question"]["submit_buttons"], timeout=1500)

            if not next_btn and submit_btn:
                log_event("SUBMISSION_STARTED", f"Reached last assignment question (Q{q_num}). Ready for submit.")
                break

            if next_btn:
                log_event("NEXT_CLICKED", f"Advancing to next question after Q{q_num}...")
                self.browser.safe_click(next_btn)
                self.browser.wait_for_idle(800)
            else:
                log_event("REVIEW_STAGE", "No further questions detected.")
                break

        # 3. Submit Assignment & Verify
        final_status = "completed"
        if Config.AUTO_SUBMIT:
            log_event("SUBMISSION_STARTED", "Submitting Assignment...")
            verified = self._submit_assignment()
            if not verified:
                final_status = "verification_failed"
                log_event("WARNING", f"Assignment submission could not be strictly verified.")
        else:
            log_event("SUBMISSION_PAUSED", "AUTO_SUBMIT=false. Review in browser.")

        self.db.complete_activity(activity_id, status=final_status)
        self.db.mark_session_completed(activity_id)

        log_event("SUBMISSION_COMPLETED", f"Assignment '{assignment_title}' finished with status '{final_status}'. Answered: {answered_count}")

        return {
            "activity_id": activity_id,
            "title": assignment_title,
            "answered": answered_count,
            "status": final_status
        }

    def _detect_long_answer_structure(self) -> bool:
        """Check if the current DOM exhibits the Digital NTTF Long Answer assignment structure."""
        long_answer_markers = [
            "div:has-text('Instructions')",
            "button:has-text('Start Assignment')",
            "div:has-text('Fullscreen Required')",
            "div:has-text('Question Title')",
            "div:has-text('Faculty-graded assignment')",
            "div:has-text('Long answer')",
            "td:has-text('Long answer')",
            "*:has-text('Long answer')",
            "div:has-text('Answer Submission')",
            "textarea"
        ]
        for marker in long_answer_markers:
            el = self.browser.find_first_element([marker], timeout=1000)
            if el and el.is_visible():
                return True
        try:
            body_txt = self.page.locator("body").inner_text()
            if "Long answer" in body_txt or "Faculty-graded" in body_txt or "Start Assignment" in body_txt:
                return True
        except Exception:
            pass
        return False

    def _submit_assignment(self) -> bool:
        """Click submit, handle confirmation dialog, and verify portal confirmation."""
        submit_btn = self.browser.find_first_element(SELECTORS["question"]["submit_buttons"], timeout=3000)
        if submit_btn and submit_btn.is_visible():
            submit_btn.click()
            self.browser.wait_for_idle(1000)
            confirm_btn = self.browser.find_first_element(SELECTORS["question"]["confirm_submit_buttons"], timeout=2000)
            if confirm_btn and confirm_btn.is_visible():
                confirm_btn.click()
            self.browser.wait_for_idle(2000)

            # Verification: check if submission is confirmed or question container is gone
            success_markers = [
                "div:has-text('submitted successfully')",
                "div:has-text('Assignment Completed')",
                "div:has-text('Submitted')",
                "div:has-text('Score')",
                ".result-card",
                "a[href*='/library']"
            ]
            marker = self.browser.find_first_element(success_markers, timeout=3000)
            if marker and marker.is_visible():
                log_event("SUBMISSION_VERIFIED", "Assignment submission verified by portal response.")
                return True
            
            # If redirected away from test form, also consider verified
            if "/library" in self.browser.page.url.lower() or "/dashboard" in self.browser.page.url.lower():
                log_event("SUBMISSION_VERIFIED", "Redirected to library after assignment submission.")
                return True

            # If submit button is no longer visible, submission went through
            if not submit_btn.is_visible():
                return True
                
        return False
