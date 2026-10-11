import os
from pathlib import Path
from dotenv import load_dotenv

# Locate backend root and load .env file
BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BACKEND_DIR / ".env"
load_dotenv(dotenv_path=ENV_PATH, override=True)

# Default to verified active model if unset
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"
DEFAULT_FALLBACK_MODEL = None

# Retry policy constants for transient 503 errors
MAX_503_RETRIES = 2
INITIAL_BACKOFF_SECONDS = 1.0
BACKOFF_FACTOR = 2.0
MAX_BACKOFF_SECONDS = 10.0
JITTER_RATIO = 0.25

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "").strip() or None
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

def get_configured_model() -> str:
    """Return the active model name from environment or fallback default."""
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL

def get_primary_model() -> str:
    """Return the primary Gemini model name."""
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_GEMINI_MODEL

def get_fallback_model() -> str | None:
    """Return the fallback Gemini model name if configured, or None."""
    val = os.getenv("GEMINI_FALLBACK_MODEL", "").strip()
    return val if val else None

def is_api_key_configured() -> bool:
    """Check if API key is present and not a placeholder, without leaking key contents."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return bool(key and key != "YOUR_KEY_HERE")
