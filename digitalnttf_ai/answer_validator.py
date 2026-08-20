"""
Digital NTTF AI Automation - Answer Validator
Performs strict validation on Groq model output against actual webpage options.
Prevents arbitrary or misaligned clicks, ensures exact or normalized text matches,
and flags low confidence responses.
"""

import re
from typing import Dict, Any, List, Tuple, Optional
from config import Config
from logger import log_event, logger

class AnswerValidator:
    @staticmethod
    def normalize_text(text: str) -> str:
        """Strip punctuation, prefixes (e.g., 'A.', 'Option 1:'), and normalize spacing."""
        if not text:
            return ""
        # Remove common option prefixes like "a)", "1.", "A - ", etc.
        cleaned = re.sub(r'^(?:[a-zA-Z0-9][\.\)\-\:\s]+|option\s+[0-9a-zA-Z][\:\.\-\s]*)', '', text.strip(), flags=re.IGNORECASE)
        # Normalize whitespace
        cleaned = " ".join(cleaned.lower().split())
        return cleaned

    @classmethod
    def validate_mcq_answer(
        cls, 
        ai_response: Dict[str, Any], 
        actual_options: List[str]
    ) -> Tuple[bool, int, str, float, str]:
        """
        Validate Groq answer against actual webpage options.
        Returns:
            (is_valid, resolved_index_0_based, resolved_option_text, confidence, reason)
        """
        if not actual_options:
            return False, 0, "", 0.0, "No actual options available on page"

        confidence = float(ai_response.get("confidence", 0.0))
        suggested_index_1_based = ai_response.get("answer_index", 1)
        suggested_text = ai_response.get("answer_text", "")

        # 1. Check direct 1-based index validity
        valid_index = False
        if isinstance(suggested_index_1_based, int):
            if 1 <= suggested_index_1_based <= len(actual_options):
                valid_index = True

        # 2. Check text match against target index option
        norm_suggested = cls.normalize_text(suggested_text)
        
        # Test direct index option match
        if valid_index:
            direct_opt = actual_options[suggested_index_1_based - 1]
            norm_direct = cls.normalize_text(direct_opt)
            if norm_suggested == norm_direct or norm_suggested in norm_direct or norm_direct in norm_suggested:
                # Perfect alignment
                status_reason = "Exact index & text match"
                if confidence < Config.AI_CONFIDENCE_THRESHOLD:
                    status_reason += f" (LOW CONFIDENCE: {confidence:.2f})"
                return True, suggested_index_1_based - 1, direct_opt, confidence, status_reason

        # 3. Fallback: Search all options for best text match
        best_match_idx = -1
        best_match_score = 0.0

        for idx, opt in enumerate(actual_options):
            norm_opt = cls.normalize_text(opt)
            if not norm_opt:
                continue

            # Exact normalized match
            if norm_suggested == norm_opt:
                best_match_idx = idx
                best_match_score = 1.0
                break
            
            # Substring match
            if norm_suggested in norm_opt or norm_opt in norm_suggested:
                similarity = len(norm_suggested) / max(len(norm_opt), 1)
                if similarity > best_match_score:
                    best_match_score = similarity
                    best_match_idx = idx

        if best_match_idx != -1 and best_match_score > 0.5:
            resolved_text = actual_options[best_match_idx]
            log_event("ANSWER_SELECTED", 
                      f"Validated by text fallback: matched Option {best_match_idx+1} ('{resolved_text}')")
            return True, best_match_idx, resolved_text, confidence, f"Text match (score: {best_match_score:.2f})"

        # 4. If direct index was valid but text was slightly differing, allow if confidence >= threshold
        if valid_index and confidence >= 0.70:
            resolved_text = actual_options[suggested_index_1_based - 1]
            log_event("ANSWER_SELECTED", 
                      f"Validated by index trust: Option {suggested_index_1_based} ('{resolved_text}')")
            return True, suggested_index_1_based - 1, resolved_text, confidence, "Index matched with high confidence"

        # 5. Invalid match - mark as unresolved
        return False, -1, "", confidence, f"Mismatch: AI suggested '{suggested_text}' (index {suggested_index_1_based}) but options did not match"

    @classmethod
    def validate_subjective_answer(cls, ai_response: Dict[str, Any]) -> Tuple[bool, str, float, str]:
        """Validate subjective text answer."""
        text = ai_response.get("answer_text", "").strip()
        confidence = float(ai_response.get("confidence", 0.0))
        
        if not text or len(text) < 5:
            return False, "", confidence, "Subjective answer text too short or empty"

        if ai_response.get("error"):
            return False, text, 0.0, "AI returned error flag"

        return True, text, confidence, "Valid subjective response"
