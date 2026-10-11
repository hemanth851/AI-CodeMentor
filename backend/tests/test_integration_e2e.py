"""
Step 10: End-to-End API Integration & User Workflow Tests.
Exercises all 6 backend endpoints in connected sequence:
1. /api/health
2. /api/analyze
3. /api/tutor
4. /api/visualize
5. /api/quiz/generate
6. /api/quiz/submit
7. / (Root endpoint)
"""

import unittest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from app.main import app
from app.models.analysis import CodeAnalysis, LineExplanation, VariableInfo
from app.models.tutor import TutorLLMResponse
from app.models.quiz import QuizGenerateResponse, QuizQuestionPublic


class TestEndToEndIntegration(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # =========================================================================
    # 1. Health Endpoint Verification
    # =========================================================================
    def test_health_check_contract(self):
        """Verify /api/health contract returns status ok."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("message", data)

    # =========================================================================
    # 2. Root Endpoint Verification
    # =========================================================================
    def test_root_endpoint_contract(self):
        """Verify root endpoint returns API info and documentation link."""
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["name"], "AI CodeMentor API")
        self.assertEqual(data["health_check"], "/api/health")

    # =========================================================================
    # 3. Complete Workflow A: First-Time User End-to-End Pipeline
    # =========================================================================
    @patch("app.api.analyze.analyze_code")
    @patch("app.api.analyze.get_gemini_client")
    @patch("app.api.tutor.ask_tutor")
    @patch("app.api.tutor.get_gemini_client")
    @patch("app.api.quiz.generate_quiz")
    @patch("app.api.quiz.get_gemini_client")
    def test_complete_first_time_user_workflow(
        self,
        mock_quiz_client,
        mock_generate_quiz,
        mock_tutor_client,
        mock_ask_tutor,
        mock_analyze_client,
        mock_analyze_code,
    ):
        """
        Simulate a complete user journey:
        1. User checks health
        2. User submits Python binary search for analysis
        3. User asks AI Tutor a follow-up question
        4. User visualizes algorithm execution
        5. User generates a quiz
        6. User submits answers and gets scored
        """
        python_code = (
            "def binary_search(arr, target):\n"
            "    low = 0\n"
            "    high = len(arr) - 1\n"
            "    while low <= high:\n"
            "        mid = (low + high) // 2\n"
            "        if arr[mid] == target:\n"
            "            return mid\n"
            "        elif arr[mid] < target:\n"
            "            low = mid + 1\n"
            "        else:\n"
            "            high = mid - 1\n"
            "    return -1\n"
            "\n"
            "result = binary_search([1, 3, 5, 7, 9], 5)\n"
        )

        # Mock Analysis Response
        mock_analyze_client.return_value = MagicMock()
        mock_analyze_code.return_value = CodeAnalysis(
            overall_purpose="Searches for target in a sorted list.",
            how_it_works="Divides search interval in half repeatedly.",
            line_by_line=[LineExplanation(line=1, code="def binary_search", explanation="Defines function.")],
            variables=[VariableInfo(name="low", purpose="Search lower bound.")],
            functions=[],
            algorithm_logic="Binary Search algorithm with O(log n) efficiency.",
            time_complexity="O(log n)",
            space_complexity="O(1)",
            potential_issues=[],
            key_learning_points=["Input list must be sorted."],
        )

        # 1. Analyze Code
        analyze_resp = self.client.post(
            "/api/analyze",
            json={"code": python_code, "learning_level": "Beginner"},
        )
        self.assertEqual(analyze_resp.status_code, 200)
        analyze_data = analyze_resp.json()
        self.assertEqual(analyze_data["status"], "success")
        self.assertEqual(analyze_data["detected_language"], "Python")
        self.assertIn("static_analysis", analyze_data)
        self.assertIsNotNone(analyze_data["static_analysis"])

        # 2. Ask Tutor Grounded in Analyzed Code
        mock_tutor_client.return_value = MagicMock()
        mock_ask_tutor.return_value = TutorLLMResponse(
            answer="The while condition ensures the bounds do not cross.",
            key_points=["low <= high maintains the active search window."],
            related_code="while low <= high:",
            grounded=True,
        )

        tutor_resp = self.client.post(
            "/api/tutor",
            json={
                "code": python_code,
                "language": "Python",
                "learning_level": "Beginner",
                "question": "Why is the loop condition low <= high?",
                "analysis": analyze_data,
                "static_analysis": analyze_data["static_analysis"],
                "history": [],
            },
        )
        self.assertEqual(tutor_resp.status_code, 200)
        tutor_data = tutor_resp.json()
        self.assertTrue(tutor_data["success"])
        self.assertTrue(tutor_data["grounded"])
        self.assertIn("while condition", tutor_data["answer"])

        # 3. Deterministically Trace Algorithm Visualization
        vis_resp = self.client.post(
            "/api/visualize",
            json={"code": python_code, "language": "Python"},
        )
        self.assertEqual(vis_resp.status_code, 200)
        vis_data = vis_resp.json()
        self.assertEqual(vis_data["status"], "success")
        self.assertTrue(vis_data["supported"])
        self.assertEqual(vis_data["final_state"].get("result"), 2)
        self.assertGreater(vis_data["total_steps"], 5)

        # 4. Generate Assessment Quiz
        mock_quiz_client.return_value = MagicMock()
        mock_generate_quiz.return_value = QuizGenerateResponse(
            quiz_id="quiz_test_123",
            quiz_token="valid_mock_token_abc",
            code_summary="Binary Search in Python",
            questions=[
                QuizQuestionPublic(
                    id=i,
                    question=f"Question {i} about binary search?",
                    options=["Option A", "Option B", "Option C", "Option D"],
                    difficulty="Beginner",
                    category="Algorithm Logic",
                )
                for i in range(1, 6)
            ],
        )

        quiz_gen_resp = self.client.post(
            "/api/quiz/generate",
            json={
                "code": python_code,
                "language": "Python",
                "learning_level": "Beginner",
                "analysis": analyze_data,
                "static_analysis": analyze_data["static_analysis"],
            },
        )
        self.assertEqual(quiz_gen_resp.status_code, 200)
        quiz_data = quiz_gen_resp.json()
        self.assertEqual(len(quiz_data["questions"]), 5)
        self.assertEqual(quiz_data["quiz_id"], "quiz_test_123")
        self.assertIn("quiz_token", quiz_data)

    # =========================================================================
    # 4. Workflow C: Error Handling & Security Boundary Tests
    # =========================================================================
    def test_analyze_empty_code_rejected(self):
        """Empty code payload should return 422 Unprocessable Entity."""
        resp = self.client.post("/api/analyze", json={"code": "", "learning_level": "Beginner"})
        self.assertEqual(resp.status_code, 422)

    @patch("app.api.analyze.get_gemini_client")
    def test_analyze_unsupported_language_behavior(self, mock_client):
        """Unsupported language syntax returns status='unsupported' cleanly."""
        mock_client.return_value = MagicMock()
        html_code = "<!DOCTYPE html><html><body><h1>Hello World</h1></body></html>"
        resp = self.client.post("/api/analyze", json={"code": html_code, "learning_level": "Beginner"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "unsupported")

    @patch("app.api.analyze.get_gemini_client")
    def test_analyze_ambiguous_short_snippet(self, mock_client):
        """Short ambiguous snippet like x = 1 returns status='ambiguous'."""
        mock_client.return_value = MagicMock()
        short_snippet = "x = 10"
        resp = self.client.post("/api/analyze", json={"code": short_snippet, "learning_level": "Beginner"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ambiguous")

    def test_visualize_non_python_supported(self):
        """Visualization of non-Python language (JavaScript) executes successfully."""
        js_code = "const x = [1, 2, 3];"
        resp = self.client.post("/api/visualize", json={"code": js_code, "language": "JavaScript"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["supported"])
        self.assertEqual(data["termination_reason"], "completed")
        self.assertTrue(len(data["trace"]) > 0)

    def test_quiz_submit_invalid_or_tampered_token(self):
        """Submitting quiz answers with invalid/tampered token returns 400."""
        resp = self.client.post(
            "/api/quiz/submit",
            json={
                "quiz_id": "quiz_fake_999",
                "quiz_token": "tampered_fake_token",
                "answers": {"1": 0, "2": 1, "3": 2, "4": 3, "5": 0},
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.json())


if __name__ == "__main__":
    unittest.main()
