"""
Comprehensive Tests for AI CodeMentor Step 5 — Static Code Analysis Engine.
Covers all 25 required test categories:
1. Variable detection
2. Function detection
3. Parameter detection
4. Loop detection
5. Nested-loop detection
6. Conditional detection
7. Recursion detection
8. Import/include detection
9. Single loop complexity evidence
10. Nested loops complexity evidence
11. Recursion complexity evidence
12. Sorting detection
13. Insufficient evidence
14. Obvious syntax issue
15. Definite issue
16. Possible issue
17. No issue
18. Partial Python snippet
19. Partial C++ snippet
20. Partial JavaScript snippet
21. Static analysis passed to Gemini
22. Static-analysis failure does not break AI explanation
23. Existing language detection still works
24. Existing structured response still works
25. Existing /api/health still works
"""

import json
import unittest
from unittest.mock import MagicMock, patch
from starlette.testclient import TestClient

from app.main import app
from app.services.static_analyzer import analyze_static
from app.services.static_analyzer.python_analyzer import analyze_python
from app.services.static_analyzer.generic_analyzer import analyze_generic
from app.services.detector import detect_language
from app.services.llm_service import build_educational_prompt
from app.models.analysis import CodeAnalysis

MOCK_STRUCTURED_ANALYSIS = {
    "overall_purpose": "Computes factorial of a given number recursively.",
    "how_it_works": "Base case returns 1 when n <= 1, else returns n multiplied by factorial of n - 1.",
    "line_by_line": [
        {
            "line": 1,
            "code": "def factorial(n):",
            "explanation": "Defines recursive function factorial with parameter n.",
        },
        {
            "line": 2,
            "code": "    if n <= 1:",
            "explanation": "Base case check for recursion termination.",
        },
        {
            "line": 3,
            "code": "        return 1",
            "explanation": "Returns 1 for 0 or 1.",
        },
        {
            "line": 4,
            "code": "    return n * factorial(n - 1)",
            "explanation": "Recursive call multiplying n by factorial(n - 1).",
        },
    ],
    "variables": [
        {"name": "n", "purpose": "Input number to compute factorial of."}
    ],
    "functions": [
        {
            "name": "factorial",
            "parameters": ["n"],
            "purpose": "Calculates factorial recursively.",
            "return_value": "Integer product.",
        }
    ],
    "algorithm_logic": "Divide and conquer recursion.",
    "time_complexity": "O(n) linear recursive calls.",
    "space_complexity": "O(n) call stack frames.",
    "potential_issues": [],
    "key_learning_points": [
        "Base case prevention of stack overflow",
        "Call stack memory",
    ],
}


class TestStaticCodeAnalysisEngineStep5(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # -------------------------------------------------------------
    # 1. Variable detection
    # -------------------------------------------------------------
    def test_01_variable_detection(self):
        """Detect variables in Python and other supported languages."""
        # Python
        py_code = "x = 10\ny = 20\ntotal = x + y"
        res_py = analyze_static(py_code, "Python")
        self.assertIn("x", res_py.variables)
        self.assertIn("y", res_py.variables)
        self.assertIn("total", res_py.variables)

        # JavaScript
        js_code = "const score = 100;\nlet playerName = 'Alice';"
        res_js = analyze_static(js_code, "JavaScript")
        self.assertIn("score", res_js.variables)
        self.assertIn("playerName", res_js.variables)

        # C++
        cpp_code = "int counter = 0;\ndouble rate = 5.5;"
        res_cpp = analyze_static(cpp_code, "C++")
        self.assertIn("counter", res_cpp.variables)
        self.assertIn("rate", res_cpp.variables)

    # -------------------------------------------------------------
    # 2. Function detection
    # -------------------------------------------------------------
    def test_02_function_detection(self):
        """Detect declared functions across languages."""
        # Python
        py_code = "def calculate_sum(a, b):\n    return a + b\n\ndef greet():\n    print('hi')"
        res_py = analyze_static(py_code, "Python")
        func_names = [f["name"] for f in res_py.functions]
        self.assertEqual(len(res_py.functions), 2)
        self.assertIn("calculate_sum", func_names)
        self.assertIn("greet", func_names)

        # Java
        java_code = "public int multiply(int a, int b) {\n    return a * b;\n}"
        res_java = analyze_static(java_code, "Java")
        self.assertEqual(len(res_java.functions), 1)
        self.assertEqual(res_java.functions[0]["name"], "multiply")

        # Go
        go_code = "func processData(item string) bool {\n    return true\n}"
        res_go = analyze_static(go_code, "Go")
        self.assertEqual(len(res_go.functions), 1)
        self.assertEqual(res_go.functions[0]["name"], "processData")

    # -------------------------------------------------------------
    # 3. Parameter detection
    # -------------------------------------------------------------
    def test_03_parameter_detection(self):
        """Accurately identify function parameters."""
        # Python
        py_code = "def divide(numerator, denominator, precision=2):\n    return round(numerator / denominator, precision)"
        res_py = analyze_static(py_code, "Python")
        self.assertEqual(len(res_py.functions), 1)
        params = res_py.functions[0]["parameters"]
        self.assertIn("numerator", params)
        self.assertIn("denominator", params)
        self.assertIn("precision", params)

        # TypeScript
        ts_code = "function findUser(id: number, activeOnly: boolean) {\n    return null;\n}"
        res_ts = analyze_static(ts_code, "TypeScript")
        self.assertEqual(len(res_ts.functions), 1)
        self.assertEqual(len(res_ts.functions[0]["parameters"]), 2)

    # -------------------------------------------------------------
    # 4. Loop detection
    # -------------------------------------------------------------
    def test_04_loop_detection(self):
        """Detect single for and while loops."""
        # Python for
        res1 = analyze_static("for i in range(10):\n    print(i)", "Python")
        self.assertEqual(res1.loops.count, 1)
        self.assertFalse(res1.loops.nested)

        # Python while
        res2 = analyze_static("while count < 5:\n    count += 1", "Python")
        self.assertEqual(res2.loops.count, 1)

        # C++ while
        res3 = analyze_static("while (n > 0) {\n    n--;\n}", "C++")
        self.assertEqual(res3.loops.count, 1)

    # -------------------------------------------------------------
    # 5. Nested-loop detection
    # -------------------------------------------------------------
    def test_05_nested_loop_detection(self):
        """Identify nested loops across Python and C-family languages."""
        # Python nested loops
        py_code = "for i in range(n):\n    for j in range(n):\n        print(i, j)"
        res_py = analyze_static(py_code, "Python")
        self.assertEqual(res_py.loops.count, 2)
        self.assertTrue(res_py.loops.nested)
        self.assertTrue(res_py.complexity_evidence.nested_loops)

        # C++ nested loops
        cpp_code = "for (int i = 0; i < n; i++) {\n    for (int j = 0; j < n; j++) {\n        cout << i << j;\n    }\n}"
        res_cpp = analyze_static(cpp_code, "C++")
        self.assertEqual(res_cpp.loops.count, 2)
        self.assertTrue(res_cpp.loops.nested)
        self.assertTrue(res_cpp.complexity_evidence.nested_loops)

    # -------------------------------------------------------------
    # 6. Conditional detection
    # -------------------------------------------------------------
    def test_06_conditional_detection(self):
        """Detect if, elif, else, and switch statements."""
        # Python
        py_code = "if score > 90:\n    grade = 'A'\nelif score > 80:\n    grade = 'B'\nelse:\n    grade = 'C'"
        res_py = analyze_static(py_code, "Python")
        self.assertGreaterEqual(res_py.conditionals.count, 1)
        self.assertTrue(res_py.conditionals.has_else or res_py.conditionals.has_elif)

        # JavaScript switch & if
        js_code = "if (x > 0) { console.log(1); } else { console.log(0); }"
        res_js = analyze_static(js_code, "JavaScript")
        self.assertGreaterEqual(res_js.conditionals.count, 1)
        self.assertTrue(res_js.conditionals.has_else)

    # -------------------------------------------------------------
    # 7. Recursion detection
    # -------------------------------------------------------------
    def test_07_recursion_detection(self):
        """Detect recursive function calls in Python and Java."""
        # Python recursion
        py_code = "def factorial(n):\n    if n <= 1:\n        return 1\n    return n * factorial(n - 1)"
        res_py = analyze_static(py_code, "Python")
        self.assertTrue(res_py.recursion_detected)
        self.assertTrue(res_py.complexity_evidence.recursion_detected)

        # Java recursion
        java_code = "int fibonacci(int n) {\n    if (n <= 1) return n;\n    return fibonacci(n - 1) + fibonacci(n - 2);\n}"
        res_java = analyze_static(java_code, "Java")
        self.assertTrue(res_java.recursion_detected)
        self.assertTrue(res_java.complexity_evidence.recursion_detected)

    # -------------------------------------------------------------
    # 8. Import/include detection
    # -------------------------------------------------------------
    def test_08_import_include_detection(self):
        """Detect imported modules and included headers."""
        # Python imports
        py_code = "import math\nfrom os import path\nprint(math.pi)"
        res_py = analyze_static(py_code, "Python")
        self.assertIn("math", res_py.imports)
        self.assertTrue(any("path" in imp for imp in res_py.imports))

        # C++ includes
        cpp_code = "#include <iostream>\n#include <vector>\nint main() { return 0; }"
        res_cpp = analyze_static(cpp_code, "C++")
        self.assertTrue(any("iostream" in inc for inc in res_cpp.imports))
        self.assertTrue(any("vector" in inc for inc in res_cpp.imports))

    # -------------------------------------------------------------
    # 9. Single loop complexity evidence
    # -------------------------------------------------------------
    def test_09_complexity_evidence_single_loop(self):
        """Single loop produces loops=1, nested_loops=False."""
        code = "for i in range(10):\n    print(i)"
        res = analyze_static(code, "Python")
        self.assertEqual(res.complexity_evidence.loops, 1)
        self.assertFalse(res.complexity_evidence.nested_loops)
        self.assertFalse(res.complexity_evidence.recursion_detected)

    # -------------------------------------------------------------
    # 10. Nested loops complexity evidence
    # -------------------------------------------------------------
    def test_10_complexity_evidence_nested_loops(self):
        """Nested loops produce loops=2, nested_loops=True."""
        code = "for i in range(n):\n    for j in range(n):\n        print(i, j)"
        res = analyze_static(code, "Python")
        self.assertEqual(res.complexity_evidence.loops, 2)
        self.assertTrue(res.complexity_evidence.nested_loops)

    # -------------------------------------------------------------
    # 11. Recursion complexity evidence
    # -------------------------------------------------------------
    def test_11_complexity_evidence_recursion(self):
        """Recursion evidence is accurately flagged."""
        code = "def countdown(n):\n    if n <= 0: return\n    countdown(n - 1)"
        res = analyze_static(code, "Python")
        self.assertTrue(res.complexity_evidence.recursion_detected)

    # -------------------------------------------------------------
    # 12. Sorting detection
    # -------------------------------------------------------------
    def test_12_sorting_detection(self):
        """Identify built-in sorting operations across languages."""
        # Python .sort()
        res1 = analyze_static("items.sort()", "Python")
        self.assertTrue(res1.complexity_evidence.sorting_detected)

        # Python sorted()
        res2 = analyze_static("sorted_items = sorted(items)", "Python")
        self.assertTrue(res2.complexity_evidence.sorting_detected)

        # Java Arrays.sort
        res3 = analyze_static("Arrays.sort(arr);", "Java")
        self.assertTrue(res3.complexity_evidence.sorting_detected)

        # C++ std::sort
        res4 = analyze_static("std::sort(vec.begin(), vec.end());", "C++")
        self.assertTrue(res4.complexity_evidence.sorting_detected)

    # -------------------------------------------------------------
    # 13. Insufficient evidence
    # -------------------------------------------------------------
    def test_13_insufficient_evidence(self):
        """Snippet without algorithmic structures yields no loop/recursion indicators."""
        code = "x = 10\nprint(x)"
        res = analyze_static(code, "Python")
        self.assertEqual(res.complexity_evidence.loops, 0)
        self.assertFalse(res.complexity_evidence.nested_loops)
        self.assertFalse(res.complexity_evidence.recursion_detected)
        self.assertFalse(res.complexity_evidence.sorting_detected)

    # -------------------------------------------------------------
    # 14. Obvious syntax issue
    # -------------------------------------------------------------
    def test_14_obvious_syntax_issue(self):
        """Unrecoverable syntax errors produce a syntax issue."""
        code = "def foo(:\n    pass"
        res = analyze_static(code, "Python")
        self.assertTrue(any(issue.type == "definite" and "syntax" in issue.description.lower() for issue in res.issues))

    # -------------------------------------------------------------
    # 15. Definite issue
    # -------------------------------------------------------------
    def test_15_definite_issue(self):
        """Unreachable code, empty except, or assignment in condition are flagged as definite."""
        # Python unreachable code after return
        py_unreachable = "def get_val():\n    return 42\n    print('Never reached')"
        res_py = analyze_static(py_unreachable, "Python")
        unreachable_issues = [i for i in res_py.issues if i.type == "definite" and "unreachable" in i.description.lower()]
        self.assertGreaterEqual(len(unreachable_issues), 1)

        # Python empty except block
        py_empty_except = "try:\n    risky()\nexcept Exception:\n    pass"
        res_except = analyze_static(py_empty_except, "Python")
        except_issues = [i for i in res_except.issues if i.type == "definite" and "empty exception" in i.description.lower()]
        self.assertGreaterEqual(len(except_issues), 1)

        # C assignment in condition
        c_assign_if = "int check(int x) {\n    if (x = 10) {\n        return 1;\n    }\n    return 0;\n}"
        res_c = analyze_static(c_assign_if, "C")
        assign_issues = [i for i in res_c.issues if i.type == "definite" and "assignment" in i.description.lower()]
        self.assertGreaterEqual(len(assign_issues), 1)

    # -------------------------------------------------------------
    # 16. Possible issue
    # -------------------------------------------------------------
    def test_16_possible_issue(self):
        """Flag suspicious infinite loops or mutable defaults as possible issues."""
        # Python while True without exit
        py_infinite = "while True:\n    print('Looping forever')"
        res_inf = analyze_static(py_infinite, "Python")
        inf_issues = [i for i in res_inf.issues if i.type == "possible" and "infinite" in i.description.lower()]
        self.assertGreaterEqual(len(inf_issues), 1)

        # Python mutable default argument
        py_mutable_default = "def append_item(val, target_list=[]):\n    target_list.append(val)\n    return target_list"
        res_mut = analyze_static(py_mutable_default, "Python")
        mut_issues = [i for i in res_mut.issues if i.type == "possible" and "mutable default" in i.description.lower()]
        self.assertGreaterEqual(len(mut_issues), 1)

    # -------------------------------------------------------------
    # 17. No issue
    # -------------------------------------------------------------
    def test_17_no_issue(self):
        """Clean, idiomatic code produces zero issues."""
        code = "def add(a, b):\n    return a + b\n\nresult = add(2, 3)\nprint(result)"
        res = analyze_static(code, "Python")
        self.assertEqual(len(res.issues), 0)

    # -------------------------------------------------------------
    # 18. Partial Python snippet
    # -------------------------------------------------------------
    def test_18_partial_python_snippet(self):
        """Incomplete Python header is recovered and marked as partial."""
        code = "for i in range(10):"
        res = analyze_static(code, "Python")
        self.assertEqual(res.parse_status, "partial")
        self.assertEqual(res.loops.count, 1)
        self.assertIn("i", res.variables)

    # -------------------------------------------------------------
    # 19. Partial C++ snippet
    # -------------------------------------------------------------
    def test_19_partial_cpp_snippet(self):
        """Top-level C++ statements without main() analyzed as partial."""
        code = "int x = 10;\ncout << x;"
        res = analyze_static(code, "C++")
        self.assertEqual(res.parse_status, "partial")
        self.assertIn("x", res.variables)
        self.assertEqual(res.loops.count, 0)

    # -------------------------------------------------------------
    # 20. Partial JavaScript snippet
    # -------------------------------------------------------------
    def test_20_partial_js_snippet(self):
        """Partial JavaScript statement snippet analyzed gracefully."""
        code = "const limit = 50;\nconsole.log(limit);"
        res = analyze_static(code, "JavaScript")
        self.assertIn("limit", res.variables)
        self.assertIn(res.parse_status, ("partial", "success"))

    # -------------------------------------------------------------
    # 21. Static analysis passed to Gemini
    # -------------------------------------------------------------
    def test_21_static_analysis_passed_to_gemini(self):
        """Prompt includes deterministic static facts when static analysis succeeds."""
        static_res = analyze_static("for i in range(10):\n    print(i)", "Python")
        prompt = build_educational_prompt(
            code="for i in range(10):\n    print(i)",
            language="Python",
            learning_level="Beginner",
            confidence="high",
            static_analysis=static_res,
        )
        self.assertIn("STATIC CODE ANALYSIS (DETERMINISTIC FACTS)", prompt)
        self.assertIn("Loops (1)", prompt)
        self.assertIn("INSTRUCTIONS FOR USING STATIC ANALYSIS", prompt)

    # -------------------------------------------------------------
    # 22. Static-analysis failure does not break AI explanation
    # -------------------------------------------------------------
    def test_22_static_analysis_failure_does_not_break_ai_explanation(self):
        """If static analysis throws an unexpected error, endpoint proceeds gracefully."""
        with patch("app.api.analyze.analyze_static") as mock_static:
            mock_static.side_effect = RuntimeError("Simulated static analyzer crash")

            with patch("app.services.llm_service.get_gemini_client") as mock_get_client:
                mock_client = MagicMock()
                mock_resp = MagicMock()
                mock_resp.text = json.dumps(MOCK_STRUCTURED_ANALYSIS)
                mock_client.models.generate_content.return_value = mock_resp
                mock_get_client.return_value = mock_client

                response = self.client.post("/api/analyze", json={
                    "code": "def foo(): pass",
                    "learning_level": "Beginner",
                })
                self.assertEqual(response.status_code, 200)
                data = response.json()
                self.assertTrue(data["success"])
                self.assertEqual(data["status"], "success")
                # AI explanation is fully intact
                self.assertEqual(data["overall_purpose"], MOCK_STRUCTURED_ANALYSIS["overall_purpose"])

    # -------------------------------------------------------------
    # 23. Existing language detection still works
    # -------------------------------------------------------------
    def test_23_existing_language_detection_still_works(self):
        """Language detection functions accurately across supported languages."""
        py_res = detect_language("def add(a, b): return a + b")
        self.assertEqual(py_res.language, "Python")

        cpp_res = detect_language("#include <iostream>\nint main() { return 0; }")
        self.assertEqual(cpp_res.language, "C++")

        sql_res = detect_language("SELECT * FROM users WHERE active = 1;")
        self.assertEqual(sql_res.language, "SQL")

    # -------------------------------------------------------------
    # 24. Existing structured response still works
    # -------------------------------------------------------------
    def test_24_existing_structured_response_still_works(self):
        """Endpoint returns all structured fields plus new static_analysis field."""
        with patch("app.services.llm_service.get_gemini_client") as mock_get_client:
            mock_client = MagicMock()
            mock_resp = MagicMock()
            mock_resp.text = json.dumps(MOCK_STRUCTURED_ANALYSIS)
            mock_client.models.generate_content.return_value = mock_resp
            mock_get_client.return_value = mock_client

            code = "def factorial(n):\n    if n <= 1: return 1\n    return n * factorial(n - 1)"
            response = self.client.post("/api/analyze", json={
                "code": code,
                "learning_level": "Beginner",
            })
            self.assertEqual(response.status_code, 200)
            data = response.json()

            # Existing fields intact
            self.assertTrue(data["success"])
            self.assertEqual(data["status"], "success")
            self.assertEqual(data["overall_purpose"], MOCK_STRUCTURED_ANALYSIS["overall_purpose"])
            self.assertEqual(len(data["line_by_line"]), 4)
            self.assertEqual(len(data["variables"]), 1)
            self.assertEqual(len(data["functions"]), 1)
            self.assertEqual(len(data["key_learning_points"]), 2)

            # Step 5 new static_analysis field
            self.assertIn("static_analysis", data)
            static = data["static_analysis"]
            self.assertEqual(static["parse_status"], "success")
            self.assertEqual(static["structure"]["functions"], 1)
            self.assertTrue(static["structure"]["recursion"])
            self.assertTrue(static["complexity_evidence"]["recursion_detected"])

    # -------------------------------------------------------------
    # 25. Existing /api/health still works
    # -------------------------------------------------------------
    def test_25_existing_api_health_still_works(self):
        """GET /api/health returns HTTP 200 and healthy status."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["message"], "AI CodeMentor backend is running")


if __name__ == "__main__":
    unittest.main()
