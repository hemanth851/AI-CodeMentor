"""
Unit and Integration Tests for Gemini 503 Resilience and Fallback Model Handling.

Covers all required test categories:
1. Primary model succeeds immediately (0 retries).
2. Primary model returns 503, then succeeds on retry (exponential backoff & jitter).
3. Primary model fails with 503 and verified fallback model succeeds.
4. Both primary and fallback models unavailable (returns user-friendly 503 overload message).
5. 429 rate limit is handled separately and not retried with 503 retry policy.
6. Permanent errors (authentication, billing/quota, validation) are not repeatedly retried.
7. API keys and sensitive credentials are never exposed in errors or responses.
8. Retry-After header is respected and bounded to prevent unbounded waiting.
9. Unverified fallback model is not enabled.
10. End-to-end integration across Analyze, Tutor, and Quiz endpoints.
"""

import json
import os
import unittest
from unittest.mock import MagicMock, patch, call
from starlette.testclient import TestClient

from app.main import app
from app.services.llm_service import (
    execute_with_retry_and_fallback,
    classify_error,
    extract_retry_after,
    calculate_retry_delay,
    is_model_verified_accessible,
    clear_model_verification_cache,
    sanitize_sensitive_data,
    raise_classified_error,
    get_gemini_client,
    LLMConfigurationError,
    LLMServiceError,
)
from app.models.analysis import CodeAnalysis
from app.models.tutor import TutorLLMResponse
from app.models.quiz import QuizLLMResponse
from app.services.detector import detect_language


class TestGeminiResilience(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        clear_model_verification_cache()
        # Fast retry backoff for testing speed
        self.env_patcher = patch.dict(
            "os.environ",
            {
                "GEMINI_API_KEY": "AIzaSyFakeSecretKeyForTesting1234567890",
                "GEMINI_MODEL": "gemini-3.6-flash",
                "GEMINI_FALLBACK_MODEL": "gemini-3.5-flash-lite",
                "GEMINI_RETRY_INITIAL_DELAY": "0.01",
            },
        )
        self.env_patcher.start()

    def tearDown(self):
        self.env_patcher.stop()
        clear_model_verification_cache()

    # -----------------------------------------------------------------
    # 1. Primary Model Succeeds
    # -----------------------------------------------------------------
    def test_01_primary_model_succeeds(self):
        """Primary model succeeds immediately on first attempt without retrying."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = "Hello world"
        mock_client.models.generate_content.return_value = mock_resp

        mock_sleep = MagicMock()
        result = execute_with_retry_and_fallback(
            client=mock_client,
            contents="Say hi",
            config=None,
            primary_model="gemini-3.6-flash",
            fallback_model="gemini-3.5-flash-lite",
            sleep_fn=mock_sleep,
        )

        self.assertEqual(result, mock_resp)
        self.assertEqual(mock_client.models.generate_content.call_count, 1)
        mock_sleep.assert_not_called()

    # -----------------------------------------------------------------
    # 2. Primary Returns 503, Then Succeeds
    # -----------------------------------------------------------------
    def test_02_primary_returns_503_then_succeeds(self):
        """Primary returns 503 once, sleeps with backoff, and succeeds on attempt 2."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE. This model is currently experiencing high demand.")
        mock_resp = MagicMock()
        mock_resp.text = "Success on attempt 2"
        mock_client.models.generate_content.side_effect = [err_503, mock_resp]

        mock_sleep = MagicMock()
        result = execute_with_retry_and_fallback(
            client=mock_client,
            contents="Test 503 retry",
            config=None,
            primary_model="gemini-3.6-flash",
            fallback_model="gemini-3.5-flash-lite",
            sleep_fn=mock_sleep,
        )

        self.assertEqual(result, mock_resp)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        # Should have slept once between attempt 1 and attempt 2
        self.assertEqual(mock_sleep.call_count, 1)
        self.assertGreater(mock_sleep.call_args[0][0], 0.0)

    # -----------------------------------------------------------------
    # 3. Primary Fails (503 Exhausted) and Verified Fallback Succeeds
    # -----------------------------------------------------------------
    def test_03_primary_fails_and_verified_fallback_succeeds(self):
        """Primary fails 3 attempts (initial + 2 retries) with 503, verified fallback succeeds."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE. This model is currently experiencing high demand.")
        mock_fallback_resp = MagicMock()
        mock_fallback_resp.text = "Fallback success"

        # 3 failures for primary, then fallback succeeds
        mock_client.models.generate_content.side_effect = [
            err_503,
            err_503,
            err_503,
            mock_fallback_resp,
        ]
        # models.get verifies fallback model accessibility
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")

        mock_sleep = MagicMock()
        result = execute_with_retry_and_fallback(
            client=mock_client,
            contents="Analyze code",
            config=None,
            primary_model="gemini-3.6-flash",
            fallback_model="gemini-3.5-flash-lite",
            sleep_fn=mock_sleep,
        )

        self.assertEqual(result, mock_fallback_resp)
        # Total 4 calls: 3 for primary (initial + 2 retries) + 1 for fallback
        self.assertEqual(mock_client.models.generate_content.call_count, 4)
        mock_client.models.get.assert_called_with(model="gemini-3.5-flash-lite")
        # Slept twice during primary retries
        self.assertEqual(mock_sleep.call_count, 2)

    # -----------------------------------------------------------------
    # 4. Both Models Unavailable
    # -----------------------------------------------------------------
    def test_04_both_models_unavailable(self):
        """Both primary and fallback models return 503; raises user-friendly LLMServiceError."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE. Spikes in demand are usually temporary.")
        mock_client.models.generate_content.side_effect = err_503
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")

        mock_sleep = MagicMock()
        with self.assertRaises(LLMServiceError) as ctx:
            execute_with_retry_and_fallback(
                client=mock_client,
                contents="Analyze code",
                config=None,
                primary_model="gemini-3.6-flash",
                fallback_model="gemini-3.5-flash-lite",
                sleep_fn=mock_sleep,
            )

        self.assertIn("experiencing high demand", str(ctx.exception).lower())
        # 3 calls on primary + 3 calls on fallback = 6 calls total
        self.assertEqual(mock_client.models.generate_content.call_count, 6)

    # -----------------------------------------------------------------
    # 5. 429 Rate Limit Handled Separately (Not Retried with 503 Policy)
    # -----------------------------------------------------------------
    def test_05_429_handled_separately(self):
        """429 rate limit is NOT retried under 503 retry policy and fails immediately."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded")

        mock_sleep = MagicMock()
        with self.assertRaises(LLMServiceError) as ctx:
            execute_with_retry_and_fallback(
                client=mock_client,
                contents="Quick question",
                config=None,
                primary_model="gemini-3.6-flash",
                fallback_model="gemini-3.5-flash-lite",
                sleep_fn=mock_sleep,
            )

        self.assertIn("rate limits", str(ctx.exception).lower())
        # Exactly 1 call: no retries attempted
        self.assertEqual(mock_client.models.generate_content.call_count, 1)
        mock_sleep.assert_not_called()

    # -----------------------------------------------------------------
    # 6. Permanent Errors Not Repeatedly Retried
    # -----------------------------------------------------------------
    def test_06_authentication_error_not_retried(self):
        """Authentication error (401/403) aborts immediately without retrying."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("401 UNAUTHENTICATED: Invalid API key")

        mock_sleep = MagicMock()
        with self.assertRaises(LLMConfigurationError) as ctx:
            execute_with_retry_and_fallback(
                client=mock_client,
                contents="Prompt",
                config=None,
                primary_model="gemini-3.6-flash",
                sleep_fn=mock_sleep,
            )

        self.assertIn("api key is not configured or invalid", str(ctx.exception).lower())
        self.assertEqual(mock_client.models.generate_content.call_count, 1)
        mock_sleep.assert_not_called()

    def test_06_permanent_quota_billing_not_retried(self):
        """Billing / permanent quota failure aborts immediately without retrying."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("Billing account disabled or quota exceeded permanently")

        mock_sleep = MagicMock()
        with self.assertRaises(LLMServiceError) as ctx:
            execute_with_retry_and_fallback(
                client=mock_client,
                contents="Prompt",
                config=None,
                primary_model="gemini-3.6-flash",
                sleep_fn=mock_sleep,
            )

        self.assertIn("billing account is disabled", str(ctx.exception).lower())
        self.assertEqual(mock_client.models.generate_content.call_count, 1)
        mock_sleep.assert_not_called()

    # -----------------------------------------------------------------
    # 7. API Key is Never Exposed in Errors, Messages, or Logs
    # -----------------------------------------------------------------
    def test_07_api_key_is_never_exposed(self):
        """Any error containing sensitive API keys or authorization headers is redacted."""
        secret_key = "AIzaSyFakeSecretKeyForTesting1234567890"
        leak_msg = f"Failed calling https://generativelanguage.googleapis.com/v1beta/models?key={secret_key}: 503 UNAVAILABLE"
        clean = sanitize_sensitive_data(leak_msg)
        self.assertNotIn(secret_key, clean)
        self.assertIn("[REDACTED", clean)

        # Test raise_classified_error does not leak key
        err = Exception(f"500 Internal error with Bearer AQ.secret_token_12345678901234567890 and key={secret_key}")
        with self.assertRaises(LLMServiceError) as ctx:
            raise_classified_error(err, model_name="gemini-3.6-flash")
        self.assertNotIn(secret_key, str(ctx.exception))
        self.assertNotIn("AQ.secret_token", str(ctx.exception))

    # -----------------------------------------------------------------
    # 8. Retry-After Header Respected and Bounded
    # -----------------------------------------------------------------
    def test_08_respect_retry_after_header(self):
        """Retry-After header from response is extracted and used as delay."""
        class MockResponse:
            headers = {"retry-after": "3.5"}

        err_with_header = Exception("503 UNAVAILABLE")
        err_with_header.response = MockResponse()

        delay = extract_retry_after(err_with_header)
        self.assertEqual(delay, 3.5)

        calculated = calculate_retry_delay(0, err_with_header)
        self.assertEqual(calculated, 3.5)

    def test_08_prevent_unbounded_waiting(self):
        """Unreasonably large Retry-After values are capped to MAX_BACKOFF_SECONDS (10.0s)."""
        class MockResponse:
            headers = {"retry-after": "99999"}

        err_huge = Exception("503 UNAVAILABLE")
        err_huge.response = MockResponse()

        delay = extract_retry_after(err_huge)
        self.assertEqual(delay, 10.0)

    # -----------------------------------------------------------------
    # 9. Unverified Fallback Model is Not Enabled
    # -----------------------------------------------------------------
    def test_09_unverified_fallback_model_is_skipped(self):
        """If fallback model verification fails (e.g. 404), fallback is not attempted."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE. Spikes in demand are usually temporary.")
        mock_client.models.generate_content.side_effect = err_503
        # models.get raises 404 for unverified fallback model
        mock_client.models.get.side_effect = Exception("404 Model not found: models/unsupported-fallback")

        mock_sleep = MagicMock()
        with self.assertRaises(LLMServiceError) as ctx:
            execute_with_retry_and_fallback(
                client=mock_client,
                contents="Analyze",
                config=None,
                primary_model="gemini-3.6-flash",
                fallback_model="unsupported-fallback",
                sleep_fn=mock_sleep,
            )

        # Fallback was skipped because verification failed: only 3 calls on primary
        self.assertEqual(mock_client.models.generate_content.call_count, 3)
        self.assertIn("experiencing high demand", str(ctx.exception).lower())

    # -----------------------------------------------------------------
    # 10. Fallback When Primary Model is 404 Not Found
    # -----------------------------------------------------------------
    def test_10_primary_model_not_found_falls_back(self):
        """If primary model is 404 Not Found, immediately fall back to verified fallback model."""
        mock_client = MagicMock()
        err_404 = Exception("404 Model not found: invalid-primary")
        mock_fallback_resp = MagicMock()
        mock_fallback_resp.text = "Fallback output"

        mock_client.models.generate_content.side_effect = [err_404, mock_fallback_resp]
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")

        mock_sleep = MagicMock()
        result = execute_with_retry_and_fallback(
            client=mock_client,
            contents="Analyze",
            config=None,
            primary_model="invalid-primary",
            fallback_model="gemini-3.5-flash-lite",
            sleep_fn=mock_sleep,
        )

        self.assertEqual(result, mock_fallback_resp)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        mock_sleep.assert_not_called()

    # -----------------------------------------------------------------
    # 11. End-to-End API Integration with 503 Fallback
    # -----------------------------------------------------------------
    @patch("app.services.llm_service.get_gemini_client")
    def test_11_analyze_endpoint_with_503_fallback(self, mock_get_client):
        """Analyze API endpoint gracefully recovers from primary 503 using verified fallback."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE. Spikes in demand are usually temporary.")

        mock_analysis_data = {
            "overall_purpose": "Calculates sum of numbers",
            "how_it_works": "Loops through numbers",
            "line_by_line": [{"line": 1, "code": "def add(a, b): return a + b", "explanation": "Adds numbers"}],
            "variables": [],
            "functions": [],
            "algorithm_logic": "Simple arithmetic",
            "time_complexity": "O(1)",
            "space_complexity": "O(1)",
            "potential_issues": [],
            "key_learning_points": ["Addition operator"],
        }
        mock_success_resp = MagicMock()
        mock_success_resp.text = json.dumps(mock_analysis_data)

        # Primary 503 (3 attempts), then fallback succeeds
        mock_client.models.generate_content.side_effect = [
            err_503,
            err_503,
            err_503,
            mock_success_resp,
        ]
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/analyze",
            json={
                "code": "def add(a, b):\n    return a + b",
                "learning_level": "Beginner",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["overall_purpose"], "Calculates sum of numbers")

    @patch("app.services.llm_service.get_gemini_client")
    def test_12_tutor_endpoint_with_503_fallback(self, mock_get_client):
        """Tutor API endpoint gracefully recovers from primary 503 using verified fallback."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE. Spikes in demand are usually temporary.")

        mock_tutor_data = {
            "answer": "The function returns the sum of parameters a and b.",
            "key_points": ["Uses the + operator"],
            "related_code": "return a + b",
            "grounded": True,
        }
        mock_success_resp = MagicMock()
        mock_success_resp.text = json.dumps(mock_tutor_data)

        mock_client.models.generate_content.side_effect = [
            err_503,
            err_503,
            err_503,
            mock_success_resp,
        ]
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/tutor",
            json={
                "code": "def add(a, b):\n    return a + b",
                "language": "Python",
                "learning_level": "Beginner",
                "question": "What does this do?",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["grounded"])
        self.assertIn("sum of parameters", data["answer"])

    @patch("app.services.quiz_service.get_gemini_client")
    def test_13_quiz_endpoint_with_503_fallback(self, mock_get_client):
        """Quiz generation API endpoint gracefully recovers from primary 503 using verified fallback."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE. Spikes in demand are usually temporary.")

        valid_quiz = {
            "questions": [
                {
                    "question": "What is the return value of add(2, 3)?",
                    "options": ["5", "6", "1", "None"],
                    "correct_answer_index": 0,
                    "explanation": "Adding 2 and 3 produces 5 according to standard addition arithmetic.",
                    "category": "Output Prediction",
                    "difficulty": "Beginner",
                },
                {
                    "question": "Which operator is used to calculate the result?",
                    "options": ["+", "-", "*", "/"],
                    "correct_answer_index": 0,
                    "explanation": "The addition operator + is used in the return statement.",
                    "category": "Syntax Semantics",
                    "difficulty": "Beginner",
                },
                {
                    "question": "What parameters does the function accept?",
                    "options": ["a and b", "x and y", "only numbers", "no parameters"],
                    "correct_answer_index": 0,
                    "explanation": "The function definition states def add(a, b).",
                    "category": "Variable Role",
                    "difficulty": "Beginner",
                },
                {
                    "question": "What is the time complexity of add?",
                    "options": ["O(1)", "O(n)", "O(log n)", "O(n^2)"],
                    "correct_answer_index": 0,
                    "explanation": "Addition executes in constant time O(1).",
                    "category": "Complexity Analysis",
                    "difficulty": "Beginner",
                },
                {
                    "question": "What happens if add is called with non-numeric inputs like strings?",
                    "options": ["Concatenates strings", "Always throws error", "Converts to numbers", "Returns None"],
                    "correct_answer_index": 0,
                    "explanation": "In Python the + operator concatenates strings.",
                    "category": "Edge Cases",
                    "difficulty": "Beginner",
                },
            ]
        }
        mock_success_resp = MagicMock()
        mock_success_resp.text = json.dumps(valid_quiz)

        mock_client.models.generate_content.side_effect = [
            err_503,
            err_503,
            err_503,
            mock_success_resp,
        ]
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/quiz/generate",
            json={
                "code": "def add(a, b):\n    return a + b\n\nresult = add(10, 20)\nprint(result)",
                "language": "Python",
                "learning_level": "Beginner",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["questions"]), 5)
        self.assertIn("quiz_token", data)



    # -----------------------------------------------------------------
    # 14. Primary 503 -> Fallback 503
    # -----------------------------------------------------------------
    @patch("app.services.llm_service.get_gemini_client")
    def test_14_primary_503_fallback_503_preserves_error(self, mock_get_client):
        """When both primary and fallback return 503, preserve high demand error without quota misclassification."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE. Spikes in demand are usually temporary.")
        mock_client.models.generate_content.side_effect = err_503
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/tutor",
            json={
                "code": "print('hello')",
                "language": "Python",
                "learning_level": "Beginner",
                "question": "What does this print?",
            },
        )

        self.assertEqual(response.status_code, 502)
        detail = response.json().get("detail", "")
        self.assertIn("experiencing high demand", detail.lower())
        self.assertNotIn("quota", detail.lower())
        # 3 calls on primary + 3 calls on fallback = 6 calls
        self.assertEqual(mock_client.models.generate_content.call_count, 6)

    # -----------------------------------------------------------------
    # 15. Primary 429 -> Correct Handling (No Fallback, No Quota Label)
    # -----------------------------------------------------------------
    @patch("app.services.llm_service.get_gemini_client")
    def test_15_primary_429_tutor_endpoint(self, mock_get_client):
        """429 RESOURCE_EXHAUSTED produces rate limit message without retrying or calling fallback."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "429 RESOURCE_EXHAUSTED: You exceeded your current quota, please check your plan and billing details."
        )
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/tutor",
            json={
                "code": "print('hello')",
                "language": "Python",
                "learning_level": "Beginner",
                "question": "What does this print?",
            },
        )

        self.assertEqual(response.status_code, 502)
        detail = response.json().get("detail", "")
        self.assertIn("rate limits", detail.lower())
        self.assertNotIn("quota has been exceeded or billing is required", detail.lower())
        # Exactly 1 attempt made: no 503 retry, no fallback
        self.assertEqual(mock_client.models.generate_content.call_count, 1)

    @patch("app.services.quiz_service.get_gemini_client")
    def test_15_primary_429_quiz_endpoint(self, mock_get_client):
        """Quiz endpoint receiving 429 produces rate limit message with no fallback attempts."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "429 RESOURCE_EXHAUSTED: Rate limit exceeded for default project."
        )
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/quiz/generate",
            json={
                "code": "def double(x):\n    return x * 2\n\nval = double(5)",
                "language": "Python",
                "learning_level": "Beginner",
            },
        )

        self.assertEqual(response.status_code, 502)
        detail = response.json().get("detail", "")
        self.assertIn("rate limits", detail.lower())
        self.assertEqual(mock_client.models.generate_content.call_count, 1)

    # -----------------------------------------------------------------
    # 16. Primary 403 -> Correct Permission / Billing Handling
    # -----------------------------------------------------------------
    @patch("app.services.llm_service.get_gemini_client")
    def test_16_primary_403_permission_billing_endpoint(self, mock_get_client):
        """403 PERMISSION_DENIED billing account disabled produces distinct billing failure message."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "403 PERMISSION_DENIED: Billing account disabled for project."
        )
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/tutor",
            json={
                "code": "print('hello')",
                "language": "Python",
                "learning_level": "Beginner",
                "question": "What does this print?",
            },
        )

        self.assertEqual(response.status_code, 502)
        detail = response.json().get("detail", "")
        self.assertIn("billing account is disabled", detail.lower())
        self.assertEqual(mock_client.models.generate_content.call_count, 1)

    # -----------------------------------------------------------------
    # 17. Quiz Secondary Generation / Validation Call Handling
    # -----------------------------------------------------------------
    @patch("app.services.quiz_service.get_gemini_client")
    def test_17_quiz_secondary_generation_succeeds_after_validation_error(self, mock_get_client):
        """Quiz attempt 1 produces duplicate options, triggering revision attempt 2 which succeeds."""
        mock_client = MagicMock()
        invalid_quiz_json = {
            "questions": [
                {
                    "question": "What does add(2, 3) return?",
                    "options": ["5", "5", "1", "None"],
                    "correct_answer_index": 0,
                    "explanation": "Adding 2 and 3 produces 5.",
                    "category": "Output Prediction",
                    "difficulty": "Beginner",
                },
                {
                    "question": "Which operator is used?",
                    "options": ["+", "-", "*", "/"],
                    "correct_answer_index": 0,
                    "explanation": "The addition operator + is used.",
                    "category": "Syntax Semantics",
                    "difficulty": "Beginner",
                },
                {
                    "question": "What parameters are taken?",
                    "options": ["a and b", "x and y", "nums", "none"],
                    "correct_answer_index": 0,
                    "explanation": "Parameters are a and b.",
                    "category": "Variable Role",
                    "difficulty": "Beginner",
                },
                {
                    "question": "What is the complexity?",
                    "options": ["O(1)", "O(n)", "O(log n)", "O(n^2)"],
                    "correct_answer_index": 0,
                    "explanation": "Complexity is O(1).",
                    "category": "Complexity Analysis",
                    "difficulty": "Beginner",
                },
                {
                    "question": "What if strings are passed?",
                    "options": ["Concatenates", "Throws error", "Converts", "Returns None"],
                    "correct_answer_index": 0,
                    "explanation": "Strings are concatenated.",
                    "category": "Edge Cases",
                    "difficulty": "Beginner",
                },
            ]
        }
        valid_quiz_json = {
            "questions": [
                {
                    "question": "What does add(2, 3) return?",
                    "options": ["5", "6", "1", "None"],
                    "correct_answer_index": 0,
                    "explanation": "Adding 2 and 3 produces 5.",
                    "category": "Output Prediction",
                    "difficulty": "Beginner",
                },
                {
                    "question": "Which operator is used?",
                    "options": ["+", "-", "*", "/"],
                    "correct_answer_index": 0,
                    "explanation": "The addition operator + is used.",
                    "category": "Syntax Semantics",
                    "difficulty": "Beginner",
                },
                {
                    "question": "What parameters are taken?",
                    "options": ["a and b", "x and y", "nums", "none"],
                    "correct_answer_index": 0,
                    "explanation": "Parameters are a and b.",
                    "category": "Variable Role",
                    "difficulty": "Beginner",
                },
                {
                    "question": "What is the complexity?",
                    "options": ["O(1)", "O(n)", "O(log n)", "O(n^2)"],
                    "correct_answer_index": 0,
                    "explanation": "Complexity is O(1).",
                    "category": "Complexity Analysis",
                    "difficulty": "Beginner",
                },
                {
                    "question": "What if strings are passed?",
                    "options": ["Concatenates", "Throws error", "Converts", "Returns None"],
                    "correct_answer_index": 0,
                    "explanation": "Strings are concatenated.",
                    "category": "Edge Cases",
                    "difficulty": "Beginner",
                },
            ]
        }

        resp1 = MagicMock(text=json.dumps(invalid_quiz_json))
        resp2 = MagicMock(text=json.dumps(valid_quiz_json))
        mock_client.models.generate_content.side_effect = [resp1, resp2]
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/quiz/generate",
            json={
                "code": "def add(a, b):\n    return a + b\n\nresult = add(10, 20)\nprint(result)",
                "language": "Python",
                "learning_level": "Beginner",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["questions"]), 5)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)

    @patch("app.services.quiz_service.get_gemini_client")
    def test_18_quiz_secondary_generation_both_fail_validation(self, mock_get_client):
        """When both generation attempts fail validation, return 502 with format error."""
        mock_client = MagicMock()
        invalid_quiz_json = {
            "questions": [
                {
                    "question": "Short",
                    "options": ["A", "B", "C", "D"],
                    "correct_answer_index": 0,
                    "explanation": "Short explanation",
                    "category": "Output Prediction",
                    "difficulty": "Beginner",
                },
            ]
        }
        resp = MagicMock(text=json.dumps(invalid_quiz_json))
        mock_client.models.generate_content.side_effect = [resp, resp]
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/quiz/generate",
            json={
                "code": "def add(a, b):\n    return a + b\n\nresult = add(10, 20)\nprint(result)",
                "language": "Python",
                "learning_level": "Beginner",
            },
        )

        self.assertEqual(response.status_code, 502)
        detail = response.json().get("detail", "")
        self.assertIn("invalid quiz format", detail.lower())
        self.assertEqual(mock_client.models.generate_content.call_count, 2)

    # -----------------------------------------------------------------
    # 19. Normal Analysis and Tutor Success
    # -----------------------------------------------------------------
    @patch("app.services.llm_service.get_gemini_client")
    def test_19_normal_analysis_success(self, mock_get_client):
        """Normal code analysis succeeds on attempt 1 without retry or fallback."""
        mock_client = MagicMock()
        mock_analysis_data = {
            "overall_purpose": "Computes factorial recursively",
            "how_it_works": "Base case at 1, multiplies recursively",
            "line_by_line": [{"line": 1, "code": "def fact(n): return 1 if n <= 1 else n * fact(n-1)", "explanation": "Factorial"}],
            "variables": [],
            "functions": [],
            "algorithm_logic": "Recursion",
            "time_complexity": "O(n)",
            "space_complexity": "O(n)",
            "potential_issues": [],
            "key_learning_points": ["Recursion base case"],
        }
        mock_resp = MagicMock(text=json.dumps(mock_analysis_data))
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/analyze",
            json={"code": "def fact(n):\n    return 1 if n <= 1 else n * fact(n-1)", "learning_level": "Intermediate"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client.models.generate_content.call_count, 1)

    @patch("app.services.llm_service.get_gemini_client")
    def test_19_normal_tutor_success(self, mock_get_client):
        """Normal AI Tutor query succeeds on attempt 1 without retry or fallback."""
        mock_client = MagicMock()
        mock_tutor_data = {
            "answer": "Recursion means a function calls itself until reaching a base condition.",
            "key_points": ["Base case terminates recursion"],
            "related_code": "return 1 if n <= 1 else n * fact(n-1)",
            "grounded": True,
        }
        mock_resp = MagicMock(text=json.dumps(mock_tutor_data))
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client.return_value = mock_client

        response = self.client.post(
            "/api/tutor",
            json={
                "code": "def fact(n):\n    return 1 if n <= 1 else n * fact(n-1)",
                "language": "Python",
                "learning_level": "Intermediate",
                "question": "How does recursion stop?",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_client.models.generate_content.call_count, 1)

    # -----------------------------------------------------------------
    # PHASE 5 SPECIFICATION TESTS
    # -----------------------------------------------------------------
    def test_phase5_01_primary_503_fallback_success(self):
        """Phase 5 Test 1: Primary 503 -> bounded retries -> fallback success."""
        mock_client = MagicMock()
        err_503 = Exception("503 UNAVAILABLE. Spikes in demand are usually temporary.")
        mock_resp = MagicMock(text="Fallback success response")

        # 3 calls on primary (initial + 2 retries), then fallback succeeds
        mock_client.models.generate_content.side_effect = [err_503, err_503, err_503, mock_resp]
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")

        mock_sleep = MagicMock()
        result = execute_with_retry_and_fallback(
            client=mock_client,
            contents="Explain code",
            config=None,
            primary_model="gemini-3.6-flash",
            fallback_model="gemini-3.5-flash-lite",
            sleep_fn=mock_sleep,
        )
        self.assertEqual(result, mock_resp)
        self.assertEqual(mock_client.models.generate_content.call_count, 4)
        self.assertEqual(mock_sleep.call_count, 2)

    def test_phase5_02_primary_daily_429_fallback_success(self):
        """Phase 5 Test 2: Primary daily 429 quota exhaustion -> 0 retries on primary -> fallback success."""
        mock_client = MagicMock()
        # Google's actual Free Tier daily quota exhaustion payload
        err_daily_429 = Exception(
            "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: "
            "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
            "limit: GenerateRequestsPerDayPerModel-FreeTier, model: gemini-3.6-flash"
        )
        mock_resp = MagicMock(text="Fallback succeeded on lite model")

        mock_client.models.generate_content.side_effect = [err_daily_429, mock_resp]
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")

        mock_sleep = MagicMock()
        result = execute_with_retry_and_fallback(
            client=mock_client,
            contents="Explain code",
            config=None,
            primary_model="gemini-3.6-flash",
            fallback_model="gemini-3.5-flash-lite",
            sleep_fn=mock_sleep,
        )
        self.assertEqual(result, mock_resp)
        # Exactly 2 calls: 1 for primary (0 retries!) and 1 for fallback
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        mock_sleep.assert_not_called()

    def test_phase5_03_primary_transient_429_bounded_handling(self):
        """Phase 5 Test 3: Primary transient 429 -> correct bounded handling respecting Retry-After."""
        mock_client = MagicMock()
        # Transient 429 with Retry-After indication
        err_transient_429 = Exception(
            "429 RESOURCE_EXHAUSTED: Rate limit exceeded. Please retry in 0.05s."
        )
        mock_resp = MagicMock(text="Succeeded on retry 2")

        # Fails once with transient 429, succeeds on retry
        mock_client.models.generate_content.side_effect = [err_transient_429, mock_resp]

        mock_sleep = MagicMock()
        result = execute_with_retry_and_fallback(
            client=mock_client,
            contents="Explain code",
            config=None,
            primary_model="gemini-3.6-flash",
            fallback_model="gemini-3.5-flash-lite",
            sleep_fn=mock_sleep,
        )
        self.assertEqual(result, mock_resp)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        self.assertEqual(mock_sleep.call_count, 1)

    def test_phase5_04_primary_daily_429_fallback_daily_429(self):
        """Phase 5 Test 4: Primary daily 429 -> fallback daily 429 -> returns truthful limits message."""
        mock_client = MagicMock()
        err_daily_primary = Exception(
            "429 RESOURCE_EXHAUSTED: GenerateRequestsPerDayPerModel-FreeTier limit exceeded for gemini-3.6-flash"
        )
        err_daily_fallback = Exception(
            "429 RESOURCE_EXHAUSTED: GenerateRequestsPerDayPerModel-FreeTier limit exceeded for gemini-3.5-flash-lite"
        )

        mock_client.models.generate_content.side_effect = [err_daily_primary, err_daily_fallback]
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")

        mock_sleep = MagicMock()
        with self.assertRaises(LLMServiceError) as ctx:
            execute_with_retry_and_fallback(
                client=mock_client,
                contents="Explain code",
                config=None,
                primary_model="gemini-3.6-flash",
                fallback_model="gemini-3.5-flash-lite",
                sleep_fn=mock_sleep,
            )

        err_msg = str(ctx.exception)
        self.assertIn("AI service limits have been reached for the available models", err_msg)
        self.assertIn("quota resets", err_msg)
        # Exactly 2 calls: 1 primary (0 retries), 1 fallback (0 retries)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)
        mock_sleep.assert_not_called()

    def test_phase5_05_both_models_exhausted(self):
        """Phase 5 Test 5: Both models exhausted -> sanitized truthful error without leaking credentials."""
        mock_client = MagicMock()
        secret_key = "AIzaSyFakeSecretKeyForTesting1234567890"
        err_primary = Exception(f"429 RESOURCE_EXHAUSTED: free_tier_requests daily limit exceeded on key={secret_key}")
        err_fallback = Exception(f"429 RESOURCE_EXHAUSTED: free_tier_requests daily limit exceeded on key={secret_key}")

        mock_client.models.generate_content.side_effect = [err_primary, err_fallback]
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")

        with self.assertRaises(LLMServiceError) as ctx:
            execute_with_retry_and_fallback(
                client=mock_client,
                contents="Prompt",
                config=None,
                primary_model="gemini-3.6-flash",
                fallback_model="gemini-3.5-flash-lite",
            )
        err_msg = str(ctx.exception)
        self.assertNotIn(secret_key, err_msg)
        self.assertIn("AI service limits have been reached for the available models", err_msg)

    def test_phase5_06_primary_403(self):
        """Phase 5 Test 6: Primary 403 permission/billing restriction -> 0 retries, no fallback."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("403 PERMISSION_DENIED: Billing account disabled.")

        mock_sleep = MagicMock()
        with self.assertRaises(LLMServiceError) as ctx:
            execute_with_retry_and_fallback(
                client=mock_client,
                contents="Prompt",
                config=None,
                primary_model="gemini-3.6-flash",
                fallback_model="gemini-3.5-flash-lite",
                sleep_fn=mock_sleep,
            )
        self.assertIn("billing account is disabled", str(ctx.exception).lower())
        self.assertEqual(mock_client.models.generate_content.call_count, 1)
        mock_sleep.assert_not_called()

    def test_phase5_07_primary_404(self):
        """Phase 5 Test 7: Primary 404 invalid model -> switches to verified fallback model."""
        mock_client = MagicMock()
        err_404 = Exception("404 NOT_FOUND: Model 'gemini-nonexistent' not found")
        mock_resp = MagicMock(text="Fallback response")

        mock_client.models.generate_content.side_effect = [err_404, mock_resp]
        mock_client.models.get.return_value = MagicMock(name="models/gemini-3.5-flash-lite")

        result = execute_with_retry_and_fallback(
            client=mock_client,
            contents="Prompt",
            config=None,
            primary_model="gemini-nonexistent",
            fallback_model="gemini-3.5-flash-lite",
        )
        self.assertEqual(result, mock_resp)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)

    def test_phase5_08_language_detection_java(self):
        """Phase 5 Test 8: Language detection using Java code -> deterministic detection with high confidence."""
        java_snippet = (
            "import java.util.ArrayList;\n"
            "class Solution {\n"
            "    public int maxSubArray(int[] nums) {\n"
            "        int maxSum = nums[0];\n"
            "        return maxSum;\n"
            "    }\n"
            "}"
        )
        res = detect_language(java_snippet)
        self.assertEqual(res.language, "Java")
        self.assertEqual(res.confidence, "high")
        self.assertEqual(res.source, "local_heuristics")

    @patch("app.services.llm_service.get_gemini_client")
    def test_phase5_09_analysis_with_deterministic_language_detection(self, mock_get_client):
        """Phase 5 Test 9: Analysis with deterministic language detection -> 0 separate Gemini detection calls."""
        from app.services.analysis_cache import analysis_cache
        analysis_cache.clear()

        mock_client = MagicMock()
        mock_analysis_data = {
            "overall_purpose": "Calculates sum of two integers in Java",
            "how_it_works": "Adds a and b and returns the result",
            "line_by_line": [{"line": 1, "code": "public int add(int a, int b) { return a + b; }", "explanation": "Add method"}],
            "variables": [],
            "functions": [{"name": "add", "parameters": ["int a", "int b"], "purpose": "Addition"}],
            "algorithm_logic": "Basic arithmetic addition",
            "time_complexity": "O(1)",
            "space_complexity": "O(1)",
            "potential_issues": [],
            "key_learning_points": ["Java method signatures"],
        }
        mock_resp = MagicMock(text=json.dumps(mock_analysis_data))
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client.return_value = mock_client

        java_code = "class MathUtils {\n    public int add(int a, int b) {\n        return a + b;\n    }\n}"
        response = self.client.post(
            "/api/analyze",
            json={"code": java_code, "learning_level": "Beginner"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["detected_language"], "Java")
        self.assertEqual(data["confidence"], "high")
        # Exactly 1 call: for analysis, NOT for language detection!
        self.assertEqual(mock_client.models.generate_content.call_count, 1)

    @patch("app.services.llm_service.get_gemini_client")
    def test_phase5_10_duplicate_request_prevention(self, mock_get_client):
        """Phase 5 Test 12: Duplicate request prevention -> reuses cache for identical fingerprint (0 extra Gemini calls)."""
        from app.services.analysis_cache import analysis_cache
        analysis_cache.clear()

        mock_client = MagicMock()
        mock_analysis_data = {
            "overall_purpose": "Prints hello world",
            "how_it_works": "Calls built-in print",
            "line_by_line": [{"line": 1, "code": "print('hello')", "explanation": "Outputs hello"}],
            "variables": [],
            "functions": [],
            "algorithm_logic": "Standard output",
            "time_complexity": "O(1)",
            "space_complexity": "O(1)",
            "potential_issues": [],
            "key_learning_points": ["Print statements"],
        }
        mock_resp = MagicMock(text=json.dumps(mock_analysis_data))
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client.return_value = mock_client

        code = "print('hello')\nprint('world')"
        # First request
        resp1 = self.client.post("/api/analyze", json={"code": code, "learning_level": "Beginner"})
        self.assertEqual(resp1.status_code, 200)
        self.assertEqual(mock_client.models.generate_content.call_count, 1)

        # Second request with identical code and level -> reused from cache
        resp2 = self.client.post("/api/analyze", json={"code": code, "learning_level": "Beginner"})
        self.assertEqual(resp2.status_code, 200)
        # Call count remains 1: 0 additional Gemini calls!
        self.assertEqual(mock_client.models.generate_content.call_count, 1)

    @patch("app.services.llm_service.get_gemini_client")
    def test_phase5_11_different_code_not_reused(self, mock_get_client):
        """Phase 5: Results are NOT reused for different code."""
        from app.services.analysis_cache import analysis_cache
        analysis_cache.clear()

        mock_client = MagicMock()
        mock_analysis_data = {
            "overall_purpose": "Test code",
            "how_it_works": "Test execution",
            "line_by_line": [{"line": 1, "code": "x = 1", "explanation": "Assigns x"}],
            "variables": [],
            "functions": [],
            "algorithm_logic": "Assignment",
            "time_complexity": "O(1)",
            "space_complexity": "O(1)",
            "potential_issues": [],
            "key_learning_points": [],
        }
        mock_resp = MagicMock(text=json.dumps(mock_analysis_data))
        mock_client.models.generate_content.return_value = mock_resp
        mock_get_client.return_value = mock_client

        code_a = "def func_a():\n    return 42"
        code_b = "def func_b():\n    return 99"

        resp_a = self.client.post("/api/analyze", json={"code": code_a, "learning_level": "Beginner"})
        self.assertEqual(resp_a.status_code, 200)
        self.assertEqual(mock_client.models.generate_content.call_count, 1)

        resp_b = self.client.post("/api/analyze", json={"code": code_b, "learning_level": "Beginner"})
        self.assertEqual(resp_b.status_code, 200)
        # Call count is 2: fresh Gemini call executed for different code
        self.assertEqual(mock_client.models.generate_content.call_count, 2)


if __name__ == "__main__":
    unittest.main()



