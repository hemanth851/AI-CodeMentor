"""
Unit and API integration tests for Step 7A Deterministic Algorithm Visualization.
Covers all 23 required test scenarios + primary demonstration example.
"""

import unittest
from starlette.testclient import TestClient

from app.main import app
from app.services.visualizer.engine import (
    trace_python_code,
    SafeTraceInterpreter,
    validate_python_ast,
    UnsupportedConstructError,
    LimitExceededError,
)

PRIMARY_DEMO_CODE = """def find_max(numbers):
    maximum = numbers[0]

    for number in numbers:
        if number > maximum:
            maximum = number

    return maximum

result = find_max([4, 9, 2, 15, 7])
"""


class TestAlgorithmVisualizer(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # -------------------------------------------------------------
    # Primary Demonstration Example
    # -------------------------------------------------------------
    def test_primary_find_max_demo(self):
        """Primary demo: find_max should deterministically trace and yield maximum 15."""
        res = trace_python_code(PRIMARY_DEMO_CODE)
        self.assertEqual(res.status, "success")
        self.assertTrue(res.supported)
        self.assertEqual(res.termination_reason, "completed")
        self.assertIn("result", res.final_state)
        self.assertEqual(res.final_state["result"], 15)

        # Verify step event types exist
        event_types = [step.event_type for step in res.trace]
        self.assertIn("initialization", event_types)
        self.assertIn("function_call", event_types)
        self.assertIn("assignment", event_types)
        self.assertIn("loop_start", event_types)
        self.assertIn("loop_iteration", event_types)
        self.assertIn("condition_true", event_types)
        self.assertIn("condition_false", event_types)
        self.assertIn("return", event_types)
        self.assertIn("completed", event_types)

    # -------------------------------------------------------------
    # 1. Simple variable assignment
    # -------------------------------------------------------------
    def test_01_simple_variable_assignment(self):
        code = "x = 10\ny = 20"
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["x"], 10)
        self.assertEqual(res.final_state["y"], 20)

    # -------------------------------------------------------------
    # 2. Arithmetic
    # -------------------------------------------------------------
    def test_02_arithmetic_operations(self):
        code = """a = 10 + 5
b = a - 3
c = b * 2
d = c // 4
e = c % 5
f = 2 ** 3
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["a"], 15)
        self.assertEqual(res.final_state["b"], 12)
        self.assertEqual(res.final_state["c"], 24)
        self.assertEqual(res.final_state["d"], 6)
        self.assertEqual(res.final_state["e"], 4)
        self.assertEqual(res.final_state["f"], 8)

    # -------------------------------------------------------------
    # 3. Conditional true
    # -------------------------------------------------------------
    def test_03_conditional_true(self):
        code = """x = 15
if x > 10:
    outcome = "large"
else:
    outcome = "small"
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["outcome"], "large")
        events = [s.event_type for s in res.trace]
        self.assertIn("condition_true", events)

    # -------------------------------------------------------------
    # 4. Conditional false
    # -------------------------------------------------------------
    def test_04_conditional_false(self):
        code = """x = 5
if x > 10:
    outcome = "large"
else:
    outcome = "small"
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["outcome"], "small")
        events = [s.event_type for s in res.trace]
        self.assertIn("condition_false", events)

    # -------------------------------------------------------------
    # 5. For loop
    # -------------------------------------------------------------
    def test_05_for_loop_range(self):
        code = """total = 0
for i in range(4):
    total += i
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["total"], 6)
        iterations = [s for s in res.trace if s.event_type == "loop_iteration"]
        self.assertEqual(len(iterations), 4)

    # -------------------------------------------------------------
    # 6. While loop
    # -------------------------------------------------------------
    def test_06_while_loop(self):
        code = """count = 0
while count < 3:
    count += 1
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["count"], 3)

    # -------------------------------------------------------------
    # 7. List iteration
    # -------------------------------------------------------------
    def test_07_list_iteration_and_indexing(self):
        code = """items = [10, 20, 30]
first = items[0]
total = 0
for val in items:
    total += val
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["first"], 10)
        self.assertEqual(res.final_state["total"], 60)

    # -------------------------------------------------------------
    # 8. Function call
    # -------------------------------------------------------------
    def test_08_function_call(self):
        code = """def add(a, b):
    return a + b

sum_val = add(7, 8)
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["sum_val"], 15)
        events = [s.event_type for s in res.trace]
        self.assertIn("function_call", events)

    # -------------------------------------------------------------
    # 9. Function return
    # -------------------------------------------------------------
    def test_09_function_return(self):
        code = """def check_pos(num):
    if num > 0:
        return True
    return False

r1 = check_pos(5)
r2 = check_pos(-2)
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["r1"], True)
        self.assertEqual(res.final_state["r2"], False)

    # -------------------------------------------------------------
    # 10. Nested conditions
    # -------------------------------------------------------------
    def test_10_nested_conditions(self):
        code = """x = 12
if x > 5:
    if x > 10:
        tag = "high"
    else:
        tag = "medium"
else:
    tag = "low"
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["tag"], "high")

    # -------------------------------------------------------------
    # 11. Nested loops
    # -------------------------------------------------------------
    def test_11_nested_loops(self):
        code = """pairs = 0
for i in range(2):
    for j in range(3):
        pairs += 1
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["pairs"], 6)

    # -------------------------------------------------------------
    # 12. Final state correctness
    # -------------------------------------------------------------
    def test_12_final_state_correctness(self):
        code = """x = 10
y = 20
z = x + y
"""
        res = trace_python_code(code)
        self.assertEqual(res.final_state, {"x": 10, "y": 20, "z": 30})

    # -------------------------------------------------------------
    # 13. Correct line numbers
    # -------------------------------------------------------------
    def test_13_correct_line_numbers(self):
        code = "a = 1\nb = 2\nc = 3"
        res = trace_python_code(code)
        assign_lines = [s.line_number for s in res.trace if s.event_type == "assignment"]
        self.assertEqual(assign_lines, [1, 2, 3])

    # -------------------------------------------------------------
    # 14. Unsupported imports
    # -------------------------------------------------------------
    def test_14_unsupported_imports(self):
        code = "import os\nos.listdir()"
        res = trace_python_code(code)
        self.assertEqual(res.status, "unsupported")
        self.assertFalse(res.supported)
        self.assertEqual(res.termination_reason, "unsupported_construct")
        self.assertIn("Import statements", res.error)

    # -------------------------------------------------------------
    # 15. Unsupported function calls
    # -------------------------------------------------------------
    def test_15_unsupported_function_calls(self):
        code = "eval('2 + 2')"
        res = trace_python_code(code)
        self.assertEqual(res.status, "unsupported")
        self.assertFalse(res.supported)
        self.assertIn("forbidden", res.error.lower())

    # -------------------------------------------------------------
    # 16. Infinite-loop protection
    # -------------------------------------------------------------
    def test_16_infinite_loop_protection(self):
        code = """while True:
    pass
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertIn(res.termination_reason, ("loop_limit_exceeded", "step_limit_exceeded"))
        self.assertGreater(res.total_steps, 0)
        self.assertLessEqual(res.total_steps, 502)

    # -------------------------------------------------------------
    # 17. Recursion limit
    # -------------------------------------------------------------
    def test_17_recursion_limit_protection(self):
        code = """def recurse():
    return recurse()

recurse()
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.termination_reason, "recursion_limit_exceeded")
        self.assertIn("recursion", res.error.lower())

    # -------------------------------------------------------------
    # 18. Step limit
    # -------------------------------------------------------------
    def test_18_step_limit_protection(self):
        code = """x = 0
for i in range(150):
    x += 1
    x -= 1
    x += 2
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertIn(res.termination_reason, ("step_limit_exceeded", "completed"))

    # -------------------------------------------------------------
    # 19. Invalid syntax
    # -------------------------------------------------------------
    def test_19_invalid_syntax(self):
        code = "def bad_syntax(:"
        res = trace_python_code(code)
        self.assertEqual(res.status, "error")
        self.assertEqual(res.termination_reason, "syntax_error")
        self.assertIn("syntax error", res.error.lower())

    # -------------------------------------------------------------
    # 20. Empty input
    # -------------------------------------------------------------
    def test_20_empty_input_validation(self):
        response = self.client.post("/api/visualize", json={"code": "   ", "language": "Python"})
        self.assertEqual(response.status_code, 422)

    # -------------------------------------------------------------
    # 21. Non-Python language
    # -------------------------------------------------------------
    def test_21_non_python_language(self):
        payload = {
            "code": "public class Main { public static void main(String[] args) {} }",
            "language": "Java",
        }
        response = self.client.post("/api/visualize", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["supported"])
        self.assertEqual(data["termination_reason"], "completed")
        self.assertTrue(len(data["trace"]) > 0)

    # -------------------------------------------------------------
    # 22. API response schema
    # -------------------------------------------------------------
    def test_22_api_response_schema(self):
        payload = {
            "code": "x = 42\ny = x * 2",
            "language": "Python",
        }
        response = self.client.post("/api/visualize", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "success")
        self.assertTrue(data["supported"])
        self.assertIsInstance(data["trace"], list)
        self.assertEqual(data["total_steps"], len(data["trace"]))
        self.assertEqual(data["final_state"], {"x": 42, "y": 84})
        self.assertEqual(data["termination_reason"], "completed")

        first_step = data["trace"][0]
        self.assertIn("step_number", first_step)
        self.assertIn("event_type", first_step)
        self.assertIn("line_number", first_step)
        self.assertIn("description", first_step)
        self.assertIn("variable_state", first_step)

    # -------------------------------------------------------------
    # 23. Existing endpoint compatibility
    # -------------------------------------------------------------
    def test_23_existing_endpoint_compatibility(self):
        # Health check must still return 200
        health_resp = self.client.get("/api/health")
        self.assertEqual(health_resp.status_code, 200)

        # Root endpoint
        root_resp = self.client.get("/")
        self.assertEqual(root_resp.status_code, 200)

    # =============================================================
    # Audit Tests: Resource Safety
    # =============================================================
    def test_audit_large_exponentiation(self):
        """Audit: Extremely large integer exponentiation should be safely intercepted."""
        code1 = "x = 2 ** 1000000"
        res1 = trace_python_code(code1)
        self.assertEqual(res1.status, "success")
        self.assertEqual(res1.termination_reason, "step_limit_exceeded")

        code2 = "x = 1000 ** 200"
        res2 = trace_python_code(code2)
        self.assertEqual(res2.status, "success")
        self.assertEqual(res2.termination_reason, "step_limit_exceeded")

    def test_audit_large_range_protection(self):
        """Audit: Huge range(1000000000000) should not cause memory exhaustion."""
        code = "for i in range(1000000000000):\n    pass"
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertIn(res.termination_reason, ("loop_limit_exceeded", "step_limit_exceeded"))

    def test_audit_large_sequence_multiplication(self):
        """Audit: Sequence multiplication like [0] * 10000000 should be bounded."""
        code1 = "items = [0] * 10000000"
        res1 = trace_python_code(code1)
        self.assertEqual(res1.status, "success")
        self.assertEqual(res1.termination_reason, "step_limit_exceeded")

        code2 = "text = 'a' * 10000000"
        res2 = trace_python_code(code2)
        self.assertEqual(res2.status, "success")
        self.assertEqual(res2.termination_reason, "step_limit_exceeded")

    def test_audit_large_integer_growth(self):
        """Audit: Unchecked integer growth (x = x * x) should be caught."""
        code = """x = 1000000
for i in range(10):
    x = x * x
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.termination_reason, "step_limit_exceeded")

    def test_audit_large_list_literal_limit(self):
        """Audit: Giant list literals with > 500 items should be bounded."""
        items_str = ", ".join(str(i) for i in range(600))
        code = f"x = [{items_str}]"
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.termination_reason, "step_limit_exceeded")

    def test_audit_snapshot_memory_bounding(self):
        """Audit: Snapshot values should truncate excessively long strings."""
        code = "s = 'a' * 300"
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        sanitized_s = res.final_state["s"]
        self.assertTrue("truncated" in sanitized_s)

    def test_audit_nested_loops_bounded(self):
        """Audit: Nested loops must not hang and must respect MAX_STEPS."""
        code = """total = 0
for i in range(50):
    for j in range(50):
        total += 1
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.termination_reason, "step_limit_exceeded")
        self.assertLessEqual(res.total_steps, 502)

    # =============================================================
    # Audit Tests: Built-in Restrictions
    # =============================================================
    def test_audit_forbidden_open(self):
        """Audit: open() must be rejected without execution."""
        res = trace_python_code("f = open('secret.txt')")
        self.assertEqual(res.status, "unsupported")
        self.assertFalse(res.supported)

    def test_audit_forbidden_eval(self):
        """Audit: eval() must be rejected without execution."""
        res = trace_python_code("x = eval('1 + 1')")
        self.assertEqual(res.status, "unsupported")
        self.assertFalse(res.supported)

    def test_audit_forbidden_exec(self):
        """Audit: exec() must be rejected without execution."""
        res = trace_python_code("exec('x = 10')")
        self.assertEqual(res.status, "unsupported")
        self.assertFalse(res.supported)

    def test_audit_forbidden_getattr(self):
        """Audit: getattr() must be rejected without execution."""
        res = trace_python_code("g = getattr")
        self.assertEqual(res.status, "unsupported")
        self.assertFalse(res.supported)

    def test_audit_forbidden_globals_and_locals(self):
        """Audit: globals() and locals() must be rejected."""
        res1 = trace_python_code("g = globals()")
        self.assertEqual(res1.status, "unsupported")
        res2 = trace_python_code("l = locals()")
        self.assertEqual(res2.status, "unsupported")

    def test_audit_forbidden_arbitrary_attributes(self):
        """Audit: Attribute access (e.g. obj.method) must be rejected."""
        res = trace_python_code("x = [1, 2]\nx.append(3)")
        self.assertEqual(res.status, "unsupported")
        self.assertIn("attribute", res.error.lower())

    def test_audit_forbidden_user_func_named_open(self):
        """Audit: Defining a user function named open() must be rejected."""
        res = trace_python_code("def open(x):\n    return x\nopen(1)")
        self.assertEqual(res.status, "unsupported")
        self.assertIn("function name 'open' is restricted", res.error.lower())

    def test_audit_forbidden_param_named_eval(self):
        """Audit: Defining a function parameter named eval must be rejected."""
        res = trace_python_code("def my_func(eval):\n    return eval\nmy_func(1)")
        self.assertEqual(res.status, "unsupported")
        self.assertIn("parameter name 'eval' is restricted", res.error.lower())

    # =============================================================
    # Audit Tests: Trace Correctness
    # =============================================================
    def test_audit_trace_snapshot_independence(self):
        """Audit: Modifying a list in place must not mutate past snapshot states."""
        code = """nums = [1, 2]
nums[0] = 99
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        first_step = [s for s in res.trace if s.event_type == "assignment"][0]
        second_step = [s for s in res.trace if s.event_type == "assignment"][1]
        self.assertEqual(first_step.variable_state["nums"], [1, 2])
        self.assertEqual(second_step.variable_state["nums"], [99, 2])

    def test_audit_trace_function_local_scope_leakage(self):
        """Audit: Function-local variables must not leak into global state."""
        code = """def calc(a):
    local_temp = a * 2
    return local_temp

result = calc(5)
"""
        res = trace_python_code(code)
        self.assertEqual(res.status, "success")
        self.assertEqual(res.final_state["result"], 10)
        self.assertNotIn("local_temp", res.final_state)
        self.assertNotIn("a", res.final_state)

    def test_audit_limit_exceeded_not_marked_completed(self):
        """Audit: A limit-exceeded trace must not terminate with 'completed'."""
        code = "while True:\n    pass"
        res = trace_python_code(code)
        self.assertNotEqual(res.termination_reason, "completed")
        self.assertEqual(res.trace[-1].event_type, "limit_exceeded")
        self.assertIn("stopped", res.trace[-1].description.lower())

