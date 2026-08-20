"""
Digital NTTF AI Automation - Database Module
Provides local persistent storage using SQLite.
Stores activity history, questions, answers, results, execution logs, and Gemini response caches.
NEVER stores passwords, tokens, or API keys.
"""

import sqlite3
import json
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from config import Config

class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initialize SQLite tables."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Activities table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                type TEXT NOT NULL,          -- 'assignment', 'practice_test', 'skill_quiz'
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,        -- 'in_progress', 'completed', 'interrupted', 'failed'
                total_questions INTEGER DEFAULT 0,
                answered_count INTEGER DEFAULT 0,
                score REAL,
                max_score REAL,
                percentage REAL,
                metadata TEXT
            )
            """)

            # Questions table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER,
                question_number INTEGER,
                question_id TEXT,
                question_text TEXT NOT NULL,
                question_type TEXT NOT NULL, -- 'MCQ', 'TrueFalse', 'Subjective', 'Checkbox', 'Dropdown'
                options_json TEXT,
                ai_answer TEXT,
                selected_answer TEXT,
                confidence REAL,
                status TEXT NOT NULL,        -- 'answered', 'unanswered', 'review_required', 'failed'
                timestamp TEXT NOT NULL,
                FOREIGN KEY (activity_id) REFERENCES activities (id)
            )
            """)

            # Question response cache (hash(question + options) -> AI answer)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS question_cache (
                question_hash TEXT PRIMARY KEY,
                question_text TEXT NOT NULL,
                options_json TEXT,
                ai_response_json TEXT NOT NULL,
                model_used TEXT NOT NULL,
                confidence REAL,
                created_at TEXT NOT NULL
            )
            """)

            # Errors table
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER,
                question_number INTEGER,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                screenshot_path TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (activity_id) REFERENCES activities (id)
            )
            """)

            # Resume sessions checkpoint
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER,
                activity_name TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                last_question_number INTEGER DEFAULT 1,
                last_question_id TEXT,
                state_data TEXT,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL,        -- 'active', 'completed', 'interrupted'
                FOREIGN KEY (activity_id) REFERENCES activities (id)
            )
            """)

            conn.commit()

    @staticmethod
    def generate_question_hash(question_text: str, options: List[Any]) -> str:
        """Generate SHA256 hash for caching."""
        normalized_q = " ".join(question_text.lower().split())
        normalized_opts = "||".join(sorted([" ".join(str(o).lower().split()) for o in options]))
        key = f"{normalized_q}@@{normalized_opts}"
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def get_cached_answer(self, question_text: str, options: List[Any]) -> Optional[Dict[str, Any]]:
        """Retrieve cached Gemini response if available."""
        q_hash = self.generate_question_hash(question_text, options)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT ai_response_json, confidence FROM question_cache WHERE question_hash = ?", (q_hash,))
            row = cursor.fetchone()
            if row:
                try:
                    data = json.loads(row["ai_response_json"])
                    data["from_cache"] = True
                    return data
                except Exception:
                    return None
        return None

    def save_cached_answer(self, question_text: str, options: List[Any], ai_response: Dict[str, Any], model_used: str):
        """Save AI answer to cache."""
        q_hash = self.generate_question_hash(question_text, options)
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT OR REPLACE INTO question_cache 
            (question_hash, question_text, options_json, ai_response_json, model_used, confidence, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                q_hash,
                question_text,
                json.dumps(options),
                json.dumps(ai_response),
                model_used,
                ai_response.get("confidence", 0.0),
                datetime.utcnow().isoformat()
            ))
            conn.commit()

    def create_activity(self, name: str, activity_type: str, total_questions: int = 0) -> int:
        """Create new activity record and return its ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
            INSERT INTO activities (name, type, started_at, status, total_questions)
            VALUES (?, ?, ?, 'in_progress', ?)
            """, (name, activity_type, now, total_questions))
            conn.commit()
            return cursor.lastrowid

    def update_activity_progress(self, activity_id: int, answered_count: int, total_questions: Optional[int] = None):
        """Update activity progress."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if total_questions is not None:
                cursor.execute("""
                UPDATE activities SET answered_count = ?, total_questions = ? WHERE id = ?
                """, (answered_count, total_questions, activity_id))
            else:
                cursor.execute("""
                UPDATE activities SET answered_count = ? WHERE id = ?
                """, (answered_count, activity_id))
            conn.commit()

    def complete_activity(self, activity_id: int, score: Optional[float] = None, 
                          max_score: Optional[float] = None, percentage: Optional[float] = None, 
                          status: str = "completed"):
        """Mark activity as completed with optional results."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
            UPDATE activities 
            SET completed_at = ?, status = ?, score = ?, max_score = ?, percentage = ?
            WHERE id = ?
            """, (now, status, score, max_score, percentage, activity_id))
            conn.commit()

    def record_question(self, activity_id: int, question_number: int, question_text: str,
                        question_type: str, options: List[Any], ai_answer: Optional[str],
                        selected_answer: Optional[str], confidence: float, status: str,
                        question_id: Optional[str] = None) -> int:
        """Record question and answer details."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
            INSERT INTO questions 
            (activity_id, question_number, question_id, question_text, question_type, 
             options_json, ai_answer, selected_answer, confidence, status, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                activity_id, question_number, question_id, question_text, question_type,
                json.dumps(options), ai_answer, selected_answer, confidence, status, now
            ))
            conn.commit()
            return cursor.lastrowid

    def record_error(self, activity_id: Optional[int], question_number: Optional[int],
                     error_type: str, error_message: str, screenshot_path: Optional[str] = None):
        """Record error occurrence."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
            INSERT INTO errors (activity_id, question_number, error_type, error_message, screenshot_path, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (activity_id, question_number, error_type, error_message, screenshot_path, now))
            conn.commit()

    def save_session_checkpoint(self, activity_id: int, activity_name: str, activity_type: str,
                                question_number: int, question_id: Optional[str] = None, 
                                state_data: Optional[Dict[str, Any]] = None):
        """Save recovery checkpoint."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.utcnow().isoformat()
            cursor.execute("""
            INSERT OR REPLACE INTO sessions 
            (activity_id, activity_name, activity_type, last_question_number, last_question_id, state_data, updated_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'active')
            """, (
                activity_id, activity_name, activity_type, question_number,
                question_id, json.dumps(state_data or {}), now
            ))
            conn.commit()

    def get_latest_interrupted_session(self) -> Optional[Dict[str, Any]]:
        """Retrieve most recent unfinished session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            SELECT * FROM sessions 
            WHERE status = 'active'
            ORDER BY id DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def mark_session_completed(self, activity_id: int):
        """Mark session as completed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE sessions SET status = 'completed' WHERE activity_id = ?", (activity_id,))
            conn.commit()

    def get_all_activities(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch list of recorded activities."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM activities ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cursor.fetchall()]

    def get_activity_questions(self, activity_id: int) -> List[Dict[str, Any]]:
        """Fetch all recorded questions for an activity."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM questions WHERE activity_id = ? ORDER BY question_number ASC", (activity_id,))
            return [dict(row) for row in cursor.fetchall()]
