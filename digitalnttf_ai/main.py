"""
Digital NTTF Auto Solver - Main Automation Entrypoint
Executes the full automated pipeline sequentially with a strict state machine:
START -> Launch Chrome -> Login -> Assignments (Subject-by-Subject, Row-by-Row) -> Practice Tests (Subject-by-Subject, Row-by-Row) -> Final Report
"""

import sys
import time
import argparse
from enum import Enum
from pathlib import Path

from config import Config
from logger import log_event, logger
from browser import BrowserController
from login import LoginManager
from library import LibraryManager
from question_engine import QuestionEngine
from assignment import AssignmentAutomation
from practice_test import PracticeTestAutomation
from groq_client import GroqClient, create_groq_client
from database import Database

class AutomationState(str, Enum):
    IDLE = "IDLE"
    LOGIN = "LOGIN"
    ASSIGNMENTS = "ASSIGNMENTS"
    ASSIGNMENT_RUNNING = "ASSIGNMENT_RUNNING"
    ASSIGNMENT_VERIFYING = "ASSIGNMENT_VERIFYING"
    ALL_ASSIGNMENTS_COMPLETE = "ALL_ASSIGNMENTS_COMPLETE"
    PRACTICE_TESTS = "PRACTICE_TESTS"
    TEST_RUNNING = "TEST_RUNNING"
    TEST_VERIFYING = "TEST_VERIFYING"
    ALL_TESTS_COMPLETE = "ALL_TESTS_COMPLETE"
    FINISHED = "FINISHED"
    ERROR = "ERROR"

class SequentialAutomationRunner:
    def __init__(self):
        self.state = AutomationState.IDLE
        self.browser: BrowserController = None
        self.groq: GroqClient = None
        self.engine: QuestionEngine = None

    def set_state(self, new_state: AutomationState, details: str = ""):
        self.state = new_state
        log_event(f"STATE_{new_state.value}", details)

    def run(self) -> bool:
        """
        Main automated execution sequence.
        Guarantees strict single-activity and single-question progression.
        """
        print("\n" + "="*60)
        print("     DIGITAL NTTF FULL AUTO SOLVER (GROQ AI)")
        print("="*60)
        
        if not Config.validate():
            self.set_state(AutomationState.ERROR, "Configuration validation failed (missing credentials or Groq key)")
            return False

        self.browser = BrowserController(headless=Config.HEADLESS)
        
        try:
            # 1. Start Browser
            self.set_state(AutomationState.LOGIN, "Initializing Chrome browser window...")
            self.browser.start()
            log_event("STATUS", "Chrome browser window opened.")

            # 2. Login
            login_mgr = LoginManager(self.browser)
            log_event("STATUS", f"Authenticating user '{Config.USERNAME}' at {Config.LOGIN_URL}...")
            if not login_mgr.login():
                self.set_state(AutomationState.ERROR, "Authentication failed. Exiting automation.")
                self.browser.take_screenshot("fatal_login_failure")
                return False

            log_event("STATUS", "Login successful! Proceeding to coursework...")

            # Initialize Groq client and question engine
            self.groq = create_groq_client(api_key=Config.GROQ_API_KEY, preferred_model=Config.GROQ_MODEL)
            self.engine = QuestionEngine(self.browser, groq_client=self.groq)
            assignment_auto = AssignmentAutomation(self.browser, self.engine)
            test_auto = PracticeTestAutomation(self.browser, self.engine)
            lib_mgr = LibraryManager(self.browser)

            completed_assignments = []
            failed_assignments = []
            completed_tests = []
            failed_tests = []
            total_questions_processed = 0

            # 3. Process Assignments
            if Config.AUTOMATION_MODE in ("all", "assignments_only", "assignments"):
                self.set_state(AutomationState.ASSIGNMENTS, "Opening Assignments portal...")
                lib_mgr.navigate_to_assignments()

                # Discover available subjects
                subjects = lib_mgr.discover_subject_cards()
                target_subjects = []

                if Config.TARGET_SUBJECT and Config.TARGET_SUBJECT.lower() != "all":
                    target_subjects = [s for s in subjects if Config.TARGET_SUBJECT.lower() in s["name"].lower()]
                    if not target_subjects:
                        target_subjects = [{"name": Config.TARGET_SUBJECT}]
                else:
                    target_subjects = subjects if subjects else [{"name": "Current Subject"}]

                log_event("STATUS", f"Processing Assignments across {len(target_subjects)} subject category(s)...")

                for s_idx, subj in enumerate(target_subjects, 1):
                    subj_name = subj.get("name", f"Subject {s_idx}")
                    log_event("SUBJECT", f"Processing Subject [{s_idx}/{len(target_subjects)}]: '{subj_name}'")
                    
                    if subj.get("element"):
                        lib_mgr.select_subject_card(subj_name)

                    # Scan assignments under this subject
                    assignments = lib_mgr.discover_assignments_in_current_view()
                    startable_assignments = [a for a in assignments if a.get("can_start")]

                    log_event("STATUS", f"Found {len(startable_assignments)} active assignment(s) in '{subj_name}'.")

                    for a_idx, assign in enumerate(startable_assignments, 1):
                        title = assign.get("title", f"Assignment {a_idx}")
                        self.set_state(AutomationState.ASSIGNMENT_RUNNING, f"[{subj_name}] Starting Assignment {a_idx}/{len(startable_assignments)}: '{title}'")
                        
                        opened = lib_mgr.start_assignment_row(assign)
                        if opened:
                            res = assignment_auto.run_assignment(title)
                            if res.get("status") == "completed":
                                self.set_state(AutomationState.ASSIGNMENT_VERIFYING, f"Verified completion of '{title}' (Answered: {res.get('answered', 0)})")
                                completed_assignments.append(res)
                                total_questions_processed += res.get("answered", 0)
                            else:
                                log_event("WARNING", f"Assignment '{title}' did not pass verification (status: {res.get('status')})")
                                failed_assignments.append({"title": title, "reason": f"Verification failed (status: {res.get('status')})"})
                                if not Config.CONTINUE_ON_ERROR:
                                    self.set_state(AutomationState.ERROR, f"Halted: Assignment '{title}' verification failed.")
                                    return False

                            # Return to assignments list
                            log_event("STATUS", "Returning to Assignments page for next coursework item...")
                            lib_mgr.navigate_to_assignments()
                            if subj.get("element"):
                                lib_mgr.select_subject_card(subj_name)
                        else:
                            log_event("ERROR", f"Could not start assignment row '{title}'.")
                            failed_assignments.append({"title": title, "reason": "Row could not be opened"})
                            if not Config.CONTINUE_ON_ERROR:
                                self.set_state(AutomationState.ERROR, f"Halted: Could not start assignment row '{title}'.")
                                return False

                if len(completed_assignments) > 0 and len(failed_assignments) == 0:
                    self.set_state(AutomationState.ALL_ASSIGNMENTS_COMPLETE, f"Completed all {len(completed_assignments)} assignment(s).")
                    log_event("STATUS", f"=== ALL ASSIGNMENTS COMPLETED ({len(completed_assignments)} total) ===")
                elif len(completed_assignments) > 0:
                    log_event("WARNING", f"Assignments completed: {len(completed_assignments)}, Failed/Skipped: {len(failed_assignments)}")
                else:
                    log_event("WARNING", f"No assignments completed (Failed/Skipped: {len(failed_assignments)})")

            # 4. Process Practice Tests
            if Config.AUTOMATION_MODE in ("all", "tests_only", "practice_tests"):
                self.set_state(AutomationState.PRACTICE_TESTS, "Opening Practice Tests portal...")
                lib_mgr.navigate_to_practice_tests()

                # Discover available test subjects
                subjects = lib_mgr.discover_subject_cards()
                target_subjects = []

                if Config.TARGET_SUBJECT and Config.TARGET_SUBJECT.lower() != "all":
                    target_subjects = [s for s in subjects if Config.TARGET_SUBJECT.lower() in s["name"].lower()]
                    if not target_subjects:
                        target_subjects = [{"name": Config.TARGET_SUBJECT}]
                else:
                    target_subjects = subjects if subjects else [{"name": "Current Subject"}]

                log_event("STATUS", f"Processing Practice Tests across {len(target_subjects)} subject category(s)...")

                for s_idx, subj in enumerate(target_subjects, 1):
                    subj_name = subj.get("name", f"Subject {s_idx}")
                    log_event("SUBJECT", f"Processing Practice Tests for Subject [{s_idx}/{len(target_subjects)}]: '{subj_name}'")
                    
                    if subj.get("element"):
                        lib_mgr.select_subject_card(subj_name)

                    # Scan practice tests under this subject
                    tests = lib_mgr.discover_practice_tests_in_current_view()
                    startable_tests = [t for t in tests if t.get("can_start")]

                    log_event("STATUS", f"Found {len(startable_tests)} startable practice test(s) in '{subj_name}'.")

                    for t_idx, test in enumerate(startable_tests, 1):
                        title = test.get("title", f"Practice Test {t_idx}")
                        self.set_state(AutomationState.TEST_RUNNING, f"[{subj_name}] Starting Practice Test {t_idx}/{len(startable_tests)}: '{title}'")
                        
                        opened = lib_mgr.start_practice_test_row(test)
                        if opened:
                            res = test_auto.run_practice_test(title)
                            if res.get("status") == "completed":
                                self.set_state(AutomationState.TEST_VERIFYING, f"Verified completion of '{title}' (Score: {res.get('score', 'N/A')}, Answered: {res.get('answered', 0)})")
                                completed_tests.append(res)
                                total_questions_processed += res.get("answered", 0)
                            else:
                                log_event("WARNING", f"Practice Test '{title}' did not pass verification (status: {res.get('status')})")
                                failed_tests.append({"title": title, "reason": f"Verification failed (status: {res.get('status')})"})
                                if not Config.CONTINUE_ON_ERROR:
                                    self.set_state(AutomationState.ERROR, f"Halted: Practice test '{title}' verification failed.")
                                    return False

                            # Return to practice tests list
                            log_event("STATUS", "Returning to Practice Tests page for next test item...")
                            lib_mgr.navigate_to_practice_tests()
                            if subj.get("element"):
                                lib_mgr.select_subject_card(subj_name)
                        else:
                            log_event("ERROR", f"Could not start practice test row '{title}'.")
                            failed_tests.append({"title": title, "reason": "Row could not be opened"})
                            if not Config.CONTINUE_ON_ERROR:
                                self.set_state(AutomationState.ERROR, f"Halted: Could not start practice test row '{title}'.")
                                return False

                if len(failed_tests) == 0:
                    self.set_state(AutomationState.ALL_TESTS_COMPLETE, f"Completed all {len(completed_tests)} practice test(s).")
                    log_event("STATUS", f"=== ALL PRACTICE TESTS COMPLETED ({len(completed_tests)} total) ===")
                else:
                    log_event("WARNING", f"Practice tests completed: {len(completed_tests)}, Failed/Skipped: {len(failed_tests)}")

            # 5. Final Report & Status Determination
            total_failed = len(failed_assignments) + len(failed_tests)
            total_completed = len(completed_assignments) + len(completed_tests)

            if total_completed > 0 and total_failed == 0:
                final_overall_status = "COMPLETED"
                status_msg = f"All {total_completed} automation tasks completed successfully."
            elif total_completed > 0 and total_failed > 0:
                final_overall_status = "PARTIAL"
                status_msg = f"Completed {total_completed} activities. {total_failed} activity(s) failed or skipped."
            elif total_failed > 0:
                final_overall_status = "FAILED"
                status_msg = f"Automation failed: 0 activities completed, {total_failed} failed."
            else:
                final_overall_status = "NO_ACTIVITIES_FOUND"
                status_msg = "No startable assignments or practice tests found."

            self.set_state(AutomationState.FINISHED, status_msg)
            print("\n" + "="*60)
            print(f"          DIGITAL NTTF AUTOMATION: {final_overall_status}")
            print("="*60)
            print(f" Assignments Completed:   {len(completed_assignments)}")
            if failed_assignments:
                print(f" Assignments Failed:      {len(failed_assignments)}")
            print(f" Practice Tests Solved:   {len(completed_tests)}")
            if failed_tests:
                print(f" Practice Tests Failed:   {len(failed_tests)}")
            print(f" Total Questions Solved:  {total_questions_processed}")
            ai_model_name = self.groq.model if (self.groq and self.groq.model) else Config.GROQ_MODEL
            print(f" AI Model Used:           Groq ({ai_model_name})")
            print(f" Final Status:            {final_overall_status}")
            print("="*60 + "\n")

            log_event("FINISHED", f"Run Result ({final_overall_status}): {len(completed_assignments)} Assignments, {len(completed_tests)} Practice Tests solved.")
            return final_overall_status == "COMPLETED"

        except KeyboardInterrupt:
            self.set_state(AutomationState.ERROR, "Automation stopped by user.")
            return False
        except Exception as e:
            self.set_state(AutomationState.ERROR, f"Unexpected automation exception: {e}")
            if self.browser:
                self.browser.take_screenshot("unexpected_crash")
            return False
        finally:
            if self.browser:
                self.browser.stop()

def main():
    parser = argparse.ArgumentParser(description="Digital NTTF AI Auto Solver (Groq AI)")
    parser.add_argument("--username", type=str, help="Digital NTTF Username")
    parser.add_argument("--password", type=str, help="Digital NTTF Password")
    parser.add_argument("--groq-key", type=str, help="Groq API Key")
    parser.add_argument("--groq-model", type=str, help="Groq Model name")
    parser.add_argument("--subject", type=str, default="all", help="Target subject (e.g. 'Advanced PLC' or 'all')")
    parser.add_argument("--mode", type=str, default="all", help="Automation mode ('all', 'assignments_only', 'tests_only')")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    parser.add_argument("--auto-submit", action="store_true", help="Automatically submit tests without prompting")
    args = parser.parse_args()

    if args.username:
        Config.USERNAME = args.username
    if args.password:
        Config.PASSWORD = args.password
    if args.groq_key:
        Config.GROQ_API_KEY = args.groq_key
    if args.groq_model:
        Config.GROQ_MODEL = args.groq_model
    if args.subject:
        Config.TARGET_SUBJECT = args.subject
    if args.mode:
        Config.AUTOMATION_MODE = args.mode
    if args.headless:
        Config.HEADLESS = True
    if args.auto_submit:
        Config.AUTO_SUBMIT = True

    runner = SequentialAutomationRunner()
    success = runner.run()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
