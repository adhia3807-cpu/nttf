"""
Digital NTTF Auto Solver - Library & Activity Manager
Accurately navigates the real Digital NTTF Assignments and Practice Tests pages,
discovers Subject Cards, and locates exact row-level Start and Take Test buttons.
"""

import time
import re
from typing import List, Dict, Any, Optional
from playwright.sync_api import Page, Locator

from config import Config, SELECTORS
from browser import BrowserController
from logger import log_event, logger

class LibraryManager:
    def __init__(self, browser_ctrl: BrowserController):
        self.browser = browser_ctrl
        self.page: Page = self.browser.page

    def navigate_to_assignments(self) -> bool:
        """Open Assignments page directly or via sidebar."""
        log_event("NAVIGATION", f"Opening Assignments: {Config.ASSIGNMENTS_URL}")
        success = self.browser.navigate_to(Config.ASSIGNMENTS_URL)
        if success:
            self.browser.wait_for_idle(1000)
            log_event("STATUS", "Assignments view loaded.")
        return success

    def navigate_to_practice_tests(self) -> bool:
        """Open Practice Tests page directly or via sidebar."""
        log_event("NAVIGATION", f"Opening Practice Tests: {Config.PRACTICE_TEST_URL}")
        success = self.browser.navigate_to(Config.PRACTICE_TEST_URL)
        if success:
            self.browser.wait_for_idle(1000)
            log_event("STATUS", "Practice Tests view loaded.")
        return success

    def discover_subject_cards(self) -> List[Dict[str, Any]]:
        """
        Extract visible subject cards (e.g. Advanced PLC, Robotics, CNC Technology, Product Design & Development).
        Strictly excludes sidebar items, user profile banners, and non-academic headers.
        """
        subjects = []
        seen_names = set()

        # Non-academic strings to exclude
        NON_SUBJECT_TERMS = {
            "dashboard", "classroom", "practice test", "assignments", "achievers", "jobs",
            "faculty", "skill library", "my notes", "notice board", "rewards", "feed",
            "adhi", "semester", "points", "student", "logout", "settings", "menu", "profile",
            "lms points", "marks obtained", "submitted", "done", "left", "viewing",
            "all assignments", "manage and submit", "subject progress", "filter assignments"
        }

        # Look specifically in Subject Progress section or cards
        card_selectors = [
            "div:has-text('Subject Progress') ~ div div[class*='card']",
            "div:has-text('Subject Progress') div[class*='Card']",
            "div:has-text('Viewing')",
            "div[class*='SubjectCard']",
            "div[class*='subject-card']",
            ".subject-card",
        ]
        
        cards = self.browser.find_all_elements(card_selectors)
        if not cards:
            # Fallback to broader card scan
            cards = self.browser.find_all_elements(["div:has-text('left')", "div:has(h4)", ".card"])

        for card in cards:
            try:
                if not card.is_visible():
                    continue
                
                text = card.inner_text().strip()
                lines = [l.strip() for l in text.split("\n") if l.strip()]
                if not lines:
                    continue

                subject_name = ""
                # 1. Match known Digital NTTF technical subjects
                for known in [
                    "CNC Technology (CP15 Sem5)", "CNC Technology",
                    "Product Design & Development", "Product Design",
                    "Advanced PLC", "Robotics"
                ]:
                    for l in lines:
                        if known.lower() in l.lower():
                            subject_name = l
                            break
                    if subject_name:
                        break

                # 2. If not matched, inspect top non-excluded line
                if not subject_name:
                    for l in lines:
                        clean_l = l.lower().strip()
                        if any(term in clean_l for term in NON_SUBJECT_TERMS):
                            continue
                        if clean_l.isdigit() or len(l) < 3 or len(l) > 60:
                            continue
                        # If line has standard subject casing / letters
                        if re.search(r'[A-Za-z]', l):
                            subject_name = l
                            break

                # Exclude non-academic noise
                if subject_name:
                    clean_check = subject_name.lower().strip()
                    if any(clean_check == term or (len(clean_check) < 15 and term in clean_check) for term in NON_SUBJECT_TERMS):
                        continue

                    if subject_name not in seen_names and len(subject_name) < 60:
                        seen_names.add(subject_name)
                        subjects.append({
                            "name": subject_name,
                            "element": card
                        })
            except Exception:
                continue

        log_event("STATUS", f"Discovered {len(subjects)} academic subject(s): {[s['name'] for s in subjects]}")
        return subjects

    def select_subject_card(self, subject_name: str) -> bool:
        """Click on a subject card to filter the table below to that subject."""
        log_event("SUBJECT_SELECT", f"Selecting Subject: '{subject_name}'")
        cards = self.discover_subject_cards()
        for subj in cards:
            if subject_name.lower() in subj["name"].lower() or subj["name"].lower() in subject_name.lower():
                try:
                    self.browser.safe_click(subj["element"], highlight_color="#3b82f6")
                    self.browser.wait_for_idle(1000)
                    log_event("STATUS", f"Switched to subject '{subj['name']}'")
                    return True
                except Exception as e:
                    log_event("WARNING", f"Could not click subject card '{subject_name}': {e}")
        
        # Fallback: search text directly
        card_loc = self.browser.page.locator(f"div:has-text('{subject_name}')").last
        if card_loc and card_loc.count() > 0 and card_loc.is_visible():
            self.browser.safe_click(card_loc, highlight_color="#3b82f6")
            self.browser.wait_for_idle(1000)
            return True

        return False

    def discover_assignments_in_current_view(self) -> List[Dict[str, Any]]:
        """
        Scan the assignments table in the current view.
        Returns assignment items with their row locator and exact Start button locator.
        """
        assignments = []
        seen_titles = set()

        # Find rows in the assignment table
        row_locators = self.browser.find_all_elements([
            "tbody tr",
            "tr:has-text('Assignment-')",
            "tr:has-text('Assignment')",
            "div[class*='row']:has-text('Assignment-')",
            "div[class*='assignment-item']",
        ])

        for idx, row in enumerate(row_locators):
            try:
                if not row.is_visible():
                    continue

                row_text = row.inner_text().strip()
                if not row_text or "ASSIGNMENT" in row_text and "QUESTIONS" in row_text:
                    # Skip header row
                    continue

                # Find exact Start button in THIS row
                start_btn = row.locator("button:has-text('Start'), a:has-text('Start'), button:has-text('Resume'), button:has-text('Attempt')").first
                has_start = start_btn.count() > 0 and start_btn.is_visible()

                # Extract Assignment title (e.g. "Assignment-1. PLC ANALOG SIGNALS")
                match = re.search(r'(Assignment\s*[-–—]?\s*\d+[\.\:\s][^\n\r]+)', row_text, re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
                else:
                    lines = [l.strip() for l in row_text.split("\n") if l.strip()]
                    title = lines[0] if lines else f"Assignment {idx+1}"

                # Clean title
                title = re.sub(r'\s+(?:Pending|Submitted|Mid Term|End Term|\d+\s*Qs).*$', '', title, flags=re.IGNORECASE).strip()

                if title in seen_titles:
                    continue
                seen_titles.add(title)

                # Status
                status = "Pending" if "pending" in row_text.lower() else ("Submitted" if "submitted" in row_text.lower() else "Available")

                assignments.append({
                    "id": len(assignments) + 1,
                    "title": title,
                    "type": "assignment",
                    "status": status,
                    "row_element": row,
                    "action_button": start_btn if has_start else None,
                    "can_start": has_start
                })
            except Exception:
                continue

        log_event("STATUS", f"Found {len(assignments)} Assignment row(s) (Pending / Startable: {sum(1 for a in assignments if a['can_start'])})")
        return assignments

    def discover_practice_tests_in_current_view(self) -> List[Dict[str, Any]]:
        """
        Scan the practice test table in the current view.
        Returns test items with their row locator and exact Take Test button locator.
        """
        tests = []
        seen_titles = set()

        # Find rows in the test table
        row_locators = self.browser.find_all_elements([
            "tbody tr",
            "tr:has-text('Practice Test')",
            "tr:has-text('Take Test')",
            "div[class*='row']:has-text('Practice Test')",
            "div[class*='test-item']",
        ])

        for idx, row in enumerate(row_locators):
            try:
                if not row.is_visible():
                    continue

                row_text = row.inner_text().strip()
                if not row_text or "TEST NAME" in row_text and "DURATION" in row_text:
                    # Skip header row
                    continue

                # Find exact Take Test button in THIS row
                take_btn = row.locator("button:has-text('Take Test'), a:has-text('Take Test'), button:has-text('Start Test'), a:has-text('Start Test')").first
                has_take = take_btn.count() > 0 and take_btn.is_visible()

                # Extract Test title (e.g. "Practice Test - 1. Introduction To Computerised Numerical Control")
                match = re.search(r'(Practice Test\s*[-–—]?\s*\d+[\.\:\s][^\n\r]+)', row_text, re.IGNORECASE)
                if match:
                    title = match.group(1).strip()
                else:
                    lines = [l.strip() for l in row_text.split("\n") if l.strip()]
                    title = lines[0] if lines else f"Practice Test {idx+1}"

                # Clean title
                title = re.sub(r'\s+(?:Available|Completed|Mid Term|End Term|\d+m|7\.50).*$', '', title, flags=re.IGNORECASE).strip()

                if title in seen_titles:
                    continue
                seen_titles.add(title)

                status = "Available" if "available" in row_text.lower() else ("Completed" if "completed" in row_text.lower() else "Available")

                tests.append({
                    "id": len(tests) + 1,
                    "title": title,
                    "type": "practice_test",
                    "status": status,
                    "row_element": row,
                    "action_button": take_btn if has_take else None,
                    "can_start": has_take
                })
            except Exception:
                continue

        log_event("STATUS", f"Found {len(tests)} Practice Test row(s) (Startable: {sum(1 for t in tests if t['can_start'])})")
        return tests

    def start_assignment_row(self, assignment_item: Dict[str, Any]) -> bool:
        """Visually click the exact Start button belonging to this assignment."""
        title = assignment_item.get("title", "Assignment")
        btn = assignment_item.get("action_button")
        
        log_event("ACTION", f"Opening Assignment '{title}'...")
        if btn and btn.count() > 0 and btn.is_visible():
            self.browser.safe_click(btn, highlight_color="#ff5722")
            self.browser.wait_for_idle(1500)
            return True

        # Fallback to row click
        row: Locator = assignment_item.get("row_element")
        if row and row.count() > 0:
            start_fallback = row.locator("button, a").first
            if start_fallback.count() > 0 and start_fallback.is_visible():
                self.browser.safe_click(start_fallback, highlight_color="#ff5722")
                self.browser.wait_for_idle(1500)
                return True

        return False

    def start_practice_test_row(self, test_item: Dict[str, Any]) -> bool:
        """Visually click the exact Take Test button belonging to this practice test."""
        title = test_item.get("title", "Practice Test")
        btn = test_item.get("action_button")
        
        log_event("ACTION", f"Opening Practice Test '{title}'...")
        if btn and btn.count() > 0 and btn.is_visible():
            self.browser.safe_click(btn, highlight_color="#2563eb")
            self.browser.wait_for_idle(1500)
            return True

        # Fallback to row click
        row: Locator = test_item.get("row_element")
        if row and row.count() > 0:
            take_fallback = row.locator("button, a").first
            if take_fallback.count() > 0 and take_fallback.is_visible():
                self.browser.safe_click(take_fallback, highlight_color="#2563eb")
                self.browser.wait_for_idle(1500)
                return True

        return False
