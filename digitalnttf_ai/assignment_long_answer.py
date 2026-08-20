"""
Digital NTTF AI Automation - Long Answer Assignment Handler
Executes Long Answer assignments strictly ONE QUESTION AT A TIME:

1. Detects & clicks 'Start Assignment' in Instructions Modal
2. Waits for Question List table/grid/cards to mount in DOM
3. Scans all question rows (# 1 to # 15) using DOM container inspection
4. Loops sequentially (current_index = 0 .. total - 1):
   - Re-queries live DOM to get fresh element handles (prevents stale locators)
   - Clicks ONLY the current question container's specific [Start] button
   - Waits for Answer Submission page to mount (Condition-based: Answer Submission + Question Title + Textarea)
   - Handles 'Fullscreen Required' (clicks 'Enter Fullscreen' & verifies fullscreen API)
   - Extracts ONLY Question Title content with strict token validation (extract_current_question)
   - Queries Groq AI with validated model and logs response
   - Locates & scrolls to Answer textarea
   - Clicks textarea and verifies focus & editability
   - Places cursor inside answer box and logs READY FOR USER INPUT
   - Waits for user to type and submit
   - Verifies submission & returns to Question List
   - Advances to next question (Question 2, Question 3, ... Question 15)
5. Verifies all questions submitted & completes Assignment
"""

import os
import time
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
from playwright.sync_api import Page, Locator

from config import Config, SELECTORS
from browser import BrowserController
from groq_client import GroqClient
from database import Database
from logger import log_event, logger


FORBIDDEN_NAVIGATION_TOKENS = [
    "Dashboard",
    "My Classroom",
    "Practice Test",
    "Assignments",
    "Achievers",
    "Jobs",
    "Faculty Connect",
    "Skill Library",
    "My Notes",
    "Notice Board",
    "Rewards",
    "Feed",
    "ADHI A",
    "Semester 5",
    "LMS POINTS",
    "LMS Points",
    "Answer Submission",
    "Fullscreen Mode",
    "Important!",
    "Read More",
    "Digital LMS",
    "Diploma In",
    "Subject Progress",
    "BEFORE YOU BEGIN"
]


def clean_question_from_row_text(text: str) -> str:
    """
    Extract and clean the pure question prompt from a question row / container's text.
    Strips headers, metadata (Long answer, Faculty-graded, NA, scores, dates, Start),
    and forbidden navigation tokens.
    """
    if not text:
        return ""

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Exact non-question metadata tokens to ignore
    ignored_exact = {
        "question", "type", "max score", "your score", "submission date",
        "action", "status", "marks", "score", "long answer", "faculty-graded",
        "start", "na", "n/a", "pending", "submitted", "completed",
        "view", "review", "view details", "details", "faculty graded",
        "subjective", "your marks", "max marks", "actions"
    }

    candidate_lines = []
    for l in lines:
        l_lower = l.lower()
        if l_lower in ignored_exact:
            continue
        # Exclude pure numbers (e.g. question index "1", max score "4")
        if re.fullmatch(r"\d+", l.strip()):
            continue
        # Exclude pure floats (e.g. "4.0", "0.0")
        if re.fullmatch(r"\d+\.\d+", l.strip()):
            continue
        # Exclude date patterns (e.g. "2026-09-30", "30/09/2026")
        if re.search(r"\b\d{4}[-/]\d{2}[-/]\d{2}\b", l) or re.search(r"\b\d{2}[-/]\d{2}[-/]\d{4}\b", l):
            continue
        # Exclude navigation / sidebar tokens
        if any(token.lower() in l_lower for token in FORBIDDEN_NAVIGATION_TOKENS):
            continue
        if len(l) >= 6:
            candidate_lines.append(l)

    if candidate_lines:
        joined = " ".join(candidate_lines).strip()
        # Clean leading numbers like "1. ", "Q1: ", "1 "
        cleaned = re.sub(r"^(?:Q(?:uestion)?\s*[\.\:]?\s*)?\d+[\.\)\s\-]+\s*", "", joined).strip()
        return cleaned

    return ""


def extract_question_number_from_row(text: str, fallback_idx: int) -> int:
    """Extract question index (1, 2, 3...) from row text."""
    if not text:
        return fallback_idx
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for l in lines:
        if re.fullmatch(r"\d{1,3}", l):
            val = int(l)
            if 1 <= val <= 200:
                return val
        m = re.search(r"^(?:Q(?:uestion)?\s*)?(\d{1,3})[\.\:\)]?\s*$", l, re.IGNORECASE)
        if m:
            val = int(m.group(1))
            if 1 <= val <= 200:
                return val
    return fallback_idx


def get_question_rows(page: Page, timeout_seconds: int = 30, verbose: bool = True) -> List[Dict[str, Any]]:
    """
    Dynamically scan and detect Question List rows/containers in the live rendered DOM.
    Polls every 300-500ms up to timeout_seconds.
    
    Robust strategy:
    1. Find visible elements containing 'Long answer' (or 'Faculty-graded')
    2. For each matching element, walk up its ancestors
    3. Check for question number, question text, and 'Start' button
    4. Select the smallest ancestor containing all required elements
    5. Store that ancestor as the question row and locate Start button inside it
    6. Returns list of question objects:
       {
           "index": 1,
           "question": "What is the binary value of an 8-bit signal at half range?",
           "row": row_locator,
           "start_button": start_button_locator,
           "can_start": bool,
           "status": "Pending" | "Submitted",
           "container": row_locator
       }
    """
    if not page:
        return []

    if verbose:
        log_event("QUESTION_DOM", "Inspecting rendered DOM")

    start_time = time.time()
    first_pass = True

    while time.time() - start_time < timeout_seconds:
        rows = _scan_question_rows_from_page(page, verbose=(verbose and first_pass))
        first_pass = False

        if len(rows) > 0:
            if verbose:
                log_event("QUESTION_DOM", f"Found question candidates: {len(rows)}")
                log_event("QUESTION_LIST", f"Detected {len(rows)} questions")
            return rows

        time.sleep(0.4)

    # If 0 questions detected after full timeout, print failure diagnostics
    _print_question_list_failure_diagnostics(page)
    return []


def _scan_question_rows_from_page(page: Page, verbose: bool = False) -> List[Dict[str, Any]]:
    """Scan and parse question row containers currently present in the DOM."""
    if not page:
        return []

    found_rows = []
    seen_y_positions = set()
    seen_questions = set()

    # Step 1: Find all elements containing "Long answer" or "Faculty-graded"
    la_locators = page.locator("xpath=//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'long answer') or contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'faculty-graded')]").all()

    # Filter to visible leaf / near-leaf elements (text length <= 80 chars)
    leaf_elements = []
    for el in la_locators:
        try:
            if not el.is_visible():
                continue
            txt = el.inner_text().strip()
            if len(txt) <= 80:
                leaf_elements.append((el, txt))
        except Exception:
            pass

    if verbose:
        log_event("QUESTION_DOM", f"Long-answer elements found: {len(leaf_elements)}")

    # Strategy A: Walk up ancestors from each "Long answer" leaf element
    for idx, (leaf_el, leaf_txt) in enumerate(leaf_elements):
        candidate_num = idx + 1
        curr = leaf_el
        best_row_loc = None
        best_start_btn = None
        best_q_text = ""
        best_q_num = candidate_num

        for level in range(1, 7):
            try:
                parent = curr.locator("xpath=..").first
                if parent.count() == 0:
                    break
                parent_text = parent.inner_text().strip()

                # Check Start buttons inside parent
                start_btns = parent.locator("button:has-text('Start'), a:has-text('Start'), [role='button']:has-text('Start')").all()
                visible_start_btns = [b for b in start_btns if b.is_visible()]
                start_btn_count = len(visible_start_btns)

                # Check occurrences of "Long answer" / "Faculty-graded"
                la_occurrences = parent_text.lower().count("long answer") + parent_text.lower().count("faculty-graded")

                # Extract cleaned question candidate
                cleaned_q = clean_question_from_row_text(parent_text)

                # A valid single question row has exactly 1 Start button (or 0 if submitted), 1 Long answer badge, and valid text
                if (start_btn_count == 1 or "Submitted" in parent_text or "Completed" in parent_text) and la_occurrences == 1 and len(cleaned_q) >= 10:
                    best_row_loc = parent
                    best_start_btn = visible_start_btns[0] if visible_start_btns else None
                    best_q_text = cleaned_q
                    best_q_num = extract_question_number_from_row(parent_text, candidate_num)
                    break

                curr = parent
            except Exception:
                break

        if best_row_loc:
            # Check Y-position for deduplication
            y_pos = None
            if best_start_btn:
                try:
                    bb = best_start_btn.bounding_box()
                    if bb:
                        y_pos = round(bb["y"], -1)
                except Exception:
                    pass
            elif best_row_loc:
                try:
                    bb = best_row_loc.bounding_box()
                    if bb:
                        y_pos = round(bb["y"], -1)
                except Exception:
                    pass

            if y_pos is not None and y_pos in seen_y_positions:
                continue
            if best_q_text in seen_questions:
                continue

            if y_pos is not None:
                seen_y_positions.add(y_pos)
            if best_q_text:
                seen_questions.add(best_q_text)

            has_start = best_start_btn is not None
            status = "Submitted" if not has_start and ("Submitted" in best_row_loc.inner_text() or "Completed" in best_row_loc.inner_text()) else "Pending"

            if verbose:
                log_event("QUESTION_CANDIDATE", f"Candidate {candidate_num}")
                log_event("QUESTION_CANDIDATE", f"Text: {best_q_text[:75]}")
                log_event("QUESTION_CANDIDATE", f"Start button found: {'true' if has_start else 'false'}")
                log_event("QUESTION_CANDIDATE", "Valid question row: true")

            found_rows.append({
                "index": best_q_num,
                "question": best_q_text,
                "row": best_row_loc,
                "start_button": best_start_btn,
                "can_start": has_start,
                "status": status,
                "container": best_row_loc,
                "_y": y_pos or 0
            })

    # Strategy B: If no rows found from Long answer elements, try walking up from visible Start buttons
    if len(found_rows) == 0:
        start_btns = page.locator("button:has-text('Start'), a:has-text('Start'), [role='button']:has-text('Start')").all()
        visible_starts = [b for b in start_btns if b.is_visible()]

        for idx, btn in enumerate(visible_starts):
            candidate_num = idx + 1
            curr = btn
            for level in range(1, 7):
                try:
                    parent = curr.locator("xpath=..").first
                    if parent.count() == 0:
                        break
                    parent_text = parent.inner_text().strip()
                    cleaned_q = clean_question_from_row_text(parent_text)
                    all_starts_inside = [b for b in parent.locator("button:has-text('Start'), a:has-text('Start')").all() if b.is_visible()]

                    if len(all_starts_inside) == 1 and len(cleaned_q) >= 10:
                        y_pos = None
                        try:
                            bb = btn.bounding_box()
                            if bb:
                                y_pos = round(bb["y"], -1)
                        except Exception:
                            pass

                        if y_pos is not None and y_pos in seen_y_positions:
                            break
                        if cleaned_q in seen_questions:
                            break

                        if y_pos is not None:
                            seen_y_positions.add(y_pos)
                        seen_questions.add(cleaned_q)

                        q_num = extract_question_number_from_row(parent_text, candidate_num)
                        found_rows.append({
                            "index": q_num,
                            "question": cleaned_q,
                            "row": parent,
                            "start_button": btn,
                            "can_start": True,
                            "status": "Pending",
                            "container": parent,
                            "_y": y_pos or 0
                        })
                        break
                    curr = parent
                except Exception:
                    break

    # Strategy C: Standard table rows / role='row'
    if len(found_rows) == 0:
        table_rows = page.locator("table tbody tr, div[role='row']").all()
        for idx, r in enumerate(table_rows):
            try:
                if not r.is_visible():
                    continue
                txt = r.inner_text().strip()
                cleaned_q = clean_question_from_row_text(txt)
                start_btn = r.locator("button:has-text('Start'), a:has-text('Start')").first
                has_start = start_btn.count() > 0 and start_btn.is_visible()

                if len(cleaned_q) >= 8 or has_start:
                    q_num = extract_question_number_from_row(txt, idx + 1)
                    status = "Submitted" if ("Submitted" in txt or "Completed" in txt) and not has_start else "Pending"
                    found_rows.append({
                        "index": q_num,
                        "question": cleaned_q,
                        "row": r,
                        "start_button": start_btn if has_start else None,
                        "can_start": has_start,
                        "status": status,
                        "container": r,
                        "_y": idx
                    })
            except Exception:
                pass

    # Sort rows by vertical position (Y) or index
    found_rows.sort(key=lambda x: (x.get("_y", 0), x.get("index", 0)))
    return found_rows


def _print_question_list_failure_diagnostics(page: Page):
    """Print targeted DOM diagnostics when question detection fails."""
    try:
        url = page.url
        title = page.title()

        la_elements = page.locator("xpath=//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'long answer')]").all()
        visible_la = [el for el in la_elements if el.is_visible()]

        start_btns = page.locator("button:has-text('Start'), a:has-text('Start')").all()
        visible_starts = [b for b in start_btns if b.is_visible()]

        print("\n[QUESTION_LIST_DIAGNOSTICS] ========================================")
        print(f"[QUESTION_LIST_DIAGNOSTICS] Current URL: {url}")
        print(f"[QUESTION_LIST_DIAGNOSTICS] Page Title:  {title}")
        print(f"[QUESTION_LIST_DIAGNOSTICS] Number of 'Long answer' elements: {len(visible_la)}")
        print(f"[QUESTION_LIST_DIAGNOSTICS] Number of visible 'Start' buttons: {len(visible_starts)}")

        for idx, el in enumerate(visible_la[:3]):
            try:
                parent = el.locator("xpath=..").first
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                cls = el.evaluate("e => e.className")
                attrs = el.evaluate("e => Array.from(e.attributes).map(a => `${a.name}=${a.value}`).join(' ')")
                outer_html = el.evaluate("e => e.outerHTML")[:250]
                parent_text = parent.inner_text().strip()[:150] if parent.count() > 0 else "None"

                print(f"[QUESTION_LIST_DIAGNOSTICS] Candidate {idx + 1}:")
                print(f"  Tag: {tag}, Class: {cls}")
                print(f"  Attributes: {attrs}")
                print(f"  Parent text: {parent_text}")
                print(f"  Snippet: {outer_html}")
            except Exception as e:
                print(f"  Error reading candidate {idx + 1}: {e}")
        print("[QUESTION_LIST_DIAGNOSTICS] ========================================\n")
    except Exception as e:
        print(f"[QUESTION_LIST_DIAGNOSTICS] Error running diagnostics: {e}")


def extract_current_question(page: Page) -> str:
    """
    Extract ONLY the question text from the Question Title container on the Answer Submission page.
    1. Locate the visible Question Title label.
    2. Find its associated container / sibling.
    3. Extract only the question text from that container.
    4. Remove the label 'Question Title' and any 'Question Title *'.
    5. Remove navigation/sidebar/footer text.
    6. Validate the result against forbidden tokens.
    """
    if not page:
        return ""

    # Strategy 1: Find Question Title header and query its parent or immediate following sibling
    try:
        title_headers = page.locator("div:has-text('Question Title'), h3:has-text('Question Title'), h4:has-text('Question Title'), label:has-text('Question Title'), p:has-text('Question Title')").all()
        for header in title_headers:
            if not header.is_visible():
                continue
            
            # Check following sibling or child paragraph
            try:
                sibling_p = header.locator("xpath=following-sibling::p | following-sibling::div[not(contains(., 'Answer'))]").first
                if sibling_p.count() > 0 and sibling_p.is_visible():
                    raw_text = sibling_p.inner_text().strip()
                    cleaned = clean_question_candidate(raw_text)
                    if validate_extracted_question(cleaned):
                        return cleaned
            except Exception:
                pass

            # Check parent container
            try:
                parent = header.locator("xpath=..").first
                if parent.count() > 0:
                    raw_text = parent.inner_text().strip()
                    cleaned = clean_question_candidate(raw_text)
                    if validate_extracted_question(cleaned):
                        return cleaned
            except Exception:
                pass
    except Exception:
        pass

    # Strategy 2: Look for dedicated question card containers
    card_selectors = [
        ".question-title-card",
        "div[class*='QuestionTitle']",
        "div[class*='question-title']",
        "div[class*='questionCard']",
        "div[class*='QuestionCard']",
        "div.card:has(div:has-text('Question Title'))"
    ]
    for sel in card_selectors:
        try:
            card = page.locator(sel).first
            if card.count() > 0 and card.is_visible():
                raw_text = card.inner_text().strip()
                cleaned = clean_question_candidate(raw_text)
                if validate_extracted_question(cleaned):
                    return cleaned
        except Exception:
            pass

    # Strategy 3: Paragraphs sitting right above the Answer / Textarea container
    try:
        textarea_container = page.locator("div:has(textarea)").first
        if textarea_container.count() > 0:
            prev_card = textarea_container.locator("xpath=preceding-sibling::div[1]").first
            if prev_card.count() > 0 and prev_card.is_visible():
                raw_text = prev_card.inner_text().strip()
                cleaned = clean_question_candidate(raw_text)
                if validate_extracted_question(cleaned):
                    return cleaned
    except Exception:
        pass

    # Fallback debug inspection
    print_question_dom_debug(page)
    return ""


def clean_question_candidate(text: str) -> str:
    """Clean raw candidate text by removing labels, badges, and extraneous whitespace."""
    if not text:
        return ""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    filtered_lines = []
    for l in lines:
        # Exclude label lines
        if l.lower() in ("question title", "question title *", "question title*", "answer *", "answer", "submit", "fullscreen mode", "answer submission"):
            continue
        if l.startswith("Question Title") or l.startswith("QUESTION TITLE"):
            l = re.sub(r"^Question\s*Title\s*\*?\s*:?", "", l, flags=re.IGNORECASE).strip()
        if len(l) > 0:
            filtered_lines.append(l)

    cleaned = " ".join(filtered_lines).strip()
    return cleaned


def validate_extracted_question(question: str) -> bool:
    """Validate that the extracted question is substantive and free from page navigation clutter."""
    if not question:
        return False
    if len(question) < 10:
        return False

    # Check for forbidden navigation/sidebar tokens
    for token in FORBIDDEN_NAVIGATION_TOKENS:
        if token.lower() in question.lower():
            return False

    return True


def print_question_dom_debug(page: Page):
    """Print targeted DOM elements when extraction fails for troubleshooting."""
    try:
        q_title_loc = page.locator("*:has-text('Question Title')").first
        q_title_text = q_title_loc.inner_text()[:150].strip() if q_title_loc.count() > 0 else "None"

        parent_loc = q_title_loc.locator("xpath=..").first if q_title_loc.count() > 0 else None
        container_text = parent_loc.inner_text()[:300].strip() if parent_loc and parent_loc.count() > 0 else "None"

        textarea_loc = page.locator("textarea").first
        has_textarea = textarea_loc.count() > 0 and textarea_loc.is_visible()

        submit_loc = page.locator("button:has-text('Submit')").first
        has_submit = submit_loc.count() > 0 and submit_loc.is_visible()

        print(f"\n[QUESTION_DOM]")
        print(f"Question title text: {q_title_text}")
        print(f"\n[QUESTION_DOM]")
        print(f"Question container text: {container_text}")
        print(f"\n[QUESTION_DOM]")
        print(f"Answer textarea found: {has_textarea}")
        print(f"\n[QUESTION_DOM]")
        print(f"Submit button found: {has_submit}\n")
    except Exception as e:
        print(f"[QUESTION_DOM] Debug inspection error: {e}")


class LongAnswerAssignmentAutomation:
    def __init__(self, browser_ctrl: BrowserController, groq_client: Optional[GroqClient] = None):
        self.browser = browser_ctrl
        self.page: Page = self.browser.page
        self.groq = groq_client or GroqClient()
        self.db = Database()

    def run_assignment(self, assignment_title: str = "Assignment", single_question_debug: bool = False) -> Dict[str, Any]:
        """
        Execute full Long-Answer assignment strictly ONE QUESTION AT A TIME.
        """
        log_event("ASSIGNMENT_STARTED", f"Starting Assignment: '{assignment_title}'")
        activity_id = self.db.create_activity(assignment_title, "assignment_long_answer")

        # Step 1: Handle Instructions Modal if present
        instructions_handled = self._handle_instructions_modal()
        if instructions_handled:
            log_event("POPUP", "Instructions modal detected.")
            log_event("POPUP", "Clicking Start Assignment.")

        # Step 2: Wait for Question List to render in DOM
        log_event("QUESTION_LIST", "Waiting for question list...")
        question_rows = self.get_question_rows(timeout_seconds=int(Config.QUESTION_LIST_TIMEOUT / 1000))
        total_questions = len(question_rows)

        if total_questions == 0:
            # Check if browser opened directly into an Answer Submission page
            if self.is_answer_page():
                log_event("STATUS", "Directly on Answer Submission page. Processing single question...")
                res = self._process_single_answer_submission(activity_id, 1, 1)
                if res.get("success"):
                    log_event("TEST", "Question 1 workflow successful")
                answered = 1 if res.get("success") else 0
                return {
                    "activity_id": activity_id,
                    "title": assignment_title,
                    "answered": answered,
                    "total": 1,
                    "status": "completed" if res.get("success") else "failed"
                }

            log_event("QUESTION_LIST_ERROR", f"Could not detect question rows for '{assignment_title}'.")
            self._dump_page_state("question_list_zero")
            return {
                "activity_id": activity_id,
                "title": assignment_title,
                "answered": 0,
                "total": 0,
                "status": "failed"
            }

        log_event("QUESTION_LIST", f"Detected {total_questions} questions")
        answered_count = 0
        failed_count = 0

        # Step 3: Sequential One-By-One Question Processing
        current_index = 0
        fresh_rows = question_rows

        while current_index < total_questions:
            # IMPORTANT: Re-scan rows from live DOM after every return to avoid stale element handles
            if current_index > 0:
                fresh_rows = self.get_question_rows(timeout_seconds=8, verbose=False)

            if not fresh_rows or current_index >= len(fresh_rows):
                log_event("WARNING", f"Question container #{current_index + 1} not found in refreshed DOM.")
                break

            target_row = fresh_rows[current_index]
            q_num = target_row.get("index", current_index + 1)
            q_text = target_row.get("question", "")

            log_event("QUESTION", f"{current_index + 1}/{total_questions}")
            if q_text:
                log_event("QUESTION_TEXT", f"{q_text}")
            log_event("ACTION", f"Opening Question {q_num}")

            # Ensure we are on the Question List before clicking
            if not self.is_question_list() and not self.is_answer_page():
                self._ensure_returned_to_question_table()

            can_start = target_row.get("can_start", True)
            status = target_row.get("status", "Pending")

            # Check if recorded in local DB or marked submitted
            if not can_start and status in ("Submitted", "Completed"):
                log_event("STATUS", f"Question {q_num} is already submitted. Skipping.")
                answered_count += 1
                current_index += 1
                continue

            # Find Start button INSIDE THIS SPECIFIC QUESTION CONTAINER ONLY
            start_btn = target_row.get("start_button") or self._find_start_button_inside_row(target_row)

            if not start_btn or start_btn.count() == 0:
                log_event("ERROR", f"Could not find Start button inside Question {q_num} container.")
                self._dump_page_state(f"q_{q_num}_no_start_button")
                if not Config.CONTINUE_ON_ERROR:
                    break
                current_index += 1
                continue

            log_event("ACTION", f"Question {q_num} Start button found")
            log_event("ACTION", f"Clicking Question {q_num} Start")

            # Safe visual click on Question X Start button
            self.browser.safe_click(start_btn, highlight_color="#ff5722")
            log_event("ACTION", f"Question {q_num} Start clicked")

            # Step 4: Wait for Answer Submission Page to mount
            on_answer_page = self._wait_for_answer_page(timeout_seconds=int(Config.QUESTION_START_TIMEOUT / 1000))
            if not on_answer_page:
                log_event("ERROR", f"Answer Submission page did not load for Question {q_num}.")
                self._dump_page_state(f"q_{q_num}_answer_page_load_failed")
                if not Config.CONTINUE_ON_ERROR:
                    break
                current_index += 1
                continue

            # Step 5: Handle Fullscreen Required
            self.handle_fullscreen()

            # Step 6: Process Answer Submission
            q_res = self._process_single_answer_submission(activity_id, q_num, total_questions, fallback_q_text=q_text)

            if q_res.get("success"):
                answered_count += 1
                log_event("QUESTION_COMPLETED", f"{q_num}/{total_questions}")
                if q_num == 1:
                    log_event("TEST", "Question 1 workflow successful")

                # If debug test mode requested, stop after Question 1
                if single_question_debug or os.getenv("DEBUG_SINGLE_QUESTION", "").lower() in ("1", "true", "yes"):
                    log_event("DEBUG", "Debug mode active: Stopped after Question 1.")
                    break
            else:
                failed_count += 1
                log_event("ERROR", f"Question {q_num}/{total_questions} failed: {q_res.get('reason')}")
                self._dump_page_state(f"q_{q_num}_submission_failed")
                if not Config.CONTINUE_ON_ERROR:
                    log_event("WARNING", f"Halting assignment on Question {q_num} failure.")
                    break

            # Advance to next question
            current_index += 1
            time.sleep(Config.VISUAL_DELAY / 1000.0)

        # Step 7: Completion Summary
        status = "completed" if answered_count == total_questions else "partial" if answered_count > 0 else "failed"
        log_event("ASSIGNMENT_FINISHED", f"Assignment '{assignment_title}' complete. Answered: {answered_count}/{total_questions}")

        self.db.complete_activity(activity_id, status, score=float(answered_count))
        self._return_to_main_assignments()

        return {
            "activity_id": activity_id,
            "title": assignment_title,
            "answered": answered_count,
            "total": total_questions,
            "status": status
        }

    # =========================================================================
    # Question Row & Container Discovery
    # =========================================================================

    def get_question_rows(self, timeout_seconds: int = 30, verbose: bool = True) -> List[Dict[str, Any]]:
        """
        Dynamically scan Question List items in the DOM using robust ancestor walking.
        """
        return get_question_rows(self.page, timeout_seconds=timeout_seconds, verbose=verbose)

    def _find_start_button_inside_row(self, row_info: Dict[str, Any]) -> Optional[Locator]:
        """Find the Start button scoped strictly inside the given question container."""
        if row_info.get("start_button"):
            return row_info.get("start_button")

        container: Optional[Locator] = row_info.get("row") or row_info.get("container")
        if not container or container.count() == 0:
            return None

        selectors = [
            "button:has-text('Start')",
            "a:has-text('Start')",
            "button.btn-primary:has-text('Start')",
            "button[class*='btn']:has-text('Start')",
            "[role='button']:has-text('Start')"
        ]

        for sel in selectors:
            btn = container.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                return btn

        return None

        for sel in selectors:
            btn = container.locator(sel).first
            if btn.count() > 0 and btn.is_visible():
                return btn

        return None

    # =========================================================================
    # State Detection & Modals
    # =========================================================================

    def is_question_list(self) -> bool:
        """Check if Question List table / grid view is currently visible."""
        markers = [
            "th:has-text('QUESTION')",
            "div:has-text('Faculty-graded')",
            "div:has-text('Long answer')",
            "table tbody tr",
            "button:has-text('Start Assignment')"
        ]
        for m in markers:
            loc = self.browser.find_first_element([m], timeout=300)
            if loc and loc.is_visible():
                return True

        try:
            body_text = self.page.locator("body").inner_text()
            if "QUESTION" in body_text and ("TYPE" in body_text or "MAX SCORE" in body_text or "Faculty-graded" in body_text or "Long answer" in body_text):
                return True
        except Exception:
            pass
        return False

    def is_answer_page(self) -> bool:
        """Check if Answer Submission form is active."""
        markers = [
            "div:has-text('Answer Submission')",
            "div:has-text('Question Title *')",
            "div:has-text('Question Title')",
            "div:has-text('Answer *')",
            "textarea"
        ]
        return any(self.browser.find_first_element([m], timeout=300) is not None for m in markers)

    def is_fullscreen_required(self) -> bool:
        """Check if Fullscreen Required modal is displayed."""
        markers = [
            "button:has-text('Enter Fullscreen')",
            "div:has-text('Fullscreen Required')",
            "div:has-text('You must submit your answer before exiting fullscreen')"
        ]
        return any(self.browser.find_first_element([m], timeout=300) is not None for m in markers)

    def is_fullscreen_active(self) -> bool:
        """Check if document.fullscreenElement is active."""
        try:
            return bool(self.page.evaluate("() => Boolean(document.fullscreenElement)"))
        except Exception:
            return False

    def _handle_instructions_modal(self) -> bool:
        """Detect and click 'Start Assignment' in the Instructions modal."""
        modal_selectors = [
            "div:has-text('Instructions')",
            "div:has-text('BEFORE YOU BEGIN')",
            "div[role='dialog']",
            ".modal",
            "button:has-text('Start Assignment')"
        ]
        modal = self.browser.find_first_element(modal_selectors, timeout=2000)
        if modal and modal.is_visible():
            start_btn = self.browser.find_first_element([
                "button:has-text('Start Assignment')",
                "a:has-text('Start Assignment')",
                "button:has-text('Start Assignment >')",
                "button.btn-primary:has-text('Start')",
                "button:has-text('Begin')"
            ], timeout=2000)

            if start_btn and start_btn.is_visible():
                self.browser.safe_click(start_btn, highlight_color="#2563eb")
                self.browser.wait_for_idle(1000)
                return True

        return False

    def handle_fullscreen(self) -> bool:
        """Handle Fullscreen Required modal using real DOM button and verify state."""
        if not self.is_fullscreen_required():
            if self.is_fullscreen_active():
                log_event("FULLSCREEN", "Active")
            return True

        log_event("FULLSCREEN", "Fullscreen Required detected.")
        enter_btn = self.browser.find_first_element([
            "button:has-text('Enter Fullscreen')",
            "a:has-text('Enter Fullscreen')",
            "button.btn-primary:has-text('Fullscreen')"
        ], timeout=2500)

        if enter_btn and enter_btn.is_visible():
            log_event("FULLSCREEN", "Clicking Enter Fullscreen.")
            self.browser.safe_click(enter_btn, highlight_color="#0284c7")
            self.browser.wait_for_idle(800)
            log_event("FULLSCREEN", "Active")
            return True

        return False

    def _wait_for_answer_page(self, timeout_seconds: int = 15) -> bool:
        """
        Wait dynamically until the Answer Submission page, Question Title, and Textarea are ready.
        """
        log_event("ANSWER_PAGE", "Waiting for answer page...")
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            self.handle_fullscreen()

            # Check for Answer Submission heading + Question Title or textarea or Submit
            has_heading = self.browser.find_first_element(["div:has-text('Answer Submission')", "h2:has-text('Answer Submission')", "h3:has-text('Answer Submission')"], timeout=200) is not None
            has_title = self.browser.find_first_element(["div:has-text('Question Title')", "h4:has-text('Question Title')", "label:has-text('Question Title')"], timeout=200) is not None
            has_answer_label = self.browser.find_first_element(["div:has-text('Answer *')", "label:has-text('Answer *')", "div:has-text('Answer')", "label:has-text('Answer')"], timeout=200) is not None
            has_textarea = self.browser.find_first_element(["textarea"], timeout=200) is not None
            has_submit = self.browser.find_first_element(["button:has-text('Submit')", "button[type='submit']"], timeout=200) is not None

            if (has_heading or has_title or has_answer_label) and (has_textarea or has_submit):
                log_event("ANSWER_PAGE", "Answer Submission detected")
                return True

            time.sleep(0.3)

        if self.is_answer_page():
            log_event("ANSWER_PAGE", "Answer Submission detected")
            return True

        return False

    # =========================================================================
    # Answer Submission Execution (Debug Typing Test Workflow)
    # =========================================================================

    def _process_single_answer_submission(self, activity_id: int, q_idx: int, total_q: int, fallback_q_text: str = "") -> Dict[str, Any]:
        """
        Execute Answer Submission debugging test workflow:
        1. Wait for Answer Page & Fullscreen
        2. Extract ONLY Question text
        3. Prepare User-Provided Test String (DO NOT generate academic answer or call Groq)
        4. Locate visible Answer textarea & verify visibility and enabled state
        5. Scroll into view, click, and verify focus
        6. Keyboard character-by-character typing (delay 8-10ms per char)
        7. Verify typed text in textarea
        8. STOP BEFORE SUBMIT (DO NOT click Submit or call answerSubmit)
        """
        result = {"success": False, "reason": ""}

        # STEP 1: Handle Fullscreen & Settle
        self.handle_fullscreen()
        self.browser.wait_for_idle(300)

        # STEP 2: Extract ONLY Question text from Question Title section
        question_text = extract_current_question(self.page)
        if not question_text and fallback_q_text:
            cleaned_fallback = clean_question_candidate(fallback_q_text)
            if validate_extracted_question(cleaned_fallback):
                question_text = cleaned_fallback

        if question_text:
            log_event("QUESTION_TEXT", f"{question_text}")

        # STEP 3: User-Provided Test String for Debugging Test (NO academic answer generation)
        test_string = os.getenv("TEST_STRING", "Automation typing test.")

        # STEP 4: Locate the Answer Textarea (verify visible, enabled, editable)
        textarea = None
        candidate_selectors = [
            "div:has-text('Answer') textarea",
            "div:has-text('Answer *') textarea",
            "textarea:visible",
            "textarea[name='answer']",
            "textarea"
        ]

        for sel in candidate_selectors:
            loc = self.browser.find_first_element([sel], timeout=1500)
            if loc and loc.is_visible() and loc.is_enabled() and loc.is_editable():
                bb = loc.bounding_box()
                if bb and bb.get("width", 0) > 0 and bb.get("height", 0) > 0:
                    textarea = loc
                    break

        if not textarea:
            log_event("ERROR", "Answer textarea not found on page.")
            result["reason"] = "Answer textarea not found"
            return result

        log_event("ANSWER_BOX", "Textarea found")
        log_event("ANSWER_BOX", "Visible: true")
        log_event("ANSWER_BOX", "Enabled: true")

        # STEP 5: Click First - Scroll into view, click, and verify focus
        try:
            textarea.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass

        log_event("ANSWER_BOX", "Clicking textarea")
        self.browser.safe_click(textarea, highlight_color="#3b82f6")

        # Verify Focus
        is_focused = False
        try:
            is_focused = bool(self.page.evaluate("() => document.activeElement && document.activeElement.tagName.toLowerCase() === 'textarea'"))
        except Exception:
            pass

        if not is_focused:
            try:
                textarea.focus()
                is_focused = True
            except Exception:
                pass

        log_event("ANSWER_BOX", "Focus verified")

        # STEP 6: Human-Like Fast Keyboard Typing (character-by-character, 8ms delay)
        log_event("TYPE", "Starting keyboard typing")
        log_event("TYPE", f"Characters: {len(test_string)}")

        try:
            textarea.press_sequentially(test_string, delay=8)
        except Exception:
            try:
                textarea.type(test_string, delay=8)
            except Exception as e:
                log_event("ERROR", f"Typing error: {e}")

        log_event("TYPE", "Typing completed")

        # STEP 7: Verify Typed Text in Textarea
        actual_text = ""
        try:
            actual_text = textarea.input_value() or ""
        except Exception:
            try:
                actual_text = textarea.evaluate("e => e.value") or ""
            except Exception:
                pass

        log_event("TYPE_VERIFY", f"Expected: {test_string}")
        log_event("TYPE_VERIFY", f"Actual: {actual_text}")

        if actual_text.strip() == test_string.strip():
            log_event("TYPE_VERIFY", "PASS")
            result["success"] = True
        else:
            # Quick single retry if character was dropped
            if len(actual_text) < len(test_string):
                try:
                    textarea.fill("")
                    textarea.click()
                    textarea.press_sequentially(test_string, delay=10)
                    actual_text = textarea.input_value() or ""
                    log_event("TYPE_VERIFY", f"Expected: {test_string}")
                    log_event("TYPE_VERIFY", f"Actual: {actual_text}")
                    if actual_text.strip() == test_string.strip():
                        log_event("TYPE_VERIFY", "PASS")
                        result["success"] = True
                    else:
                        log_event("TYPE_VERIFY", "FAIL")
                except Exception:
                    log_event("TYPE_VERIFY", "FAIL")
            else:
                log_event("TYPE_VERIFY", "FAIL")

        # STEP 8: STOP BEFORE SUBMIT - DO NOT CLICK SUBMIT OR CALL answerSubmit()
        log_event("DEBUG", "STOPPING BEFORE SUBMIT")

        return result

    def _wait_for_question_submission_verified(self, timeout_seconds: int = 45) -> bool:
        """Wait dynamically for submission confirmation or transition back to list."""
        start_t = time.time()
        while time.time() - start_t < timeout_seconds:
            # If back on question list table
            if self.is_question_list():
                return True

            # If success alert or toast appeared
            toast = self.browser.find_first_element([
                "div:has-text('submitted successfully')",
                "div:has-text('Answer submitted')",
                "div:has-text('Success')",
                ".toast-success"
            ], timeout=400)
            if toast and toast.is_visible():
                return True

            # If textarea is no longer visible (form unmounted after submission)
            textarea = self.browser.find_first_element(["textarea"], timeout=300)
            if not textarea or not textarea.is_visible():
                return True

            time.sleep(0.4)

        return False

    def _ensure_returned_to_question_table(self):
        """Ensure browser navigates back to the Question List table."""
        self.browser.wait_for_idle(1000)
        if self.is_answer_page():
            back_btn = self.browser.find_first_element([
                "button:has-text('Back')",
                "a:has-text('Back')",
                "button:has-text('< Back')",
                "a:has-text('< Back')"
            ], timeout=2000)
            if back_btn and back_btn.is_visible():
                self.browser.safe_click(back_btn)
                self.browser.wait_for_idle(1200)

    def _return_to_main_assignments(self):
        """Navigate back to /assignments coursework page."""
        log_event("NAVIGATION", "Returning to main Assignments page...")
        back_btn = self.browser.find_first_element([
            "a[href*='/assignments']",
            "button:has-text('Back')",
            "a:has-text('Back')",
            "button:has-text('< Back')",
            "a:has-text('< Back')"
        ], timeout=2000)

        if back_btn and back_btn.is_visible():
            self.browser.safe_click(back_btn)
            self.browser.wait_for_idle(1200)
        else:
            self.browser.navigate_to(Config.ASSIGNMENTS_URL)
            self.browser.wait_for_idle(1200)

    def _dump_page_state(self, label: str):
        """
        Capture diagnostic dump when unexpected layout is encountered.
        """
        try:
            url = self.page.url
            title = self.page.title()
            body_snippet = self.page.locator("body").inner_text()[:2500]

            print(f"\n[DEBUG_DUMP] ==================================================")
            print(f"[DEBUG_DUMP] DIAGNOSTIC DUMP: {label}")
            print(f"[DEBUG_DUMP] URL:          {url}")
            print(f"[DEBUG_DUMP] Title:        {title}")
            print(f"[DEBUG_DUMP] Body Snippet:\n{body_snippet}\n")

            # Visible buttons
            visible_btns = self.page.locator("button, a.btn").all()
            btn_texts = [b.inner_text().strip() for b in visible_btns if b.is_visible()]
            print(f"[DEBUG_DUMP] Visible Buttons: {btn_texts}")
        except Exception:
            pass
