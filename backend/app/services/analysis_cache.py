import hashlib
import time
import threading
from typing import Optional, Dict, Any, Tuple
from collections import OrderedDict
from app.models.analysis import AnalyzeCodeResponse

MAX_ANALYSIS_CACHE_SIZE = 500
ANALYSIS_CACHE_TTL_SECONDS = 3600  # 1 hour


class AnalysisCache:
    """
    Thread-safe bounded in-memory cache and concurrency guard for code analysis responses.
    - Reuses an existing analysis only when code fingerprint and configuration match.
    - Prevents duplicate concurrent submissions for the exact same fingerprint.
    - Does not reuse results for different code.
    """

    def __init__(self, max_size: int = MAX_ANALYSIS_CACHE_SIZE, ttl_seconds: int = ANALYSIS_CACHE_TTL_SECONDS):
        self._lock = threading.RLock()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self._in_flight: Dict[str, threading.Event] = {}
        self._in_flight_results: Dict[str, Any] = {}
        self._in_flight_errors: Dict[str, Exception] = {}

    @staticmethod
    def compute_fingerprint(code: str, language: str, learning_level: str) -> str:
        """
        Compute deterministic SHA-256 fingerprint from code content, language, and learning level.
        """
        raw_key = f"{code.strip()}||{language.strip().lower()}||{learning_level.strip().lower()}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get(self, fingerprint: str) -> Optional[AnalyzeCodeResponse]:
        """Retrieve cached analysis if present and not expired."""
        with self._lock:
            entry = self._cache.get(fingerprint)
            if not entry:
                return None
            if time.time() - entry["created_at"] > self._ttl_seconds:
                self._cache.pop(fingerprint, None)
                return None
            self._cache.move_to_end(fingerprint)
            return entry["response"]

    def put(self, fingerprint: str, response: AnalyzeCodeResponse) -> None:
        """Store analysis response in cache with eviction if capacity exceeded."""
        with self._lock:
            now = time.time()
            if len(self._cache) >= self._max_size:
                oldest_key, _ = next(iter(self._cache.items()))
                self._cache.pop(oldest_key, None)
            self._cache[fingerprint] = {
                "created_at": now,
                "response": response,
            }
            self._cache.move_to_end(fingerprint)

    def acquire_in_flight(self, fingerprint: str) -> Tuple[bool, Optional[threading.Event]]:
        """
        Acquire in-flight execution rights for a fingerprint.
        Returns (is_leader, event):
        - If is_leader is True: caller must compute result and call complete_in_flight.
        - If is_leader is False: caller must wait on event and then call get_in_flight_result.
        """
        with self._lock:
            # First check if result was already cached
            cached = self._cache.get(fingerprint)
            if cached and time.time() - cached["created_at"] <= self._ttl_seconds:
                return False, None

            if fingerprint in self._in_flight:
                return False, self._in_flight[fingerprint]

            event = threading.Event()
            self._in_flight[fingerprint] = event
            return True, event

    def complete_in_flight(
        self,
        fingerprint: str,
        response: Optional[AnalyzeCodeResponse] = None,
        error: Optional[Exception] = None,
    ) -> None:
        """Complete an in-flight computation, notifying any waiting concurrent requests."""
        event = None
        with self._lock:
            if response is not None:
                now = time.time()
                if len(self._cache) >= self._max_size:
                    oldest_key, _ = next(iter(self._cache.items()))
                    self._cache.pop(oldest_key, None)
                self._cache[fingerprint] = {
                    "created_at": now,
                    "response": response,
                }
                self._cache.move_to_end(fingerprint)
                self._in_flight_results[fingerprint] = response
            elif error is not None:
                self._in_flight_errors[fingerprint] = error

            event = self._in_flight.get(fingerprint)

        if event is not None:
            event.set()

    def release_in_flight(self, fingerprint: str) -> None:
        """Clean up in-flight bookkeeping after all waiters have finished or timed out."""
        with self._lock:
            self._in_flight.pop(fingerprint, None)
            self._in_flight_results.pop(fingerprint, None)
            self._in_flight_errors.pop(fingerprint, None)

    def get_in_flight_result(self, fingerprint: str) -> Optional[AnalyzeCodeResponse]:
        """Retrieve the result completed by the leader for this in-flight request."""
        with self._lock:
            if fingerprint in self._in_flight_errors:
                raise self._in_flight_errors[fingerprint]
            if fingerprint in self._in_flight_results:
                return self._in_flight_results[fingerprint]
            # Fallback to cache lookup
            entry = self._cache.get(fingerprint)
            if entry:
                return entry["response"]
            return None

    def clear(self) -> None:
        """Clear all cached entries and in-flight tracking (useful for testing)."""
        with self._lock:
            self._cache.clear()
            self._in_flight.clear()
            self._in_flight_results.clear()
            self._in_flight_errors.clear()


# Global singleton instance
analysis_cache = AnalysisCache()
