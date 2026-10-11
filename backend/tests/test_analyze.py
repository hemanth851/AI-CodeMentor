"""
Comprehensive Tests for AI CodeMentor Step 4 — Structured AI Code Explanation.
Covers all 20 required test categories:
1. Python detection
2. Java detection
3. C detection
4. C++ detection
5. JavaScript detection
6. TypeScript detection
7. C# detection
8. Go detection
9. Rust detection
10. PHP detection
11. Kotlin detection
12. Swift detection
13. SQL detection
14. Partial snippets
15. Short/ambiguous snippets
16. Unsupported languages
17. Structured response validation
18. Invalid learning level
19. Invalid/empty code
20. Existing API behavior
"""

import json
import unittest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from app.main import app
from app.services.detector import detect_language, detect_by_extension, detect_by_heuristics
from app.services.llm_service import build_educational_prompt
from app.models.analysis import CodeAnalysis

MOCK_STRUCTURED_ANALYSIS = {
    "overall_purpose": "Calculates the maximum element in a list of numbers.",
    "how_it_works": "Iterates through the list, comparing each element to the current maximum.",
    "line_by_line": [
        {
            "line": 1,
            "code": "def find_max(numbers):",
            "explanation": "Defines a function named find_max that takes a collection of numbers as input.",
        },
        {
            "line": 2,
            "code": "    return max(numbers)",
            "explanation": "Returns the largest item using the built-in max function.",
        },
    ],
    "variables": [
        {
            "name": "numbers",
            "purpose": "List of integers to evaluate for the maximum value.",
        }
    ],
    "functions": [
        {
            "name": "find_max",
            "parameters": ["numbers"],
            "purpose": "Finds the maximum value in the input list.",
            "return_value": "The largest numeric value found.",
        }
    ],
    "algorithm_logic": "Linear scan finding the upper bound element.",
    "time_complexity": "O(n) where n is the number of elements in the list.",
    "space_complexity": "O(1) auxiliary space.",
    "potential_issues": [
        {
            "severity": "possible",
            "description": "Raises ValueError if numbers list is empty.",
        }
    ],
    "key_learning_points": [
        "Function definition syntax",
        "Built-in aggregation utilities",
        "Linear time complexity",
    ],
}


class TestAnalyzeEndpointStep4(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # -------------------------------------------------------------
    # 20. Existing API Behavior: Health check
    # -------------------------------------------------------------
    def test_20_health_check(self):
        """GET /api/health should return HTTP 200 and healthy status."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["message"], "AI CodeMentor backend is running")

    # -------------------------------------------------------------
    # 19. Invalid / Empty Code
    # -------------------------------------------------------------
    def test_19_empty_code_rejected(self):
        """Empty or whitespace-only code should return 422."""
        response = self.client.post("/api/analyze", json={
            "code": "   \n\t  ",
            "learning_level": "Beginner",
        })
        self.assertEqual(response.status_code, 422)

    def test_19_code_over_100kb_rejected(self):
        """Code exceeding 100 KB should be rejected with 422."""
        large_code = "x = 1\n" * 20000  # > 100 KB
        response = self.client.post("/api/analyze", json={
            "code": large_code,
            "learning_level": "Beginner",
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn("100 KB", str(response.json()))

    # -------------------------------------------------------------
    # 18. Invalid Learning Level
    # -------------------------------------------------------------
    def test_18_invalid_learning_level_rejected(self):
        """Invalid learning levels like Expert, Master, Pro should return 422."""
        response = self.client.post("/api/analyze", json={
            "code": "print('hello')",
            "learning_level": "Expert",
        })
        self.assertEqual(response.status_code, 422)
        self.assertIn("Invalid learning level", str(response.json()))

    # -------------------------------------------------------------
    # 1-13. Language Detection for all 13 Supported Languages
    # -------------------------------------------------------------
    def test_01_python_detection(self):
        """Python detection via syntax characteristics or .py extension."""
        code = "def greet(name):\n    for i in range(3):\n        print(f'Hello {name}')"
        res = detect_language(code)
        self.assertEqual(res.language, "Python")
        self.assertEqual(res.confidence, "high")

        # Via file extension
        ext_res = detect_by_extension("script.py")
        self.assertEqual(ext_res.language, "Python")

    def test_02_java_detection(self):
        """Java detection via syntax characteristics or .java extension."""
        code = "public class Solution {\n    public static void main(String[] args) {\n        System.out.println(\"Java\");\n    }\n}"
        res = detect_language(code)
        self.assertEqual(res.language, "Java")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("Solution.java")
        self.assertEqual(ext_res.language, "Java")

    def test_03_c_detection(self):
        """C detection via #include <stdio.h>, printf, and pointers."""
        code = "#include <stdio.h>\nint main(void) {\n    printf(\"Value: %d\\n\", 42);\n    return 0;\n}"
        res = detect_language(code)
        self.assertEqual(res.language, "C")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("main.c")
        self.assertEqual(ext_res.language, "C")

    def test_04_cpp_detection(self):
        """C++ detection via #include <iostream>, std::cout, and cin."""
        code = "#include <iostream>\nusing namespace std;\nint main() {\n    cout << \"Hello C++\" << endl;\n    return 0;\n}"
        res = detect_language(code)
        self.assertEqual(res.language, "C++")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("main.cpp")
        self.assertEqual(ext_res.language, "C++")

    def test_05_javascript_detection(self):
        """JavaScript detection via console.log, const, arrow functions."""
        code = "const calculateSum = (a, b) => {\n    console.log('Calculating...');\n    return a + b;\n};"
        res = detect_language(code)
        self.assertEqual(res.language, "JavaScript")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("app.js")
        self.assertEqual(ext_res.language, "JavaScript")

    def test_06_typescript_detection(self):
        """TypeScript detection via interface, type annotations, and generics."""
        code = "interface User {\n    id: number;\n    name: string;\n}\nconst u: User = { id: 1, name: 'Alice' };"
        res = detect_language(code)
        self.assertEqual(res.language, "TypeScript")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("service.ts")
        self.assertEqual(ext_res.language, "TypeScript")

    def test_07_csharp_detection(self):
        """C# detection via using System, Console.WriteLine, namespace."""
        code = "using System;\nnamespace App {\n    class Program {\n        static void Main() {\n            Console.WriteLine(\"Hello C#\");\n        }\n    }\n}"
        res = detect_language(code)
        self.assertEqual(res.language, "C#")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("Program.cs")
        self.assertEqual(ext_res.language, "C#")

    def test_08_go_detection(self):
        """Go detection via package main, fmt.Println, :=, and func."""
        code = "package main\nimport \"fmt\"\nfunc main() {\n    msg := \"Hello Go\"\n    fmt.Println(msg)\n}"
        res = detect_language(code)
        self.assertEqual(res.language, "Go")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("main.go")
        self.assertEqual(ext_res.language, "Go")

    def test_09_rust_detection(self):
        """Rust detection via fn main, let mut, println!, unwrap."""
        code = "fn main() {\n    let mut count = 0;\n    count += 1;\n    println!(\"Count is: {}\", count);\n}"
        res = detect_language(code)
        self.assertEqual(res.language, "Rust")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("main.rs")
        self.assertEqual(ext_res.language, "Rust")

    def test_10_php_detection(self):
        """PHP detection via <?php, $ variables, and echo."""
        code = "<?php\n$greeting = \"Hello PHP\";\necho $greeting;\n?>"
        res = detect_language(code)
        self.assertEqual(res.language, "PHP")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("index.php")
        self.assertEqual(ext_res.language, "PHP")

    def test_11_kotlin_detection(self):
        """Kotlin detection via fun main, val, println, data class."""
        code = "data class User(val name: String)\nfun main() {\n    val user = User(\"Kotlin\")\n    println(user.name)\n}"
        res = detect_language(code)
        self.assertEqual(res.language, "Kotlin")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("Main.kt")
        self.assertEqual(ext_res.language, "Kotlin")

    def test_12_swift_detection(self):
        """Swift detection via guard let, func, print, import Foundation."""
        code = "import Foundation\nfunc greet(person: String) -> String {\n    guard !person.isEmpty else { return \"Empty\" }\n    return \"Hello, \" + person\n}"
        res = detect_language(code)
        self.assertEqual(res.language, "Swift")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("App.swift")
        self.assertEqual(ext_res.language, "Swift")

    def test_13_sql_detection(self):
        """SQL detection via SELECT, FROM, WHERE, GROUP BY."""
        code = "SELECT department, COUNT(*) FROM employees WHERE salary > 50000 GROUP BY department;"
        res = detect_language(code)
        self.assertEqual(res.language, "SQL")
        self.assertEqual(res.confidence, "high")

        ext_res = detect_by_extension("query.sql")
        self.assertEqual(ext_res.language, "SQL")

    # -------------------------------------------------------------
    # 14. Partial Snippets
    # -------------------------------------------------------------
    def test_14_partial_snippets_supported(self):
        """Valid partial snippets without main() or classes should be detected and accepted."""
        # 1. Partial Python
        res1 = detect_language("for i in range(5):\n    print(i)")
        self.assertEqual(res1.language, "Python")

        # 2. Partial C
        res2 = detect_language("int x = 10;\nprintf(\"%d\", x);")
        self.assertEqual(res2.language, "C")

        # 3. Partial SQL
        res3 = detect_language("SELECT name FROM students;")
        self.assertEqual(res3.language, "SQL")

        # 4. Partial Python if-block
        res4 = detect_language("if x > 10:\n    print(\"Large\")")
        self.assertEqual(res4.language, "Python")

    # -------------------------------------------------------------
    # 15. Short / Ambiguous Snippets
    # -------------------------------------------------------------
    def test_15_short_ambiguous_snippet_requests_more_code(self):
        """Ambiguous snippets like 'x = 10' should return friendly request for more code without inventing language."""
        with patch("app.services.llm_service.get_gemini_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            response = self.client.post("/api/analyze", json={
                "code": "x = 10",
                "learning_level": "Beginner",
            })
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertTrue(data["success"])
            self.assertEqual(data["status"], "ambiguous")
            self.assertEqual(data["confidence"], "low")
            self.assertIn("too short to confidently determine", data["message"])
            self.assertIn("Please provide a few more lines of code", data["message"])

    # -------------------------------------------------------------
    # 16. Unsupported Languages
    # -------------------------------------------------------------
    def test_16_unsupported_language_returns_friendly_message(self):
        """Unsupported languages (Ruby, HTML) should return clear unsupported notice."""
        with patch("app.services.llm_service.get_gemini_client") as mock_get_client:
            mock_client = MagicMock()
            mock_get_client.return_value = mock_client

            # HTML snippet
            html_code = "<!DOCTYPE html><html><body><h1>Hello World</h1></body></html>"
            response = self.client.post("/api/analyze", json={
                "code": html_code,
                "learning_level": "Beginner",
            })
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["status"], "unsupported")
            self.assertIn("not currently supported", data["message"])

            # Ruby file extension upload
            response_rb = self.client.post("/api/analyze", json={
                "code": "puts 'Hello World'",
                "filename": "script.rb",
                "learning_level": "Beginner",
            })
            self.assertEqual(response_rb.status_code, 200)
            data_rb = response_rb.json()
            self.assertEqual(data_rb["status"], "unsupported")
            self.assertIn("not currently supported", data_rb["message"])

    # -------------------------------------------------------------
    # 17. Structured Response Validation
    # -------------------------------------------------------------
    def test_17_structured_response_validation(self):
        """Full end-to-end endpoint test returning all structured fields."""
        with patch("app.services.llm_service.get_gemini_client") as mock_get_client:
            mock_client = MagicMock()
            mock_response = MagicMock()
            mock_response.text = json.dumps(MOCK_STRUCTURED_ANALYSIS)
            mock_client.models.generate_content.return_value = mock_response
            mock_get_client.return_value = mock_client

            code = "def find_max(numbers):\n    return max(numbers)"
            response = self.client.post("/api/analyze", json={
                "code": code,
                "learning_level": "Beginner",
            })
            self.assertEqual(response.status_code, 200)
            data = response.json()

            # Verify structured fields
            self.assertTrue(data["success"])
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["detected_language"], "Python")
            self.assertIn(data["confidence"], ("high", "moderate"))
            self.assertEqual(data["overall_purpose"], MOCK_STRUCTURED_ANALYSIS["overall_purpose"])
            self.assertEqual(data["how_it_works"], MOCK_STRUCTURED_ANALYSIS["how_it_works"])
            self.assertEqual(len(data["line_by_line"]), 2)
            self.assertEqual(data["line_by_line"][0]["line"], 1)
            self.assertEqual(len(data["variables"]), 1)
            self.assertEqual(len(data["functions"]), 1)
            self.assertEqual(data["algorithm_logic"], MOCK_STRUCTURED_ANALYSIS["algorithm_logic"])
            self.assertEqual(data["time_complexity"], MOCK_STRUCTURED_ANALYSIS["time_complexity"])
            self.assertEqual(data["space_complexity"], MOCK_STRUCTURED_ANALYSIS["space_complexity"])
            self.assertEqual(len(data["potential_issues"]), 1)
            self.assertEqual(len(data["key_learning_points"]), 3)

    # -------------------------------------------------------------
    # 20. Existing API Behavior: LLM Error Handling
    # -------------------------------------------------------------
    def test_20_missing_api_key_returns_503(self):
        """Unset or placeholder API key returns HTTP 503."""
        with patch.dict("os.environ", {"GEMINI_API_KEY": "YOUR_KEY_HERE"}):
            response = self.client.post("/api/analyze", json={
                "code": "def hello(): pass",
                "learning_level": "Beginner",
            })
            self.assertEqual(response.status_code, 503)
            self.assertIn("Gemini API key is not configured", response.json()["detail"])

    def test_20_missing_model_config_returns_503(self):
        """Missing GEMINI_MODEL env var returns HTTP 503."""
        with patch.dict("os.environ", {"GEMINI_MODEL": "", "GEMINI_API_KEY": "dummy_key"}):
            response = self.client.post("/api/analyze", json={
                "code": "def hello(): pass",
                "learning_level": "Beginner",
            })
            self.assertEqual(response.status_code, 503)
            self.assertIn("GEMINI_MODEL is not configured", response.json()["detail"])

    @patch("app.services.llm_service.get_gemini_client")
    def test_20_unavailable_model_returns_503(self, mock_get_client):
        """Unavailable model raises clear 503 error."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("404 Model not found")
        mock_get_client.return_value = mock_client

        with patch.dict("os.environ", {"GEMINI_MODEL": "invalid-model-x", "GEMINI_API_KEY": "dummy_key"}):
            response = self.client.post("/api/analyze", json={
                "code": "def hello(): pass",
                "learning_level": "Beginner",
            })
            self.assertEqual(response.status_code, 503)
            self.assertIn("unavailable", response.json()["detail"].lower())

    @patch("app.services.llm_service.get_gemini_client")
    def test_20_rate_limit_returns_502(self, mock_get_client):
        """Rate limit error raises 502 with friendly user message."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("429 ResourceExhausted: Quota exceeded")
        mock_get_client.return_value = mock_client

        response = self.client.post("/api/analyze", json={
            "code": "def hello(): pass",
            "learning_level": "Beginner",
        })
        self.assertEqual(response.status_code, 502)
        self.assertIn("rate limits", response.json()["detail"].lower())

    @patch("app.services.llm_service.get_gemini_client")
    def test_20_timeout_returns_502(self, mock_get_client):
        """Timeout error raises 502 with friendly message."""
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("Request timed out after 30s")
        mock_get_client.return_value = mock_client

        response = self.client.post("/api/analyze", json={
            "code": "def hello(): pass",
            "learning_level": "Beginner",
        })
        self.assertEqual(response.status_code, 502)
        self.assertIn("timed out", response.json()["detail"].lower())

    def test_prompt_format(self):
        """Educational prompt strictly follows required Step 4 guidelines."""
        prompt = build_educational_prompt("print('hi')", "Python", "Beginner", confidence="high")
        self.assertIn("You are AI CodeMentor, an expert educational programming tutor.", prompt)
        self.assertIn("PARTIAL SNIPPETS ARE VALID", prompt)
        self.assertIn("PRESERVE CODE INTEGRITY", prompt)
        self.assertIn("NO INVENTED IDENTIFIERS", prompt)
        self.assertIn("TIME & SPACE COMPLEXITY", prompt)
        self.assertIn("Target Programming Language: Python", prompt)
        self.assertIn("Learning Level: Beginner", prompt)


if __name__ == "__main__":
    unittest.main()
