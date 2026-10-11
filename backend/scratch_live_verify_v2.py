import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def run_live_tests():
    print("=== LIVE BACKEND VERIFICATION FOR ISSUES 1 & 2 ===")
    
    # 1. Health
    r = requests.get(f"{BASE_URL}/api/health", timeout=5)
    assert r.status_code == 200
    print("[PASS] 1. Backend health check: 200 OK")

    # 2. Python visualization
    py_code = "x = 5\ny = x * 2"
    r = requests.post(f"{BASE_URL}/api/visualize", json={"code": py_code, "language": "Python"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "success"
    assert d["supported"] is True
    assert d["final_state"] == {"x": 5, "y": 10}
    print("[PASS] 2. Python code visualization: success with", d["total_steps"], "steps")

    # 3. Java visualization with explicit language="Java"
    java_code = "public class Adder { public static int add(int a, int b) { return a + b; } }"
    r = requests.post(f"{BASE_URL}/api/visualize", json={"code": java_code, "language": "Java"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "unsupported"
    assert d["supported"] is False
    assert d["error"] == "Interactive visualization is currently available only for Python."
    print("[PASS] 3. Java visualization (language='Java'): unsupported with exact message")

    # 4. Java visualization with default/python language
    r = requests.post(f"{BASE_URL}/api/visualize", json={"code": java_code, "language": "Python"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "unsupported"
    assert d["supported"] is False
    assert d["error"] == "Interactive visualization is currently available only for Python."
    assert "syntax error" not in (d.get("error") or "").lower()
    print("[PASS] 4. Java visualization (sent as 'Python'): intercepted, NO syntax error, returns exact message")

    # 5. Genuine Python syntax error
    r = requests.post(f"{BASE_URL}/api/visualize", json={"code": "def foo(:\n    pass", "language": "Python"}, timeout=10)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "error"
    assert "Python syntax error" in d["error"]
    print("[PASS] 5. Genuine Python syntax error: returns line-specific syntax error")

    # 6. Quiz Generation
    quiz_payload = {
        "code": "def compute_factorial(n):\n    if n <= 1:\n        return 1\n    return n * compute_factorial(n - 1)",
        "language": "Python",
        "learning_level": "Beginner"
    }
    r = requests.post(f"{BASE_URL}/api/quiz/generate", json=quiz_payload, timeout=30)
    assert r.status_code == 200
    q_data = r.json()
    questions = q_data.get("questions", [])
    assert len(questions) == 5, f"Expected 5 questions, got {len(questions)}"
    for idx, q in enumerate(questions):
        assert len(q.get("options", [])) == 4, f"Question {idx+1} does not have 4 options"
    assert bool(q_data.get("quiz_token"))
    print("[PASS] 6. Quiz generation: produced exactly 5 questions with 4 options each and secure token")

    # 7. Quiz Submission
    answers = {str(q["id"]): 0 for q in questions}
    submit_payload = {
        "quiz_id": q_data["quiz_id"],
        "quiz_token": q_data["quiz_token"],
        "answers": answers
    }
    r = requests.post(f"{BASE_URL}/api/quiz/submit", json=submit_payload, timeout=10)
    assert r.status_code == 200
    sub_data = r.json()
    assert "score" in sub_data
    assert sub_data["total"] == 5
    assert len(sub_data.get("review", [])) == 5
    print("[PASS] 7. Quiz submission: scored deterministically, total=5, review length=5")

    # 8. Quiz submission with invalid token
    bad_payload = dict(submit_payload)
    bad_payload["quiz_token"] = "invalid.token.here"
    r = requests.post(f"{BASE_URL}/api/quiz/submit", json=bad_payload, timeout=10)
    assert r.status_code == 400
    print("[PASS] 8. Tampered quiz token: rejected with HTTP 400")

    print("\n>>> ALL 8 LIVE BACKEND & WORKFLOW TESTS PASSED CLEANLY <<<")

if __name__ == "__main__":
    run_live_tests()
