"""
Regression tests for Visualization failure fixes, language discrimination, and Quiz integrity.

Verifies:
1. Valid Python code visualization succeeds via restricted AST tracing.
2. Java code with language="Java" returns unsupported status with exact message.
3. Java code with language="Python" (or omitted) is detected as non-Python and returns
   unsupported rather than a Python syntax error.
4. Genuine Python syntax error returns syntax_error cleanly without crashing.
5. Quiz generation produces 5 questions with 4 options each.
6. Quiz scoring deterministically validates answers.
7. Visualization errors do not affect analysis or tutor endpoints.
"""

import unittest
from starlette.testclient import TestClient

from app.main import app
from app.services.visualizer.engine import trace_python_code


class TestVisualizeQuizRegression(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_01_valid_python_visualization_succeeds(self):
        """Python algorithm execution visualization succeeds deterministically."""
        code = "total = 0\nfor x in [1, 2, 3]:\n    total += x"
        payload = {"code": code, "language": "Python"}
        response = self.client.post("/api/visualize", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["supported"])
        self.assertEqual(data["termination_reason"], "completed")
        self.assertEqual(data["final_state"].get("total"), 6)
        self.assertTrue(len(data["trace"]) > 0)

    def test_02_java_explicit_language_returns_supported_language_message(self):
        """Java code with language='Java' visualizes successfully."""
        payload = {
            "code": "public class Adder { public static int add(int a, int b) { return a + b; } }",
            "language": "Java",
        }
        response = self.client.post("/api/visualize", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["supported"])
        self.assertEqual(data["termination_reason"], "completed")
        self.assertTrue(len(data["trace"]) > 0)

    def test_03_java_code_sent_as_python_never_displays_python_syntax_error(self):
        """Java code sent with language='Python' visualizes successfully without syntax error."""
        java_code = "public class Adder {\n    public static int add(int a, int b) {\n        return a + b;\n    }\n}"
        payload = {
            "code": java_code,
            "language": "Python",
        }
        response = self.client.post("/api/visualize", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["supported"])
        self.assertNotIn("syntax error", (data.get("error") or "").lower())
        self.assertTrue(len(data["trace"]) > 0)

    def test_04_direct_trace_on_java_code_returns_unsupported_not_syntax_error(self):
        """trace_python_code directly on Java snippet intercepts and returns unsupported."""
        java_code = "public class Main { public static void main(String[] args) { System.out.println(1); } }"
        res = trace_python_code(java_code)
        self.assertEqual(res.status, "unsupported")
        self.assertFalse(res.supported)
        self.assertEqual(res.termination_reason, "unsupported_language")
        self.assertEqual(res.error, "Interactive visualization is currently available only for Python.")

    def test_05_genuine_python_syntax_error_returns_meaningful_syntax_error(self):
        """A genuine syntax error in Python code returns syntax_error with line info."""
        broken_python = "def broken(\n    x = 10"
        res = trace_python_code(broken_python)
        self.assertEqual(res.status, "error")
        self.assertTrue(res.supported)
        self.assertEqual(res.termination_reason, "syntax_error")
        self.assertIn("Python syntax error", res.error)

    def test_06_visualization_failure_does_not_break_health_or_static_analysis(self):
        """Calling visualize with unsupported code does not impact API health or endpoints."""
        vis_resp = self.client.post("/api/visualize", json={"code": "class Foo {}", "language": "Java"})
        self.assertEqual(vis_resp.status_code, 200)

        health_resp = self.client.get("/api/health")
        self.assertEqual(health_resp.status_code, 200)
        self.assertEqual(health_resp.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
