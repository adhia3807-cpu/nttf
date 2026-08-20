"""
Digital NTTF Auto Solver - Logging Module
Structured, sanitized event logger for execution tracking and status reporting.
"""

import sys
import re
import logging
from datetime import datetime
from pathlib import Path
from config import Config

class SecretFilter(logging.Filter):
    """Redact sensitive passwords and API keys from logs."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = str(record.msg)
        if Config.PASSWORD and len(Config.PASSWORD) > 2:
            msg = msg.replace(Config.PASSWORD, '********')
        if Config.GROQ_API_KEY and len(Config.GROQ_API_KEY) > 5:
            msg = msg.replace(Config.GROQ_API_KEY, '[REDACTED_GROQ_KEY]')
        # Redact generic Groq keys matching pattern gsk_...
        msg = re.sub(r'gsk_[0-9A-Za-z]{20,}', '[REDACTED_GROQ_KEY]', msg)
        record.msg = msg
        return True

def setup_logger():
    Config.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    Config.SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    
    log = logging.getLogger("DigitalNTTF")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    
    secret_filter = SecretFilter()
    
    # File Handler
    fh = logging.FileHandler(Config.LOG_FILE, encoding='utf-8')
    fh.setLevel(logging.INFO)
    fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
    fh.addFilter(secret_filter)
    log.addHandler(fh)
    
    # Console Handler (flush immediately for subprocess capture)
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S'))
    ch.addFilter(secret_filter)
    log.addHandler(ch)
    
    return log

logger = setup_logger()

def log_event(event: str, details: str = ""):
    """Standardized event logger conforming to specification."""
    msg = f"[{event}] {details}" if details else f"[{event}]"
    if event == "ERROR":
        logger.error(msg)
    else:
        logger.info(msg)
    sys.stdout.flush()
