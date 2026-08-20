"""
Digital NTTF AI Automation - Groq AI Client
Integrates Groq API with dynamic runtime model discovery, automated fallback selection,
error handling (401/403/404/429/5xx), options matching, confidence scoring, and SQLite response caching.
"""

import os
import json
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Tuple

from config import Config
from logger import log_event, logger
from database import Database

try:
    from groq import Groq, APIError, AuthenticationError, NotFoundError, PermissionDeniedError, RateLimitError
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("Groq Python SDK not installed. Please run: pip install groq")


PRIORITIZED_TEXT_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "llama3-8b-8192",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b"
]


def get_available_groq_models(api_key: Optional[str] = None) -> List[str]:
    """
    Query Groq's models API (https://api.groq.com/openai/v1/models) using the provided API key.
    Filters and returns list of actual available model IDs suitable for text/chat generation.
    """
    key = api_key or Config.GROQ_API_KEY
    log_event("AI_INIT", "Checking available Groq models")

    if not key:
        log_event("AI_ERROR", "Groq API key is not configured. Set GROQ_API_KEY environment variable.")
        return []

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/models",
        headers={
            "Authorization": f"Bearer {key}",
            "User-Agent": "DigitalNTTF-Automation/1.0"
        },
        method="GET"
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                models_data = data.get("data", [])

                # Filter for text/chat models, excluding audio, embeddings, guardrails, tts, vision-only
                suitable_models = []
                for item in models_data:
                    m_id = item.get("id", "")
                    if not m_id:
                        continue
                    m_id_lower = m_id.lower()
                    if any(unsupported in m_id_lower for unsupported in ["whisper", "embedding", "guard", "audio", "tts"]):
                        continue
                    # Check active state if present in metadata
                    if item.get("active", True) is False:
                        continue
                    suitable_models.append(m_id)

                return suitable_models

    except urllib.error.HTTPError as e:
        if e.code == 401:
            log_event("AI_ERROR", "Invalid Groq API key.")
        elif e.code == 403:
            log_event("AI_ERROR", "Access denied for this Groq API key.")
        elif e.code == 429:
            log_event("AI_ERROR", "Groq rate limit reached during model discovery.")
        else:
            log_event("AI_ERROR", f"Groq models API returned HTTP {e.code}: {e.reason}")
    except Exception as e:
        log_event("AI_ERROR", f"Could not fetch available Groq models: {e}")

    return []


def choose_best_available_text_model(available_models: List[str]) -> Optional[str]:
    """
    Choose the best suitable text model from the available models list
    based on priority order.
    """
    if not available_models:
        return None

    for candidate in PRIORITIZED_TEXT_MODELS:
        if candidate in available_models:
            return candidate

    # Fallback to the first available text model if none of the priority list match
    return available_models[0]


def select_groq_model(available_models: List[str], preferred_model: Optional[str] = None) -> Optional[str]:
    """
    Select the active Groq model according to user preference and actual availability.
    Logs preferred and selected models cleanly without exposing secrets.
    """
    configured_model = preferred_model or Config.GROQ_MODEL

    log_event("AI_INIT", f"Preferred model: {configured_model}")

    if not available_models:
        log_event("AI_ERROR", "No usable Groq text model available")
        return None

    if configured_model and configured_model in available_models:
        selected_model = configured_model
    else:
        selected_model = choose_best_available_text_model(available_models)

    if selected_model:
        log_event("AI_INIT", f"Selected model: {selected_model}")
    else:
        log_event("AI_ERROR", "No usable Groq text model available")

    return selected_model


def create_groq_client(api_key: Optional[str] = None, preferred_model: Optional[str] = None) -> 'GroqClient':
    """
    Central factory function to instantiate and initialize the Groq client
    with verified dynamic model discovery.
    """
    return GroqClient(api_key=api_key, preferred_model=preferred_model)


class GroqClient:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None, preferred_model: Optional[str] = None):
        self.api_key = api_key or Config.GROQ_API_KEY
        self.preferred_model = model or preferred_model or Config.GROQ_MODEL
        self.db = Database()
        self.client = None
        self.available_models: List[str] = []
        self.model: Optional[str] = None
        self.failed_models: List[str] = []

        if not self.api_key:
            log_event("AI_ERROR", "Groq API key is not configured. Set GROQ_API_KEY environment variable.")
            return

        # 1. Discover available models from Groq API
        self.available_models = get_available_groq_models(self.api_key)

        # 2. Select best available model
        self.model = select_groq_model(self.available_models, self.preferred_model)

        # 3. Initialize SDK client
        if self.model and GROQ_AVAILABLE:
            try:
                self.client = Groq(api_key=self.api_key)
                log_event("AI_READY", f"Initialized Groq Client with verified model: {self.model}")
            except Exception as e:
                log_event("AI_ERROR", f"Failed to initialize Groq Client: {e}")

    def switch_to_next_fallback_model(self, failed_model: str, reason: str = "") -> Optional[str]:
        """
        Switch to next available model when a model fails with 404 (model_not_found) or 403 (forbidden).
        Guarantees never retrying the same failed model.
        """
        if failed_model not in self.failed_models:
            self.failed_models.append(failed_model)

        if failed_model in self.available_models:
            self.available_models.remove(failed_model)

        next_model = choose_best_available_text_model(self.available_models)
        if next_model:
            self.model = next_model
            log_event("AI_INFO", f"Switched model from '{failed_model}' to '{self.model}' ({reason})")
            return self.model
        else:
            log_event("AI_ERROR", "No more fallback Groq models available.")
            self.model = None
            return None

    def get_mcq_answer(self, question: str, options: List[str], instructions: str = "") -> Dict[str, Any]:
        """
        Solve a Multiple Choice / True-False / Checkbox question using Groq.
        """
        # 1. Check local SQLite Cache first
        cached = self.db.get_cached_answer(question, options)
        if cached:
            log_event("GROQ_RESPONSE", f"Loaded answer from cache (confidence: {cached.get('confidence', 'N/A')})")
            return cached

        # 2. Rate limit delay
        if Config.GROQ_REQUEST_DELAY > 0:
            time.sleep(Config.GROQ_REQUEST_DELAY)

        # 3. Build strict prompt
        formatted_options = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])

        prompt = f"""You are an expert technical evaluator solving an educational multiple-choice question for Digital NTTF.

Question:
{question}

Available options:
{formatted_options}

{f"Instructions/Context: {instructions}" if instructions else ""}

Task:
1. Carefully analyze the question and all choices.
2. Select the single most accurate option from the available list.
3. Match the exact option text verbatim.
4. Provide confidence (0.0 to 1.0) and a concise 1-sentence technical explanation.

Return ONLY a valid JSON object matching this schema:
{{
  "answer_index": <INTEGER from 1 to {len(options)}>,
  "answer_text": "<exact option text>",
  "confidence": <FLOAT between 0.0 and 1.0>,
  "reasoning": "<brief technical explanation>"
}}"""

        if not self.model or not self.client:
            log_event("AI_ERROR", "Groq client or valid model is not available.")
            return {
                "answer_index": None,
                "answer_text": None,
                "confidence": 0.0,
                "reasoning": "Groq model unavailable",
                "error": True,
                "from_cache": False
            }

        log_event("GROQ_REQUEST", f"Asking Groq ({self.model}) for: '{question[:70]}...' ({len(options)} options)")

        attempt = 0
        while self.model and attempt < 4:
            attempt += 1
            current_model = self.model
            try:
                response_data = self._call_groq_json(prompt)
                if response_data:
                    ans_idx = int(response_data.get("answer_index", 1))
                    if ans_idx < 1 or ans_idx > len(options):
                        text_match_idx = self._find_matching_option_index(response_data.get("answer_text", ""), options)
                        if text_match_idx is not None:
                            ans_idx = text_match_idx + 1
                            response_data["answer_index"] = ans_idx

                    ans_text = response_data.get("answer_text", "")
                    if 1 <= ans_idx <= len(options) and not ans_text:
                        response_data["answer_text"] = options[ans_idx - 1]

                    confidence = float(response_data.get("confidence", 0.90))
                    response_data["confidence"] = confidence

                    log_event("GROQ_RESPONSE",
                              f"Groq selected Option {ans_idx}: '{response_data.get('answer_text')}' (Confidence: {confidence:.2f})")

                    self.db.save_cached_answer(question, options, response_data, self.model)
                    response_data["from_cache"] = False
                    return response_data

            except Exception as e:
                err_str = str(e).lower()
                if "401" in err_str or ("invalid" in err_str and "key" in err_str):
                    log_event("AI_ERROR", "Invalid Groq API key. Stopping AI calls.")
                    break
                elif "404" in err_str or "model_not_found" in err_str or "not found" in err_str:
                    log_event("AI_ERROR", f"Model unavailable: '{current_model}'. Switching model.")
                    next_m = self.switch_to_next_fallback_model(current_model, "404 model_not_found")
                    if not next_m:
                        break
                    continue
                elif "403" in err_str or "permission" in err_str or "forbidden" in err_str:
                    log_event("AI_ERROR", f"Access denied for model: '{current_model}'. Switching model.")
                    next_m = self.switch_to_next_fallback_model(current_model, "403 forbidden")
                    if not next_m:
                        break
                    continue
                elif "429" in err_str or "rate limit" in err_str:
                    backoff = min(2.0 ** attempt + 1.0, 15.0)
                    log_event("AI_ERROR", f"Groq rate limit reached (429). Exponential backoff {backoff:.1f}s...")
                    time.sleep(backoff)
                    continue
                else:
                    backoff = min(2.0 ** attempt, 10.0)
                    log_event("AI_ERROR", f"Groq request error ({e}). Retrying in {backoff:.1f}s...")
                    time.sleep(backoff)
                    continue

        return {
            "answer_index": None,
            "answer_text": None,
            "confidence": 0.0,
            "reasoning": "Groq inference failed",
            "error": True,
            "from_cache": False
        }

    def get_long_answer(self, question: str, subject_context: str = "") -> Dict[str, Any]:
        """
        Generate high-quality, technically accurate Long-Answer response for Digital NTTF
        Diploma engineering assignments.
        """
        if not question or not question.strip():
            return {
                "answer": "",
                "confidence": 0.0,
                "error": True,
                "reason": "Empty question string"
            }

        # 1. Check local SQLite Cache first
        cached = self.db.get_cached_answer(question, ["LONG_ANSWER"])
        if cached and cached.get("answer"):
            log_event("GROQ_RESPONSE", f"Loaded long-answer from cache ({len(cached['answer'])} chars)")
            return cached

        # 2. Rate limit delay
        if Config.GROQ_REQUEST_DELAY > 0:
            time.sleep(Config.GROQ_REQUEST_DELAY)

        # 3. Clean, direct prompt for diploma-level engineering (4-mark answer)
        prompt = f"""You are answering a Diploma-level engineering assignment for Digital NTTF (4-mark long answer question).

Question:
{question}

Requirements:
- Directly answer the question with technical precision.
- Provide a clear, technically correct explanation suitable for a 4-mark academic question.
- Avoid unnecessary introduction, preamble, or conversational filler.
- Avoid markdown code blocks unless strictly relevant.
- Return ONLY the exact answer text."""

        if not self.model or not self.client:
            log_event("AI_ERROR", "No usable Groq text model available")
            return {
                "answer": "",
                "confidence": 0.0,
                "error": True,
                "reason": "No usable Groq model available"
            }

        attempt = 0
        while self.model and attempt < 4:
            attempt += 1
            current_model = self.model
            try:
                log_event("GROQ", "Request sent")
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a professional engineering instructor answering diploma-level assignments. Provide direct, technically accurate, clear, and relevant answers with no preamble or conversational filler. Return only the answer text."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    model=current_model,
                    temperature=0.2,
                    max_tokens=600
                )

                answer_text = chat_completion.choices[0].message.content.strip()
                if answer_text.startswith("```") and answer_text.endswith("```"):
                    lines = answer_text.split("\n")
                    answer_text = "\n".join(lines[1:-1]).strip()

                if answer_text and len(answer_text) > 10:
                    res = {
                        "answer": answer_text,
                        "confidence": 0.95,
                        "error": False,
                        "from_cache": False,
                        "model": current_model
                    }
                    log_event("GROQ", "Answer received")
                    self.db.save_cached_answer(question, ["LONG_ANSWER"], res, current_model)
                    return res

            except Exception as e:
                err_str = str(e).lower()
                if "401" in err_str or ("invalid" in err_str and "key" in err_str):
                    log_event("AI_ERROR", "Invalid Groq API key. Stopping AI calls.")
                    break
                elif "404" in err_str or "model_not_found" in err_str or "not found" in err_str:
                    log_event("AI_ERROR", f"Model unavailable: '{current_model}'. Switching model.")
                    next_m = self.switch_to_next_fallback_model(current_model, "404 model_not_found")
                    if not next_m:
                        break
                    continue
                elif "403" in err_str or "permission" in err_str or "forbidden" in err_str:
                    log_event("AI_ERROR", f"Access denied for model: '{current_model}'. Switching model.")
                    next_m = self.switch_to_next_fallback_model(current_model, "403 forbidden")
                    if not next_m:
                        break
                    continue
                elif "429" in err_str or "rate limit" in err_str:
                    backoff = min(2.0 ** attempt + 1.0, 15.0)
                    log_event("AI_ERROR", f"Groq rate limit reached (429). Exponential backoff {backoff:.1f}s...")
                    time.sleep(backoff)
                    continue
                else:
                    backoff = min(2.0 ** attempt, 10.0)
                    log_event("AI_ERROR", f"Groq request error ({e}). Retrying in {backoff:.1f}s...")
                    time.sleep(backoff)
                    continue

        return {
            "answer": "",
            "confidence": 0.0,
            "error": True,
            "reason": "AI inference failed"
        }

    def get_subjective_answer(self, question: str, subject_context: str = "") -> Dict[str, Any]:
        """Subjective answer helper (delegates to get_long_answer)."""
        return self.get_long_answer(question, subject_context)

    def _call_groq_json(self, prompt: str) -> Optional[Dict[str, Any]]:
        """Execute chat completion via Groq with JSON response enforcement."""
        if not self.client or not self.model:
            raise RuntimeError("Groq Client is not configured or no model selected.")

        chat_completion = self.client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise technical question-answering system. You always respond in valid JSON matching the requested schema without markdown codeblocks or conversational text."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            model=self.model,
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        content = chat_completion.choices[0].message.content
        if not content:
            raise ValueError("Empty response received from Groq API")

        raw_text = content.strip()
        cleaned = raw_text
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"Could not parse valid JSON from output: {raw_text[:200]}")

    def _find_matching_option_index(self, target_text: str, options: List[str]) -> Optional[int]:
        """Find best matching index for option text."""
        norm_target = " ".join(target_text.lower().split())
        for idx, opt in enumerate(options):
            norm_opt = " ".join(opt.lower().split())
            if norm_target == norm_opt or norm_target in norm_opt or norm_opt in norm_target:
                return idx
        return None
