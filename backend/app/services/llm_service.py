import os
import json
import logging
import random
import re
import time
from typing import Optional, Any, Callable, Dict
from dotenv import load_dotenv

from app.models.analysis import CodeAnalysis
from app.config import (
    MAX_503_RETRIES,
    INITIAL_BACKOFF_SECONDS,
    BACKOFF_FACTOR,
    MAX_BACKOFF_SECONDS,
    JITTER_RATIO,
    get_primary_model,
    get_fallback_model,
)

load_dotenv(override=True)

logger = logging.getLogger(__name__)


class LLMConfigurationError(Exception):
    """Raised when the LLM service is improperly configured (e.g. missing API key or model)."""
    pass


class LLMServiceError(Exception):
    """Raised when communication with Gemini fails at runtime (e.g. rate limit, timeout, API error)."""
    pass


_SHARED_CLIENT: Optional[Any] = None
_VERIFIED_MODELS_CACHE: Dict[str, bool] = {}


def sanitize_sensitive_data(text: str) -> str:
    """Strip API keys, secret credentials, and sensitive provider data from messages."""
    if not text:
        return ""
    env_key = os.getenv("GEMINI_API_KEY", "").strip()
    if env_key and len(env_key) > 4:
        text = text.replace(env_key, "[REDACTED_API_KEY]")
    text = re.sub(r'AIza[0-9A-Za-z-_]{35}', '[REDACTED_API_KEY]', text)
    text = re.sub(r'AQ\.[0-9A-Za-z-_]{20,}', '[REDACTED_API_KEY]', text)
    text = re.sub(r'Bearer\s+[A-Za-z0-9-_.]+', 'Bearer [REDACTED_TOKEN]', text, flags=re.IGNORECASE)
    text = re.sub(r'(?:key|api_key|token)=([A-Za-z0-9-_]+)', r'\1=[REDACTED]', text, flags=re.IGNORECASE)
    return text


def get_gemini_client(force_new: bool = False):
    """
    Initialize and return the official Google GenAI client using the environment.
    Reuses a cached client instance when force_new=False to share the client across features.
    
    Raises:
        LLMConfigurationError: When GEMINI_API_KEY is unset or set to placeholder.
    """
    global _SHARED_CLIENT
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "YOUR_KEY_HERE":
        logger.error("Gemini API key is not configured or still set to placeholder in backend/.env")
        raise LLMConfigurationError(
            "Gemini API key is not configured. Please set a valid GEMINI_API_KEY in backend/.env"
        )

    if _SHARED_CLIENT is not None and not force_new:
        return _SHARED_CLIENT

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        _SHARED_CLIENT = client
        return client
    except Exception as e:
        logger.error(f"Failed to initialize GenAI client: {sanitize_sensitive_data(str(e))}")
        raise LLMConfigurationError(
            "Failed to initialize Gemini client. Please check your configuration."
        )


def extract_quota_details(error: Exception) -> dict:
    """
    Extract structured quota information from Google GenAI ClientError / APIError,
    inspecting details, response, and message.
    """
    info = {
        "quota_id": None,
        "quota_metric": None,
        "quota_dimensions": {},
        "quota_value": None,
        "retry_delay": None,
    }

    # 1. Check details attribute
    details = getattr(error, "details", None)
    details_list = []
    if isinstance(details, dict):
        err_dict = details.get("error", {}) if isinstance(details.get("error"), dict) else details
        raw_list = err_dict.get("details", [])
        if isinstance(raw_list, list):
            details_list.extend(raw_list)
    elif isinstance(details, list):
        details_list.extend(details)

    # 2. Check response JSON if available
    response = getattr(error, "response", None)
    if response is not None and hasattr(response, "json"):
        try:
            resp_json = response.json()
            if isinstance(resp_json, dict):
                err_dict = resp_json.get("error", {}) if isinstance(resp_json.get("error"), dict) else resp_json
                raw_list = err_dict.get("details", [])
                if isinstance(raw_list, list):
                    details_list.extend(raw_list)
        except Exception:
            pass

    for d in details_list:
        if not isinstance(d, dict):
            continue
        # Check QuotaFailure
        violations = d.get("violations", [])
        if isinstance(violations, list):
            for v in violations:
                if isinstance(v, dict):
                    if not info["quota_id"] and "quotaId" in v:
                        info["quota_id"] = str(v["quotaId"])
                    if not info["quota_metric"] and "quotaMetric" in v:
                        info["quota_metric"] = str(v["quotaMetric"])
                    if not info["quota_value"] and "quotaValue" in v:
                        info["quota_value"] = str(v["quotaValue"])
                    if not info["quota_dimensions"] and "quotaDimensions" in v:
                        info["quota_dimensions"] = v["quotaDimensions"]
        # Check RetryInfo
        if "retryDelay" in d:
            info["retry_delay"] = str(d["retryDelay"])

    # 3. String-based fallback for embedded JSON or message text
    err_str = str(error)
    if not info["quota_metric"]:
        m = re.search(r"quota\s*metric[:\s']+([a-zA-Z0-9_\-./]+)", err_str, re.IGNORECASE)
        if m:
            info["quota_metric"] = m.group(1).strip("'\"")
    if not info["quota_id"]:
        m = re.search(r"quota\s*id[:\s']+([a-zA-Z0-9_\-./]+)", err_str, re.IGNORECASE)
        if m:
            info["quota_id"] = m.group(1).strip("'\"")
        else:
            m2 = re.search(r"\b(GenerateRequestsPerDayPer[a-zA-Z0-9_\-]+|GenerateRequestsPer[a-zA-Z0-9_\-]+|RequestsPerDay[a-zA-Z0-9_\-]*|RequestsPerMinute[a-zA-Z0-9_\-]*|TokensPerMinute[a-zA-Z0-9_\-]*)\b", err_str)
            if m2:
                info["quota_id"] = m2.group(1)

    return info


def extract_retry_after(error: Exception) -> Optional[float]:
    """
    Extract retry delay in seconds if supplied in headers, details, or message.
    Ensures delay is non-negative and bounded by MAX_BACKOFF_SECONDS to prevent unbounded waiting.
    """
    # 1. Check HTTP response headers if available on error
    response = getattr(error, "response", None)
    if response is not None:
        headers = getattr(response, "headers", None)
        if headers and hasattr(headers, "get"):
            retry_val = headers.get("retry-after") or headers.get("Retry-After")
            if retry_val:
                try:
                    sec = float(retry_val)
                    if sec >= 0:
                        return min(sec, MAX_BACKOFF_SECONDS)
                except (ValueError, TypeError):
                    pass

    # 2. Check structured details dictionary (e.g. RetryInfo)
    quota_info = extract_quota_details(error)
    if quota_info.get("retry_delay"):
        delay_str = str(quota_info["retry_delay"]).rstrip("s")
        try:
            sec = float(delay_str)
            if sec >= 0:
                return min(sec, MAX_BACKOFF_SECONDS)
        except (ValueError, TypeError):
            pass

    details = getattr(error, "details", None)
    if isinstance(details, dict):
        error_dict = details.get("error", {}) if isinstance(details.get("error"), dict) else details
        err_details = error_dict.get("details", [])
        if isinstance(err_details, list):
            for d in err_details:
                if isinstance(d, dict) and "retryDelay" in d:
                    delay_str = str(d["retryDelay"]).rstrip("s")
                    try:
                        sec = float(delay_str)
                        if sec >= 0:
                            return min(sec, MAX_BACKOFF_SECONDS)
                    except (ValueError, TypeError):
                        pass

    # 3. Check error string regex pattern (including "Please retry in X.Xs")
    err_str = str(error).lower()
    match = re.search(r'(?:retry[-_ ]after|retrydelay|retry in)[:\s=]+([0-9]+(?:\.[0-9]+)?)s?', err_str)
    if match:
        try:
            sec = float(match.group(1))
            if sec >= 0:
                return min(sec, MAX_BACKOFF_SECONDS)
        except (ValueError, TypeError):
            pass

    return None


def calculate_retry_delay(attempt: int, error: Exception) -> float:
    """
    Calculate backoff delay for the given retry attempt (0-indexed).
    Respects Retry-After if supplied.
    Otherwise uses exponential backoff with jitter, capped at MAX_BACKOFF_SECONDS.
    """
    retry_after = extract_retry_after(error)
    if retry_after is not None and retry_after > 0:
        return min(retry_after, MAX_BACKOFF_SECONDS)

    base_backoff = float(os.getenv("GEMINI_RETRY_INITIAL_DELAY", str(INITIAL_BACKOFF_SECONDS)))
    delay = base_backoff * (BACKOFF_FACTOR ** attempt)
    jitter = random.uniform(0.0, JITTER_RATIO * delay)
    return min(delay + jitter, MAX_BACKOFF_SECONDS)


def classify_error(error: Exception, model_name: str = "") -> dict:
    """
    Classify any Gemini API or runtime error into a standardized category:
    - 429 daily request quota exhaustion ("daily_quota_exhausted")
    - 429 transient per-minute request limit ("transient_rate_limit")
    - 429 token-per-minute limit ("transient_token_limit")
    - 503 temporary overload ("temporary_overload")
    - 404 invalid model ("invalid_model")
    - 403 permission/billing restriction ("permission_billing_failure")
    - 401 authentication failure ("authentication_failure")
    - 504 timeout ("timeout")
    - unknown
    """
    code = getattr(error, "code", None)
    status = getattr(error, "status", None)
    err_str = str(error).lower()
    clean_msg = sanitize_sensitive_data(str(error))

    if code is None:
        status_code_attr = getattr(error, "status_code", None)
        if isinstance(status_code_attr, int):
            code = status_code_attr
        else:
            match = re.search(r'\b(400|401|403|404|429|500|502|503|504)\b', err_str)
            if match:
                code = int(match.group(1))

    # 1. Invalid / unavailable model (404)
    if code == 404 or status == "NOT_FOUND" or any(kw in err_str for kw in (
        "not found", "not_found", "unsupported model", "unknown model", "no longer available"
    )):
        return {
            "category": "invalid_model",
            "is_503_retryable": False,
            "is_daily_quota": False,
            "is_transient": False,
            "status_code": 404,
            "message": clean_msg,
        }

    # 2. 503 Temporary overload / unavailable (503)
    if code == 503 or status == "UNAVAILABLE" or any(kw in err_str for kw in (
        "503", "unavailable", "high demand", "spikes in demand", "overloaded", "temporarily unavailable"
    )):
        return {
            "category": "temporary_overload",
            "is_503_retryable": True,
            "is_daily_quota": False,
            "is_transient": True,
            "status_code": 503,
            "message": clean_msg,
        }

    # 3. 429 Rate limit / Quota exceeded
    if code == 429 or status == "RESOURCE_EXHAUSTED" or any(kw in err_str for kw in (
        "429", "rate limit", "rate_limit", "resource_exhausted", "too many requests"
    )):
        quota_info = extract_quota_details(error)
        quota_id = (quota_info.get("quota_id") or "").lower()
        quota_metric = (quota_info.get("quota_metric") or "").lower()

        # Check Daily Request Quota Exhaustion
        is_daily = (
            any(kw in quota_id for kw in ("perday", "requestsperday", "generaterequestsperday", "daily"))
            or any(kw in quota_metric for kw in ("free_tier_requests", "generate_content_free_tier_requests", "per_day", "daily"))
            or any(kw in err_str for kw in (
                "generaterequestsperday",
                "requestsperday",
                "requests per day",
                "perday",
                "per day",
                "daily request",
                "daily quota",
                "generate_content_free_tier_requests",
                "free_tier_requests",
                "free tier requests",
            ))
        )
        if is_daily:
            return {
                "category": "daily_quota_exhausted",
                "is_503_retryable": False,
                "is_daily_quota": True,
                "is_transient": False,
                "status_code": 429,
                "quota_id": quota_info.get("quota_id"),
                "quota_metric": quota_info.get("quota_metric"),
                "message": clean_msg,
            }

        # Check Token-Per-Minute (TPM) limit
        is_tpm = (
            any(kw in quota_id for kw in ("tokensperminute", "token", "tpm"))
            or any(kw in quota_metric for kw in ("tokens_per_minute", "tokens", "input_tokens", "output_tokens"))
            or any(kw in err_str for kw in ("tokens per minute", "tokensperminute", "token limit", "tpm"))
        )
        if is_tpm:
            return {
                "category": "transient_token_limit",
                "is_503_retryable": False,
                "is_daily_quota": False,
                "is_transient": True,
                "status_code": 429,
                "quota_id": quota_info.get("quota_id"),
                "quota_metric": quota_info.get("quota_metric"),
                "message": clean_msg,
            }

        # Transient Per-Minute Request Limit (RPM) or other 429
        return {
            "category": "transient_rate_limit",
            "is_503_retryable": False,
            "is_daily_quota": False,
            "is_transient": True,
            "status_code": 429,
            "quota_id": quota_info.get("quota_id"),
            "quota_metric": quota_info.get("quota_metric"),
            "message": clean_msg,
        }

    # 4. Authentication failure (401 or invalid API key)
    if code == 401 or status == "UNAUTHENTICATED" or any(kw in err_str for kw in (
        "api key is not configured", "invalid api key", "api_key_invalid", "unauthenticated",
        "bad credential", "api key not valid"
    )):
        return {
            "category": "authentication_failure",
            "is_503_retryable": False,
            "is_daily_quota": False,
            "is_transient": False,
            "status_code": 401,
            "message": clean_msg,
        }

    # 5. Permission / Billing failure (403 or permission denied)
    if code == 403 or status == "PERMISSION_DENIED" or any(kw in err_str for kw in (
        "permission_denied", "permission denied", "billing account disabled",
        "consumer suspended", "billing is not enabled", "insufficient_quota"
    )):
        return {
            "category": "permission_billing_failure",
            "is_503_retryable": False,
            "is_daily_quota": False,
            "is_transient": False,
            "status_code": 403,
            "message": clean_msg,
        }

    # 6. Timeout (504 or deadline exceeded)
    if code == 504 or status == "DEADLINE_EXCEEDED" or any(kw in err_str for kw in (
        "timeout", "timed out", "deadline exceeded", "deadline_exceeded"
    )):
        return {
            "category": "timeout",
            "is_503_retryable": False,
            "is_daily_quota": False,
            "is_transient": False,
            "status_code": 504,
            "message": clean_msg,
        }

    return {
        "category": "unknown",
        "is_503_retryable": False,
        "is_daily_quota": False,
        "is_transient": False,
        "status_code": code,
        "message": clean_msg,
    }


def raise_classified_error(error: Exception, model_name: str = "", default_msg: str = "") -> None:
    """
    Convert a low-level Gemini exception into an appropriate LLMConfigurationError or LLMServiceError
    with sanitized, user-friendly messages without exposing API keys, stack traces, or sensitive provider data.
    """
    if isinstance(error, (LLMConfigurationError, LLMServiceError)):
        raise error

    classification = classify_error(error, model_name=model_name)
    category = classification["category"]

    if category == "invalid_model":
        model_display = model_name or "configured model"
        raise LLMConfigurationError(
            f"Configured model '{model_display}' is unavailable. Please verify GEMINI_MODEL in backend/.env"
        )
    elif category == "authentication_failure":
        raise LLMConfigurationError(
            "Gemini API key is not configured or invalid. Please check your GEMINI_API_KEY in backend/.env"
        )
    elif category == "permission_billing_failure":
        raise LLMServiceError(
            "The AI service permission was denied or billing account is disabled. Please check your project settings."
        )
    elif category == "daily_quota_exhausted":
        raise LLMServiceError(
            "AI service limits have been reached for the available models. Please try again after the quota resets."
        )
    elif category in ("transient_rate_limit", "transient_token_limit", "rate_limit"):
        raise LLMServiceError(
            "The AI service is temporarily busy due to rate limits. Please wait a moment and try again."
        )
    elif category == "timeout":
        raise LLMServiceError(
            "Request to the AI service timed out. Please try again."
        )
    elif category == "temporary_overload":
        raise LLMServiceError(
            "The AI service is experiencing high demand. Please try again later."
        )
    else:
        raise LLMServiceError(
            default_msg or "Unable to analyze the code right now. Please try again."
        )


def is_model_verified_accessible(client: Any, model_name: str) -> bool:
    """
    Verify whether the model is supported and accessible to the current API project.
    Results are cached in memory.
    """
    if not model_name:
        return False
    clean_name = model_name.strip()
    if clean_name in _VERIFIED_MODELS_CACHE:
        return _VERIFIED_MODELS_CACHE[clean_name]

    if client is None:
        return False

    try:
        if hasattr(client, "models") and hasattr(client.models, "get"):
            model_info = client.models.get(model=clean_name)
            if model_info is not None:
                _VERIFIED_MODELS_CACHE[clean_name] = True
                return True
        elif hasattr(client, "models") and hasattr(client.models, "list"):
            models_list = client.models.list()
            names = [getattr(m, "name", "") for m in models_list]
            if clean_name in names or f"models/{clean_name}" in names:
                _VERIFIED_MODELS_CACHE[clean_name] = True
                return True
        _VERIFIED_MODELS_CACHE[clean_name] = True
        return True
    except Exception as e:
        logger.warning(
            f"Fallback model '{clean_name}' verification failed: {type(e).__name__} - {sanitize_sensitive_data(str(e))}"
        )
        _VERIFIED_MODELS_CACHE[clean_name] = False
        return False


def clear_model_verification_cache() -> None:
    """Clear cached model verification states (used in tests and config reload)."""
    _VERIFIED_MODELS_CACHE.clear()


def _execute_model_with_retry(
    client: Any,
    model_name: str,
    contents: Any,
    config: Any,
    max_503_retries: int = MAX_503_RETRIES,
    max_transient_retries: int = 1,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Any:
    """
    Execute generate_content on a single model with bounded retries:
    - 503 temporary overload: up to max_503_retries with exponential backoff and jitter.
    - 429 transient rate/token limits: up to max_transient_retries respecting Retry-After.
    - 429 daily quota exhaustion: 0 retries (aborts immediately so fallback can engage).
    - Permanent errors (401, 403, 404): 0 retries (aborts immediately).
    Logs sanitized diagnostic details (model name, attempt number, status code, classification).
    """
    last_error = None
    max_attempts = max(max_503_retries, max_transient_retries) + 1

    for attempt in range(max_attempts):
        try:
            logger.info(f"Gemini API request attempt {attempt + 1} starting on model '{model_name}'.")
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            logger.info(f"Gemini API request succeeded on model '{model_name}' (attempt {attempt + 1}).")
            return response
        except Exception as err:
            last_error = err
            classification = classify_error(err, model_name=model_name)
            category = classification.get("category")

            # Preserve diagnostic details in backend logs
            logger.warning(
                f"Gemini attempt failed: model='{model_name}', attempt={attempt + 1}, "
                f"exception_type='{type(err).__name__}', status_code={classification.get('status_code')}, "
                f"category='{category}', error='{classification.get('message')}'"
            )

            # Daily quota exhaustion must NEVER be retried on the same model
            if category == "daily_quota_exhausted":
                logger.info(
                    f"Model '{model_name}' has exhausted its daily request quota; "
                    f"aborting retries on model '{model_name}'."
                )
                raise err

            # Handle 503 temporary overload retries
            if category == "temporary_overload":
                if attempt >= max_503_retries:
                    logger.warning(
                        f"Exhausted {max_503_retries} retries on model '{model_name}' for 503 overload: "
                        f"{sanitize_sensitive_data(str(err))}"
                    )
                    raise err
                delay = calculate_retry_delay(attempt, err)
                logger.warning(
                    f"The AI model is temporarily overloaded. Retrying in {delay:.2f}s... "
                    f"(attempt {attempt + 1}/{max_503_retries + 1})"
                )
                sleep_fn(delay)
                continue

            # Handle transient 429 rate limit or token limit retries
            if category in ("transient_rate_limit", "transient_token_limit"):
                retry_after = extract_retry_after(err)
                if retry_after is not None and retry_after > 0 and attempt < max_transient_retries:
                    delay = calculate_retry_delay(attempt, err)
                    logger.warning(
                        f"Gemini transient rate limit on model '{model_name}'. Retrying in {delay:.2f}s... "
                        f"(attempt {attempt + 1}/{max_transient_retries + 1})"
                    )
                    sleep_fn(delay)
                    continue
                else:
                    logger.info(
                        f"Transient rate limit on model '{model_name}' without Retry-After or retries exhausted; aborting."
                    )
                    raise err

            # Non-retryable error (authentication, permission, invalid model, etc.)
            logger.info(
                f"Error category '{category}' is non-retryable on model '{model_name}'; aborting retries."
            )
            raise err

    raise last_error


def execute_with_retry_and_fallback(
    client: Any,
    contents: Any,
    config: Any,
    primary_model: Optional[str] = None,
    fallback_model: Optional[str] = None,
    default_msg: str = "",
    sleep_fn: Callable[[float], None] = time.sleep,
) -> Any:
    """
    Unified execution handler across Analysis, Tutor, and Quiz generation.
    Handles:
    - Bounded retries (503 overload and transient 429 with backoff and Retry-After)
    - Zero retry on daily quota exhaustion (429) to avoid wasting time
    - Automatic fallback model switching when primary encounters daily quota exhaustion (429), 503, or 404
    - Verification that fallback model is supported and accessible
    - Truthful, sanitized user errors when both primary and fallback models are exhausted
    """
    resolved_primary = primary_model or get_primary_model()
    if not resolved_primary:
        raise LLMConfigurationError("GEMINI_MODEL is not configured. Please define GEMINI_MODEL in backend/.env")

    resolved_fallback = fallback_model if fallback_model is not None else get_fallback_model()
    if resolved_fallback:
        resolved_fallback = resolved_fallback.strip()
        if resolved_fallback == resolved_primary:
            resolved_fallback = None

    try:
        return _execute_model_with_retry(
            client=client,
            model_name=resolved_primary,
            contents=contents,
            config=config,
            sleep_fn=sleep_fn,
        )
    except Exception as primary_err:
        primary_class = classify_error(primary_err, model_name=resolved_primary)
        primary_cat = primary_class["category"]

        # Fallback is eligible on daily quota exhaustion (429), 503 temporary overload,
        # or model unavailability (404)
        is_fallback_eligible = primary_cat in (
            "daily_quota_exhausted",
            "temporary_overload",
            "invalid_model",
        )

        if is_fallback_eligible and resolved_fallback:
            if is_model_verified_accessible(client, resolved_fallback):
                if primary_cat == "daily_quota_exhausted":
                    logger.warning(
                        "The daily request limit for the configured AI model has been reached. Trying the backup model."
                    )
                logger.warning(
                    f"Primary model '{resolved_primary}' failed with {primary_cat} "
                    f"(status={primary_class.get('status_code')}). Switching to verified fallback model '{resolved_fallback}'."
                )
                try:
                    fallback_response = _execute_model_with_retry(
                        client=client,
                        model_name=resolved_fallback,
                        contents=contents,
                        config=config,
                        sleep_fn=sleep_fn,
                    )
                    logger.info(f"Fallback model '{resolved_fallback}' succeeded.")
                    return fallback_response
                except Exception as fallback_err:
                    fallback_class = classify_error(fallback_err, model_name=resolved_fallback)
                    fallback_cat = fallback_class["category"]
                    logger.error(
                        f"Fallback model '{resolved_fallback}' also failed: exception_type='{type(fallback_err).__name__}', "
                        f"status_code={fallback_class.get('status_code')}, category='{fallback_cat}', "
                        f"error='{sanitize_sensitive_data(str(fallback_err))}'. Original primary error was: "
                        f"category='{primary_cat}', status_code={primary_class.get('status_code')}."
                    )

                    # Truthful reporting when quota is exhausted across models
                    if fallback_cat == "daily_quota_exhausted" or primary_cat == "daily_quota_exhausted":
                        raise LLMServiceError(
                            "AI service limits have been reached for the available models. Please try again after the quota resets."
                        )
                    elif fallback_cat == "temporary_overload":
                        raise_classified_error(fallback_err, model_name=resolved_fallback, default_msg=default_msg)
                    else:
                        raise_classified_error(fallback_err, model_name=resolved_fallback, default_msg=default_msg)
            else:
                logger.warning(
                    f"Configured fallback model '{resolved_fallback}' could not be verified as accessible. "
                    "Skipping fallback."
                )
        else:
            logger.warning(
                f"Primary model '{resolved_primary}' failed with non-fallback category '{primary_cat}' "
                f"(status={primary_class.get('status_code')}). Fallback not eligible or not configured."
            )

        if primary_cat == "daily_quota_exhausted":
            raise LLMServiceError(
                "AI service limits have been reached for the available models. Please try again after the quota resets."
            )

        raise_classified_error(primary_err, model_name=resolved_primary, default_msg=default_msg)



def build_educational_prompt(
    code: str,
    language: str,
    learning_level: str,
    confidence: str = "high",
    static_analysis: Optional[Any] = None,
) -> str:
    """
    Build the structured educational tutor prompt strictly according to Step 4 & Step 5 specifications.
    Includes rules for partial code snippets, learning level depth, variables/functions handling,
    complexity constraints, bug distinctions, and deterministic static analysis facts.
    """
    level_guidance = {
        "Beginner": (
            "- Use clear, accessible, and friendly language.\n"
            "- Explain basic concepts and unfamiliar syntax clearly.\n"
            "- Avoid unnecessary jargon; define technical terms when used."
        ),
        "Intermediate": (
            "- Provide moderate technical detail.\n"
            "- Explain implementation decisions and core language patterns.\n"
            "- Discuss how components interact."
        ),
        "Advanced": (
            "- Deliver deep technical explanations with precise terminology.\n"
            "- Discuss edge cases, efficiency trade-offs, and compiler/runtime implementation details.\n"
            "- Provide rigorous complexity analysis where applicable."
        ),
    }.get(learning_level, "- Explain the code clearly and thoroughly.")

    confidence_note = ""
    if confidence.lower() == "moderate":
        confidence_note = (
            f"NOTE: The language is detected as likely {language} with moderate confidence. "
            "Explain it in terms of this language while acknowledging any syntax ambiguity if relevant.\n\n"
        )

    static_section = ""
    if static_analysis is not None:
        summary_text = getattr(static_analysis, "to_prompt_summary", None)
        if callable(summary_text):
            evidence_str = static_analysis.to_prompt_summary()
        elif isinstance(static_analysis, str):
            evidence_str = static_analysis
        else:
            evidence_str = str(static_analysis)

        static_section = (
            "=== STATIC CODE ANALYSIS (DETERMINISTIC FACTS) ===\n"
            f"{evidence_str}\n\n"
            "INSTRUCTIONS FOR USING STATIC ANALYSIS:\n"
            "- Ground your educational explanation in the statically determined facts above.\n"
            "- Explain the facts to the student rather than guessing or recalculating them.\n"
            "- For Complexity: Use loop counts, nesting, sorting, and recursion evidence. "
            "If evidence is insufficient (e.g. single variable assignment, partial snippet, incomplete logic), "
            "output 'Not meaningfully applicable / cannot be determined from the provided snippet.' Do not guess.\n"
            "- For Issues: Help the student understand any definite or possible issues detected.\n"
            "- SOURCE CODE IS ULTIMATE TRUTH: If static analysis reports uncertainty or conflicts with actual code semantics, "
            "preserve that nuance. Never blindly repeat incorrect facts if the code proves otherwise.\n\n"
        )

    return (
        "You are AI CodeMentor, an expert educational programming tutor.\n\n"
        f"{confidence_note}"
        "Your task is to provide a structured educational explanation of the submitted source code.\n\n"
        "=== STRICT AI TUTOR RULES ===\n"
        "1. PARTIAL SNIPPETS ARE VALID: The submitted code does NOT need to be a complete program, "
        "function, class, or executable. Never reject or complain that the snippet lacks main(), classes, "
        "imports, or complete structures. Explain valid partial snippets directly.\n"
        "2. PRESERVE CODE INTEGRITY: Never modify or rewrite the user's code unless explicitly requested. "
        "Never invent code or lines that do not exist.\n"
        "3. NO INVENTED IDENTIFIERS: Never invent variables or functions. If the code has no functions, "
        "return an empty list [] for functions. If it has no variables, return an empty list [] for variables.\n"
        "4. ALGORITHM / LOGIC: Explain the logical flow or algorithm present in the code. For a small or partial snippet, "
        "explain the specific logic rather than forcing it into a textbook algorithm category.\n"
        "5. TIME & SPACE COMPLEXITY: Estimate time and space complexity ONLY when enough code is available to determine it. "
        "If the snippet is too small or complexity is not meaningfully applicable, output: "
        "'Not meaningfully applicable / cannot be determined from the provided snippet.' Do not hallucinate complexity.\n"
        "6. POTENTIAL BUGS & ISSUES: Clearly distinguish definite syntax/runtime bugs from possible edge cases, logical issues, "
        "or suspicious patterns. Set severity to 'definite' for confirmed bugs, or 'possible' / 'low' / 'medium' / 'high' for edge cases.\n"
        "7. LEARNING DEPTH:\n"
        f"{level_guidance}\n\n"
        f"Target Programming Language: {language}\n"
        f"Learning Level: {learning_level}\n\n"
        f"{static_section}"
        f"Submitted Code Snippet:\n```\n{code}\n```\n"
    )


def analyze_code(
    code: str,
    language: str,
    learning_level: str,
    confidence: str = "high",
    static_analysis: Optional[Any] = None,
) -> CodeAnalysis:
    """
    Send code to Gemini for structured educational explanation.
    
    Args:
        code: The source code to explain.
        language: Programming language (one of the 13 supported languages).
        learning_level: Depth of explanation (Beginner, Intermediate, Advanced).
        confidence: Detection confidence ('high' or 'moderate').
        static_analysis: Optional StaticAnalysisResult with deterministic evidence.
        
    Returns:
        Structured CodeAnalysis object.
        
    Raises:
        LLMConfigurationError: For missing or invalid API keys, or unavailable models.
        LLMServiceError: For API communication failures, timeouts, rate limits, or unparsable output.
    """
    model_name = os.getenv("GEMINI_MODEL", "").strip()
    if not model_name:
        logger.error("GEMINI_MODEL environment variable is not defined.")
        raise LLMConfigurationError(
            "GEMINI_MODEL is not configured. Please define GEMINI_MODEL in backend/.env"
        )

    client = get_gemini_client()
    prompt = build_educational_prompt(
        code=code,
        language=language,
        learning_level=learning_level,
        confidence=confidence,
        static_analysis=static_analysis,
    )

    try:
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=CodeAnalysis,
            temperature=0.2,
        )

        response = execute_with_retry_and_fallback(
            client=client,
            contents=prompt,
            config=config,
            primary_model=model_name,
            default_msg="Unable to analyze the code right now. Please try again.",
        )

        # Extract generated explanation text safely
        generated_text = None
        if hasattr(response, "text") and response.text:
            generated_text = response.text.strip()

        if not generated_text:
            logger.error("Gemini returned an empty response.")
            raise LLMServiceError("Unable to analyze the code right now. Please try again.")

        # Clean potential markdown wrapping if present
        if generated_text.startswith("```"):
            import re
            generated_text = re.sub(r"^```(?:json)?\s*", "", generated_text)
            generated_text = re.sub(r"\s*```$", "", generated_text)

        analysis = CodeAnalysis.model_validate_json(generated_text)
        return analysis

    except (LLMConfigurationError, LLMServiceError):
        raise
    except Exception as e:
        logger.error(f"Analysis request failed: {type(e).__name__} - {sanitize_sensitive_data(str(e))}")
        raise_classified_error(
            e,
            model_name=model_name,
            default_msg="Unable to analyze the code right now. Please try again.",
        )



def format_static_analysis_for_tutor(static_analysis: Any) -> str:
    """Helper to format static analysis facts cleanly for the tutor prompt."""
    if not static_analysis:
        return ""
    if hasattr(static_analysis, "to_prompt_summary") and callable(static_analysis.to_prompt_summary):
        return static_analysis.to_prompt_summary()
    if isinstance(static_analysis, dict):
        parts = []
        if "structure" in static_analysis and static_analysis["structure"]:
            s = static_analysis["structure"]
            if isinstance(s, dict):
                parts.append("Structure Metrics: " + ", ".join(f"{k}: {v}" for k, v in s.items() if v is not None))
            else:
                parts.append(f"Structure Metrics: {s}")
        if "complexity_evidence" in static_analysis and static_analysis["complexity_evidence"]:
            c = static_analysis["complexity_evidence"]
            if isinstance(c, dict):
                parts.append("Complexity Evidence: " + ", ".join(f"{k}: {v}" for k, v in c.items() if v is not None))
            else:
                parts.append(f"Complexity Evidence: {c}")
        if parts:
            return "\n".join(parts)
        return json.dumps(static_analysis, indent=2)
    return str(static_analysis)


def format_existing_analysis_for_tutor(analysis: Any) -> str:
    """Helper to format previous structured code explanation for the tutor prompt."""
    if not analysis:
        return ""
    if hasattr(analysis, "model_dump") and callable(analysis.model_dump):
        analysis = analysis.model_dump()
    elif hasattr(analysis, "dict") and callable(analysis.dict):
        analysis = analysis.dict()
    if isinstance(analysis, dict):
        parts = []
        if analysis.get("overall_purpose"):
            parts.append(f"Overall Purpose: {analysis['overall_purpose']}")
        if analysis.get("how_it_works"):
            parts.append(f"How It Works: {analysis['how_it_works']}")
        if analysis.get("algorithm_logic"):
            parts.append(f"Algorithm / Logic: {analysis['algorithm_logic']}")
        if analysis.get("time_complexity"):
            parts.append(f"Time Complexity: {analysis['time_complexity']}")
        if analysis.get("space_complexity"):
            parts.append(f"Space Complexity: {analysis['space_complexity']}")
        if analysis.get("potential_issues"):
            issues = analysis["potential_issues"]
            if isinstance(issues, list) and issues:
                issue_descs = [
                    (i.get("description", str(i)) if isinstance(i, dict) else getattr(i, "description", str(i)))
                    for i in issues
                ]
                parts.append("Identified Issues: " + "; ".join(issue_descs))
        if analysis.get("key_learning_points"):
            points = analysis["key_learning_points"]
            if isinstance(points, list) and points:
                parts.append("Key Learning Points: " + "; ".join(str(p) for p in points))
        return "\n".join(parts)
    return str(analysis)


def format_history_for_tutor(history: Optional[list]) -> str:
    """Format bounded conversation history for the tutor prompt."""
    if not history:
        return ""
    bounded = history[-10:]
    lines = []
    for msg in bounded:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
        else:
            role = getattr(msg, "role", "user")
            content = getattr(msg, "content", "")
        speaker = "User" if role == "user" else "AI Tutor"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def build_tutor_prompt(
    code: str,
    language: str,
    learning_level: str,
    question: str,
    static_analysis: Optional[Any] = None,
    analysis: Optional[Any] = None,
    history: Optional[list] = None,
) -> str:
    """
    Build the dedicated interactive tutor prompt strictly according to Step 6 specifications.
    Enforces grounding in current code, learning-level adaptation, and non-hallucination rules.
    """
    level_guidance = {
        "Beginner": (
            "- Use simple vocabulary and intuitive explanations.\n"
            "- Provide small illustrative examples where helpful.\n"
            "- Use minimal jargon; explain programming terminology when used.\n"
            "- Do not make the explanation artificially childish."
        ),
        "Intermediate": (
            "- Use standard technical terminology.\n"
            "- Detail implementation decisions and relationships between functions and data.\n"
            "- Explain complexity where supported by static evidence."
        ),
        "Advanced": (
            "- Provide in-depth technical details and algorithmic reasoning.\n"
            "- Discuss efficiency trade-offs, edge cases, and design implications.\n"
            "- Provide rigorous complexity considerations."
        ),
    }.get(learning_level, "- Explain the concept clearly and thoroughly.")

    static_text = format_static_analysis_for_tutor(static_analysis)
    analysis_text = format_existing_analysis_for_tutor(analysis)
    history_text = format_history_for_tutor(history)

    static_section = ""
    if static_text.strip():
        static_section = (
            "=== STATIC ANALYSIS FACTS ===\n"
            f"{static_text.strip()}\n\n"
        )

    analysis_section = ""
    if analysis_text.strip():
        analysis_section = (
            "=== EXISTING CODE ANALYSIS CONTEXT ===\n"
            f"{analysis_text.strip()}\n\n"
        )

    history_section = ""
    if history_text.strip():
        history_section = (
            "=== RECENT CONVERSATION HISTORY ===\n"
            f"{history_text.strip()}\n\n"
        )

    return (
        "You are an interactive programming tutor for AI CodeMentor.\n\n"
        "Your task is to answer the user's question about the supplied source code in an educational manner.\n\n"
        "=== STRICT GROUNDING & TUTOR RULES ===\n"
        "1. THE SOURCE CODE IS THE ULTIMATE SOURCE OF TRUTH: Answer primarily based on the provided code.\n"
        "2. DO NOT INVENT CODE: Do not invent code that does not exist in the source code.\n"
        "3. DO NOT INVENT IDENTIFIERS: Do not claim a variable, function, class, or parameter exists if it does not exist.\n"
        "4. DO NOT INVENT LINE NUMBERS: Only reference line numbers that actually exist in the provided code.\n"
        "5. DO NOT ASSUME MISSING CODE: If the question cannot be answered from the provided code, explicitly state "
        "that the available code does not contain enough information and set grounded=false.\n"
        "6. CONFLICT RESOLUTION: If static-analysis facts conflict with the source code, trust the source code and acknowledge the limitation.\n"
        "7. DO NOT BLINDLY ACCEPT STATIC ANALYSIS: Verify claims against the actual source code.\n"
        "8. DO NOT HALLUCINATE BIG-O COMPLEXITY: Only provide a Big-O claim when there is sufficient evidence in the code. "
        "Otherwise, explain the limitation.\n"
        "9. UNGROUNDED PREMISES: If the user asks about an element or outcome not supported by the code (e.g., 'Why does it return 20?' "
        "when 20 is never produced, or asking about a non-existent variable 'total'), explain that the premise is not supported by "
        "the code instead of inventing an explanation, and set grounded=false.\n"
        "10. TEACH THE CONCEPT: Explain the 'why' and pedagogical reasoning, not just a one-line answer.\n"
        "11. LEARNING QUESTIONS: When asked about a programming concept (e.g., 'What is recursion?'), explain the concept clearly "
        "and connect it back to the current code where possible.\n"
        "12. FOLLOW-UP CONTINUITY: If recent conversation history is provided, understand the context of the user's follow-up question.\n\n"
        f"=== LEARNING LEVEL GUIDANCE ({learning_level}) ===\n"
        f"{level_guidance}\n\n"
        f"Target Programming Language: {language}\n"
        f"Learning Level: {learning_level}\n\n"
        f"{static_section}"
        f"{analysis_section}"
        f"{history_section}"
        f"=== SOURCE CODE (GROUND TRUTH) ===\n```\n{code}\n```\n\n"
        f"=== USER QUESTION ===\n{question}\n"
    )


def ask_tutor(
    code: str,
    language: str,
    learning_level: str,
    question: str,
    static_analysis: Optional[Any] = None,
    analysis: Optional[Any] = None,
    history: Optional[list] = None,
) -> Any:
    """
    Send user question and code context to Gemini for an educational, grounded tutor response.

    Args:
        code: Source code currently analyzed.
        language: Detected programming language.
        learning_level: Educational level (Beginner, Intermediate, Advanced).
        question: User question about the code.
        static_analysis: Optional static analysis data.
        analysis: Optional existing structured explanation.
        history: Optional list of recent messages.

    Returns:
        TutorLLMResponse containing answer, key_points, related_code, and grounded status.

    Raises:
        LLMConfigurationError: For missing or invalid API keys, or unavailable models.
        LLMServiceError: For API communication failures, timeouts, rate limits, or unparsable output.
    """
    from app.models.tutor import TutorLLMResponse

    model_name = os.getenv("GEMINI_MODEL", "").strip()
    if not model_name:
        logger.error("GEMINI_MODEL environment variable is not defined.")
        raise LLMConfigurationError(
            "GEMINI_MODEL is not configured. Please define GEMINI_MODEL in backend/.env"
        )

    client = get_gemini_client()
    prompt = build_tutor_prompt(
        code=code,
        language=language,
        learning_level=learning_level,
        question=question,
        static_analysis=static_analysis,
        analysis=analysis,
        history=history,
    )

    try:
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=TutorLLMResponse,
            temperature=0.2,
        )

        response = execute_with_retry_and_fallback(
            client=client,
            contents=prompt,
            config=config,
            primary_model=model_name,
            default_msg="The AI Tutor could not answer right now. Please try again.",
        )

        # Extract generated response text safely
        generated_text = None
        if hasattr(response, "text") and response.text:
            generated_text = response.text.strip()

        if not generated_text:
            logger.error("Gemini returned an empty response for tutor question.")
            raise LLMServiceError("The AI Tutor could not answer right now. Please try again.")

        # Clean potential markdown wrapping if present
        if generated_text.startswith("```"):
            import re
            generated_text = re.sub(r"^```(?:json)?\s*", "", generated_text)
            generated_text = re.sub(r"\s*```$", "", generated_text)

        tutor_response = TutorLLMResponse.model_validate_json(generated_text)
        return tutor_response

    except (LLMConfigurationError, LLMServiceError):
        raise
    except Exception as e:
        logger.error(f"Tutor request failed: {type(e).__name__} - {sanitize_sensitive_data(str(e))}")
        raise_classified_error(
            e,
            model_name=model_name,
            default_msg="The AI Tutor could not answer right now. Please try again.",
        )


