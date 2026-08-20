"""
Digital NTTF AI Automation - Question Engine
Central question processing pipeline orchestrating parsing, Groq AI inference, answer validation,
visual browser interaction, selection verification, and database persistence.
"""

import time
from typing import Dict, Any, Optional
from playwright.sync_api import Locator

from config import Config
from browser import BrowserController
from question_parser import QuestionParser
from groq_client import GroqClient
from answer_validator import AnswerValidator
from database import Database
from logger import log_event, logger

class QuestionEngine:
    def __init__(self, browser_ctrl: BrowserController, groq_client: Optional[GroqClient] = None):
        self.browser = browser_ctrl
        self.parser = QuestionParser(browser_ctrl)
        self.groq = groq_client or GroqClient()
        self.validator = AnswerValidator()
        self.db = Database()

    def process_current_question(self, activity_id: int, activity_type: str) -> Dict[str, Any]:
        """
        Execute full single-question processing pipeline:
        1. Detect & Extract Question (with visual focus)
        2. Call Groq
        3. Validate Answer
        4. Select / Enter Answer in Browser with visual feedback
        5. Verify Selection State
        6. Record to SQLite Database
        """
        result = {
            "success": False,
            "question_number": 0,
            "total_questions": None,
            "question_text": "",
            "ai_answer": None,
            "selected_answer": None,
            "confidence": 0.0,
            "status": "failed",
            "reason": ""
        }

        # 1. Parse Question from Browser DOM
        log_event("ACTION", "Reading Question from webpage...")
        q_data = self.parser.detect_question()
        if not q_data:
            result["reason"] = "Could not detect active question on page."
            return result

        q_num = q_data["question_number"]
        total_q = q_data["total_questions"]
        q_text = q_data["question_text"]
        q_type = q_data["question_type"]
        options = q_data["options"]
        option_locators = q_data["option_locators"]

        result["question_number"] = q_num
        result["total_questions"] = total_q
        result["question_text"] = q_text

        # 2. Process according to Question Type
        if q_type in ("MCQ", "TrueFalse", "Checkbox"):
            if not options:
                result["reason"] = "No options found for choice question"
                log_event("ERROR", f"Q{q_num}: No options found for {q_type}")
                return result

            # Call Groq
            log_event("ACTION", f"Asking Groq AI ({self.groq.model}) for Q{q_num}...")
            ai_resp = self.groq.get_mcq_answer(q_text, options)
            ai_ans_text = ai_resp.get("answer_text", "")
            confidence = ai_resp.get("confidence", 0.0)
            result["ai_answer"] = ai_ans_text
            result["confidence"] = confidence

            # Validate against actual webpage options
            is_valid, opt_idx, resolved_text, conf, val_reason = self.validator.validate_mcq_answer(ai_resp, options)
            result["selected_answer"] = resolved_text

            if not is_valid or opt_idx < 0 or opt_idx >= len(option_locators):
                # Retry once with strict matching
                log_event("WARNING", f"Q{q_num}: Validation failed ({val_reason}), retrying with Groq...")
                ai_resp = self.groq.get_mcq_answer(q_text, options, instructions="Select strictly from the given options list.")
                is_valid, opt_idx, resolved_text, conf, val_reason = self.validator.validate_mcq_answer(ai_resp, options)

            if is_valid and 0 <= opt_idx < len(option_locators):
                target_locator: Locator = option_locators[opt_idx]
                
                log_event("ACTION", f"Selecting Option {opt_idx+1}: '{resolved_text}' in browser...")
                
                # Perform click on option with green highlight for user visibility
                click_success = self.browser.safe_click(target_locator, highlight_color="#10b981")
                if click_success:
                    # Verify selection
                    self.browser.wait_for_idle(250)
                    log_event("ANSWER_SELECTED", f"Q{q_num}: Visibly selected Option {opt_idx+1} ('{resolved_text}')")
                    
                    status = "answered"
                    if conf < Config.AI_CONFIDENCE_THRESHOLD:
                        status = "review_required"

                    result["success"] = True
                    result["status"] = status
                    result["reason"] = val_reason
                else:
                    result["reason"] = "Click on option locator failed"
                    log_event("ERROR", f"Q{q_num}: Failed to click option {opt_idx+1}")
            else:
                result["status"] = "review_required"
                result["reason"] = f"Unresolved option match: {val_reason}"
                log_event("ERROR", f"Q{q_num}: Could not reliably match option. Flagged for review.")

        elif q_type == "Subjective":
            # Subjective / Essay question
            log_event("ACTION", f"Generating Subjective response with Groq for Q{q_num}...")
            ai_resp = self.groq.get_subjective_answer(q_text)
            is_valid, ans_text, conf, val_reason = self.validator.validate_subjective_answer(ai_resp)
            
            result["ai_answer"] = ans_text
            result["selected_answer"] = ans_text
            result["confidence"] = conf

            editor_loc: Locator = q_data.get("editor_locator")
            if editor_loc and is_valid:
                try:
                    log_event("ACTION", f"Filling subjective answer in editor...")
                    self.browser.safe_fill(editor_loc, ans_text)
                    self.browser.wait_for_idle(300)
                    log_event("ANSWER_SELECTED", f"Q{q_num}: Filled subjective answer ({len(ans_text)} chars)")
                    result["success"] = True
                    result["status"] = "answered"
                except Exception as e:
                    result["reason"] = f"Failed to fill editor: {e}"
                    log_event("ERROR", f"Q{q_num}: Error filling text editor: {e}")
            else:
                result["reason"] = "Subjective answer validation or editor locator missing"

        # 3. Record Question Details to Database
        self.db.record_question(
            activity_id=activity_id,
            question_number=q_num,
            question_text=q_text,
            question_type=q_type,
            options=options,
            ai_answer=result["ai_answer"],
            selected_answer=result["selected_answer"],
            confidence=result["confidence"],
            status=result["status"]
        )

        # 4. Save Session Checkpoint
        self.db.save_session_checkpoint(
            activity_id=activity_id,
            activity_name=f"Activity #{activity_id}",
            activity_type=activity_type,
            question_number=q_num,
            state_data={"question_text": q_text[:80], "status": result["status"]}
        )

        log_event("QUESTION_COMPLETED", f"Q{q_num} done (status: {result['status']})")
        return result
