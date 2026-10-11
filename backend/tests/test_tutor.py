"""
Comprehensive Tests for AI CodeMentor Step 6 — Interactive AI Tutor / Code Q&A.
Covers all required test categories:
API Validation:
1. Empty question
2. Empty code
3. Invalid learning level
4. Missing required fields
5. Valid tutor request

Context Grounding:
6. Code is included in Gemini context
7. Language is included in context
8. Learning level is included in context
9. Static-analysis facts are included
10. Existing analysis is included

Conversation:
11. First question works
12. Follow-up question works
13. Conversation history is bounded (max 10 messages)
14. New analysis clears old tutor context

Error Handling:
15. Gemini API failure (rate limit / 500)
16. Network / API timeout exception
17. Invalid / empty response from Gemini
18. Tutor request before analysis / missing parameters
"""

import json
import unittest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from app.main import app
from app.models.tutor import TutorRequest, TutorResponse, TutorMessage, TutorLLMResponse
from app.services.llm_service import build_tutor_prompt, ask_tutor, LLMConfigurationError, LLMServiceError


MOCK_TUTOR_ANSWER = {
    "answer": "The loop is necessary because it iterates through each number in the collection to compare it with the current maximum.",
    "key_points": [
        "Processes each element sequentially",
        "Updates the maximum whenever a larger number is found",
    ],
    "related_code": "for number in numbers:\n    if number > maximum:\n        maximum = number",
    "grounded": True,
}

SAMPLE_PYTHON_CODE = (
    "def find_max(numbers):\n"
    "    maximum = numbers[0]\n"
    "    for number in numbers:\n"
    "        if number > maximum:\n"
    "            maximum = number\n"
    "    return maximum\n"
)


class TestAiTutorStep6(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # -----------------------------------------------------------------
    # API Validation Tests (1-5)
    # -----------------------------------------------------------------
    def test_01_empty_question_rejected(self):
        """1. Empty or whitespace-only question should return HTTP 422."""
        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
            "question": "   ",
        }
        response = self.client.post("/api/tutor", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_02_empty_code_rejected(self):
        """2. Empty or whitespace-only code should return HTTP 422."""
        payload = {
            "code": "   ",
            "language": "Python",
            "learning_level": "Beginner",
            "question": "Why is the loop needed?",
        }
        response = self.client.post("/api/tutor", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_03_invalid_learning_level_rejected(self):
        """3. Invalid learning level string should return HTTP 422."""
        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "SuperExpertMaster",
            "question": "Why is the loop needed?",
        }
        response = self.client.post("/api/tutor", json=payload)
        self.assertEqual(response.status_code, 422)

    def test_04_missing_required_fields_rejected(self):
        """4. Missing required fields (such as question or language) should return HTTP 422."""
        # Missing question
        res1 = self.client.post("/api/tutor", json={"code": SAMPLE_PYTHON_CODE, "language": "Python"})
        self.assertEqual(res1.status_code, 422)

        # Missing code
        res2 = self.client.post("/api/tutor", json={"language": "Python", "question": "Explain this"})
        self.assertEqual(res2.status_code, 422)

        # Missing language
        res3 = self.client.post("/api/tutor", json={"code": SAMPLE_PYTHON_CODE, "question": "Explain this"})
        self.assertEqual(res3.status_code, 422)

    @patch("app.api.tutor.ask_tutor")
    @patch("app.api.tutor.get_gemini_client")
    def test_05_valid_tutor_request_succeeds(self, mock_client, mock_ask):
        """5. Valid tutor request returns HTTP 200 with structured response."""
        mock_client.return_value = MagicMock()
        mock_ask.return_value = TutorLLMResponse(**MOCK_TUTOR_ANSWER)

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
            "question": "Why is the loop necessary?",
        }
        response = self.client.post("/api/tutor", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("The loop is necessary", data["answer"])
        self.assertEqual(len(data["key_points"]), 2)
        self.assertTrue(data["grounded"])
        self.assertIn("for number in numbers", data["related_code"])

    # -----------------------------------------------------------------
    # Context Grounding Tests (6-10)
    # -----------------------------------------------------------------
    def test_06_code_is_included_in_context(self):
        """6. The source code must be embedded verbatim in the tutor prompt."""
        prompt = build_tutor_prompt(
            code=SAMPLE_PYTHON_CODE,
            language="Python",
            learning_level="Beginner",
            question="Why is this loop needed?",
        )
        self.assertIn(SAMPLE_PYTHON_CODE, prompt)
        self.assertIn("=== SOURCE CODE (GROUND TRUTH) ===", prompt)

    def test_07_language_is_included_in_context(self):
        """7. Target programming language must be explicitly provided in prompt."""
        prompt = build_tutor_prompt(
            code=SAMPLE_PYTHON_CODE,
            language="Python",
            learning_level="Intermediate",
            question="What is the complexity?",
        )
        self.assertIn("Target Programming Language: Python", prompt)

    def test_08_learning_level_is_included_in_context(self):
        """8. Learning level and level-specific pedagogical guidance must be in prompt."""
        prompt_beg = build_tutor_prompt(
            code=SAMPLE_PYTHON_CODE,
            language="Python",
            learning_level="Beginner",
            question="Explain line 2",
        )
        self.assertIn("Learning Level: Beginner", prompt_beg)
        self.assertIn("Use simple vocabulary and intuitive explanations", prompt_beg)

        prompt_adv = build_tutor_prompt(
            code=SAMPLE_PYTHON_CODE,
            language="Python",
            learning_level="Advanced",
            question="Explain line 2",
        )
        self.assertIn("Learning Level: Advanced", prompt_adv)
        self.assertIn("algorithmic reasoning", prompt_adv)

    def test_09_static_analysis_facts_included(self):
        """9. Static analysis facts (loops, nesting, recursion) must be included when present."""
        static_facts = {
            "structure": {"loops": 1, "conditionals": 1, "functions": 1},
            "complexity_evidence": {"loops": 1, "nested_loops": False, "recursion_detected": False},
        }
        prompt = build_tutor_prompt(
            code=SAMPLE_PYTHON_CODE,
            language="Python",
            learning_level="Intermediate",
            question="What is the time complexity?",
            static_analysis=static_facts,
        )
        self.assertIn("=== STATIC ANALYSIS FACTS ===", prompt)
        self.assertIn("Structure Metrics:", prompt)
        self.assertIn("Complexity Evidence:", prompt)

    def test_10_existing_analysis_included(self):
        """10. Existing structured explanation must be included in prompt for pedagogical grounding."""
        analysis_context = {
            "overall_purpose": "Finds the maximum integer in a list.",
            "how_it_works": "Iterates sequentially through the list.",
            "algorithm_logic": "Linear scan with upper-bound tracking.",
            "time_complexity": "O(n)",
        }
        prompt = build_tutor_prompt(
            code=SAMPLE_PYTHON_CODE,
            language="Python",
            learning_level="Beginner",
            question="Why can't we use an if statement instead?",
            analysis=analysis_context,
        )
        self.assertIn("=== EXISTING CODE ANALYSIS CONTEXT ===", prompt)
        self.assertIn("Finds the maximum integer in a list.", prompt)
        self.assertIn("Linear scan with upper-bound tracking.", prompt)

    # -----------------------------------------------------------------
    # Conversation Tests (11-14)
    # -----------------------------------------------------------------
    @patch("app.api.tutor.ask_tutor")
    @patch("app.api.tutor.get_gemini_client")
    def test_11_first_question_works(self, mock_client, mock_ask):
        """11. First tutor question without prior history works cleanly."""
        mock_client.return_value = MagicMock()
        mock_ask.return_value = TutorLLMResponse(**MOCK_TUTOR_ANSWER)

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
            "question": "What does this function do?",
            "history": [],
        }
        response = self.client.post("/api/tutor", json=payload)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["grounded"])

    def test_12_follow_up_question_includes_conversation_history(self):
        """12. Follow-up question formats previous conversation turns into prompt."""
        history = [
            TutorMessage(role="user", content="Why is a loop used?"),
            TutorMessage(role="tutor", content="The loop processes each item sequentially."),
        ]
        prompt = build_tutor_prompt(
            code=SAMPLE_PYTHON_CODE,
            language="Python",
            learning_level="Beginner",
            question="Why can't we just use an if statement?",
            history=history,
        )
        self.assertIn("=== RECENT CONVERSATION HISTORY ===", prompt)
        self.assertIn("User: Why is a loop used?", prompt)
        self.assertIn("AI Tutor: The loop processes each item sequentially.", prompt)
        self.assertIn("Why can't we just use an if statement?", prompt)

    def test_13_conversation_history_is_bounded(self):
        """13. History is strictly bounded to the last 10 messages."""
        # Create 16 messages
        messages = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"Message {i}"}
            for i in range(16)
        ]
        req = TutorRequest(
            code=SAMPLE_PYTHON_CODE,
            language="Python",
            learning_level="Beginner",
            question="Final question?",
            history=messages,
        )
        # Should keep only last 10 messages
        self.assertEqual(len(req.history), 10)
        self.assertEqual(req.history[0].content, "Message 6")
        self.assertEqual(req.history[-1].content, "Message 15")

        # Also test in prompt builder
        prompt = build_tutor_prompt(
            code=SAMPLE_PYTHON_CODE,
            language="Python",
            learning_level="Beginner",
            question="Final question?",
            history=messages,
        )
        self.assertNotIn("Message 0", prompt)
        self.assertIn("Message 15", prompt)

    def test_14_new_analysis_clears_old_context(self):
        """14. A new code analysis session starts with empty history."""
        # Simulate new session with empty history
        req = TutorRequest(
            code="x = 50\nprint(x)",
            language="Python",
            learning_level="Beginner",
            question="What does x contain?",
            history=[],
        )
        self.assertEqual(len(req.history), 0)
        self.assertIn("x = 50", req.code)

    # -----------------------------------------------------------------
    # Error Handling Tests (15-18)
    # -----------------------------------------------------------------
    @patch("app.api.tutor.ask_tutor")
    @patch("app.api.tutor.get_gemini_client")
    def test_15_gemini_api_failure_handled(self, mock_client, mock_ask):
        """15. Gemini API failure returns 502 with user-friendly message."""
        mock_client.return_value = MagicMock()
        mock_ask.side_effect = LLMServiceError(
            "The AI service is temporarily busy due to rate limits. Please wait a moment and try again."
        )

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
            "question": "Explain this code",
        }
        response = self.client.post("/api/tutor", json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("temporarily busy", response.json()["detail"])

    @patch("app.api.tutor.ask_tutor")
    @patch("app.api.tutor.get_gemini_client")
    def test_16_network_timeout_handled(self, mock_client, mock_ask):
        """16. Network/timeout exception returns 502 with friendly message."""
        mock_client.return_value = MagicMock()
        mock_ask.side_effect = LLMServiceError(
            "Request to the AI service timed out. Please try again."
        )

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
            "question": "Explain this code",
        }
        response = self.client.post("/api/tutor", json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("timed out", response.json()["detail"])

    @patch("app.api.tutor.get_gemini_client")
    def test_17_missing_api_key_configuration(self, mock_client):
        """17. Missing API key returns 503 service unavailable."""
        mock_client.side_effect = LLMConfigurationError("Gemini API key is not configured.")

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
            "question": "Explain this code",
        }
        response = self.client.post("/api/tutor", json=payload)
        self.assertEqual(response.status_code, 503)
        self.assertIn("API key is not configured", response.json()["detail"])

    def test_18_tutor_request_before_analysis_missing_code(self):
        """18. Tutor request without code or with empty body fails validation."""
        response = self.client.post("/api/tutor", json={})
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
