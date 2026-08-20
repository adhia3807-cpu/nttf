"""
Digital NTTF AI Automation - Recovery & State Checkpointing
Handles crash/interruption recovery, session state loading, and seamless task resumption.
"""

from typing import Optional, Dict, Any
from database import Database
from logger import log_event, logger

class RecoveryManager:
    def __init__(self):
        self.db = Database()

    def check_for_interrupted_activity(self) -> Optional[Dict[str, Any]]:
        """Check if an incomplete session exists in the database."""
        session = self.db.get_latest_interrupted_session()
        if session:
            log_event("RECOVERY", f"Discovered interrupted session: Activity #{session['activity_id']} ({session['activity_name']}) at Q{session['last_question_number']}")
        return session

    def resume_prompt(self) -> Optional[Dict[str, Any]]:
        """Prompt user on CLI to resume if an unfinished activity was detected."""
        session = self.check_for_interrupted_activity()
        if not session:
            return None

        print("\n" + "="*60)
        print("          UNFINISHED ACTIVITY DETECTED")
        print("="*60)
        print(f" Activity:    {session['activity_name']}")
        print(f" Type:        {session['activity_type']}")
        print(f" Last Q#:     {session['last_question_number']}")
        print(f" Updated:     {session['updated_at']}")
        print("="*60)
        
        choice = input("Do you want to resume this activity? (Y/n): ").strip().lower()
        if choice in ("", "y", "yes"):
            log_event("RECOVERY", "User opted to resume previous session.")
            return session
        else:
            log_event("RECOVERY", "User skipped session resumption.")
            return None
