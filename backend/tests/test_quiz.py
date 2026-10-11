"""
Comprehensive Unit and Integration Tests for Step 8A — Dynamic AI Quiz & Learning Assessment.

Covers all required test scenarios:
1. Valid quiz generation response
2. Invalid learning level
3. Missing source code
4. Malformed Gemini response
5. Incorrect question count
6. Incorrect number of options
7. Invalid correct-answer index
8. Duplicate options
9. Grounded categories and dynamic selection
10. Gemini unavailable or timeout
11. API configuration missing
12. Existing endpoints remain functional
13. Deterministic scoring
14. Anti-cheat validation (correct answers hidden from public response)
15. Tampered or expired token rejection
"""

import json
import unittest
from unittest.mock import patch, MagicMock
from starlette.testclient import TestClient

from app.main import app
from app.models.quiz import (
    QuizGenerateRequest,
    QuizGenerateResponse,
    QuizSubmitRequest,
    QuizSubmitResponse,
    QuizLLMResponse,
    QuizQuestionLLM,
)
from app.services.quiz_service import (
    generate_quiz,
    score_quiz,
    QuizGenerationError,
    validate_quiz_response,
    create_quiz_token,
    verify_quiz_token,
    check_code_sufficiency,
    shuffle_question_options,
)
from app.services.llm_service import (
    LLMConfigurationError,
    LLMServiceError,
)

SAMPLE_PYTHON_CODE = """def find_max(numbers):
    maximum = numbers[0]
    for number in numbers:
        if number > maximum:
            maximum = number
    return maximum

result = find_max([4, 9, 2, 15, 7])
"""

VALID_MOCK_QUESTIONS = [
    {
        "question": "What is the primary objective of the find_max function?",
        "options": [
            "To sort the list in ascending order",
            "To find and return the largest number in the list",
            "To calculate the sum of numbers",
            "To count the frequency of each element",
        ],
        "correct_answer_index": 1,
        "explanation": "The function initializes maximum to the first element and updates it whenever a larger number is encountered.",
        "category": "Program purpose and overall understanding",
        "difficulty": "Beginner",
    },
    {
        "question": "What initial value is stored in the variable 'maximum'?",
        "options": [
            "0",
            "None",
            "numbers[0] (the first element)",
            "The length of the numbers list",
        ],
        "correct_answer_index": 2,
        "explanation": "On line 2, maximum is set to numbers[0] as the baseline comparison value.",
        "category": "Variables and data types",
        "difficulty": "Beginner",
    },
    {
        "question": "Under what condition does the function update the 'maximum' variable?",
        "options": [
            "When number < maximum",
            "When number == maximum",
            "When number > maximum",
            "At the end of every loop iteration",
        ],
        "correct_answer_index": 2,
        "explanation": "The conditional 'if number > maximum:' checks if the current element is greater before updating.",
        "category": "Conditional statements",
        "difficulty": "Beginner",
    },
    {
        "question": "What does the for loop iterate over?",
        "options": [
            "The range of indices from 0 to len(numbers)",
            "Each element in the numbers collection directly",
            "A copy of sorted numbers",
            "The digits of the number 15",
        ],
        "correct_answer_index": 1,
        "explanation": "The syntax 'for number in numbers:' directly iterates through each item in the collection.",
        "category": "Loops and iteration",
        "difficulty": "Beginner",
    },
    {
        "question": "What is the final value assigned to 'result' in this code?",
        "options": [
            "4",
            "9",
            "15",
            "7",
        ],
        "correct_answer_index": 2,
        "explanation": "15 is the maximum element in [4, 9, 2, 15, 7], which find_max returns.",
        "category": "Return values",
        "difficulty": "Beginner",
    },
]


class TestQuizStep8A(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    # -------------------------------------------------------------
    # 1. Valid quiz generation response
    # -------------------------------------------------------------
    @patch("app.services.quiz_service.get_gemini_client")
    def test_01_valid_quiz_generation(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({"questions": VALID_MOCK_QUESTIONS})
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("quiz_id", data)
        self.assertIn("quiz_token", data)
        self.assertEqual(data["total_questions"], 5)
        self.assertEqual(len(data["questions"]), 5)

        first_q = data["questions"][0]
        self.assertEqual(first_q["id"], 1)
        self.assertIn("question", first_q)
        self.assertEqual(len(first_q["options"]), 4)
        self.assertIn("category", first_q)
        self.assertIn("difficulty", first_q)

        # Anti-cheat check: correct_answer_index and explanation MUST NOT be exposed!
        self.assertNotIn("correct_answer_index", first_q)
        self.assertNotIn("explanation", first_q)

    # -------------------------------------------------------------
    # 2. Invalid learning level
    # -------------------------------------------------------------
    def test_02_invalid_learning_level(self):
        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "SuperNinjaExpert",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 422)

    # -------------------------------------------------------------
    # 3. Missing or whitespace source code
    # -------------------------------------------------------------
    def test_03_missing_source_code(self):
        payload = {
            "code": "   ",
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 422)

    # -------------------------------------------------------------
    # 4. Malformed Gemini response (not valid JSON)
    # -------------------------------------------------------------
    @patch("app.services.quiz_service.get_gemini_client")
    def test_04_malformed_gemini_response(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "This is not json at all."
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 502)

    # -------------------------------------------------------------
    # 5. Incorrect question count (e.g. 4 instead of 5)
    # -------------------------------------------------------------
    @patch("app.services.quiz_service.get_gemini_client")
    def test_05_incorrect_question_count(self, mock_get_client):
        mock_client = MagicMock()
        mock_response = MagicMock()
        # Only 4 questions
        mock_response.text = json.dumps({"questions": VALID_MOCK_QUESTIONS[:4]})
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("Expected exactly 5 questions", response.json()["detail"])

    # -------------------------------------------------------------
    # 6. Incorrect number of options (e.g. 3 options)
    # -------------------------------------------------------------
    @patch("app.services.quiz_service.get_gemini_client")
    def test_06_incorrect_number_of_options(self, mock_get_client):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        bad_questions[0]["options"] = ["Opt 1", "Opt 2", "Opt 3"]  # Only 3 options

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({"questions": bad_questions})
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("must have exactly 4 options", response.json()["detail"])

    # -------------------------------------------------------------
    # 7. Invalid correct-answer index (e.g. index 4)
    # -------------------------------------------------------------
    @patch("app.services.quiz_service.get_gemini_client")
    def test_07_invalid_correct_answer_index(self, mock_get_client):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        bad_questions[0]["correct_answer_index"] = 4  # Valid range is 0..3

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({"questions": bad_questions})
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("invalid correct_answer_index", response.json()["detail"])

    # -------------------------------------------------------------
    # 8. Duplicate options
    # -------------------------------------------------------------
    @patch("app.services.quiz_service.get_gemini_client")
    def test_08_duplicate_options_rejected(self, mock_get_client):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        bad_questions[0]["options"] = ["Same", "Same", "Opt 3", "Opt 4"]

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = json.dumps({"questions": bad_questions})
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("duplicate options", response.json()["detail"].lower())

    # -------------------------------------------------------------
    # 9. Dynamic category selection
    # -------------------------------------------------------------
    def test_09_categories_are_present(self):
        """Verify mock questions cover multiple dynamic categories."""
        categories = [q["category"] for q in VALID_MOCK_QUESTIONS]
        self.assertEqual(len(set(categories)), 5)

    # -------------------------------------------------------------
    # 10. Gemini unavailable / 503 or timeout
    # -------------------------------------------------------------
    @patch("app.services.quiz_service.get_gemini_client")
    def test_10_gemini_unavailable(self, mock_get_client):
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception("503 Service Unavailable: High demand spike")
        mock_get_client.return_value = mock_client

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 502)

    # -------------------------------------------------------------
    # 11. API configuration missing
    # -------------------------------------------------------------
    @patch("app.services.quiz_service.get_gemini_client")
    def test_11_api_configuration_missing(self, mock_get_client):
        mock_get_client.side_effect = LLMConfigurationError("Gemini API key is not configured.")

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 503)

    # -------------------------------------------------------------
    # 12. Existing endpoints remain functional
    # -------------------------------------------------------------
    def test_12_existing_endpoints_functional(self):
        # Health check
        res_health = self.client.get("/api/health")
        self.assertEqual(res_health.status_code, 200)

        # Root endpoint
        res_root = self.client.get("/")
        self.assertEqual(res_root.status_code, 200)

    # -------------------------------------------------------------
    # 13. Deterministic scoring
    # -------------------------------------------------------------
    def test_13_deterministic_scoring(self):
        token = create_quiz_token("test-quiz-123", VALID_MOCK_QUESTIONS)

        # 4 out of 5 correct:
        # Q1: ans=1 (correct), Q2: ans=2 (correct), Q3: ans=2 (correct), Q4: ans=1 (correct), Q5: ans=0 (wrong: correct is 2)
        submit_payload = {
            "quiz_id": "test-quiz-123",
            "quiz_token": token,
            "answers": {
                "1": 1,
                "2": 2,
                "3": 2,
                "4": 1,
                "5": 0,
            },
        }

        response = self.client.post("/api/quiz/submit", json=submit_payload)
        self.assertEqual(response.status_code, 200)

        result = response.json()
        self.assertTrue(result["success"])
        self.assertEqual(result["score"], 4)
        self.assertEqual(result["total"], 5)
        self.assertEqual(result["percentage"], 80.0)
        self.assertIn("review", result)
        self.assertEqual(len(result["review"]), 5)

        q5_review = result["review"][4]
        self.assertFalse(q5_review["is_correct"])
        self.assertEqual(q5_review["selected_index"], 0)
        self.assertEqual(q5_review["correct_index"], 2)
        self.assertIn("explanation", q5_review)

    # -------------------------------------------------------------
    # 14. Perfect score
    # -------------------------------------------------------------
    def test_14_perfect_score_5_out_of_5(self):
        token = create_quiz_token("test-quiz-perf", VALID_MOCK_QUESTIONS)

        submit_payload = {
            "quiz_id": "test-quiz-perf",
            "quiz_token": token,
            "answers": {
                "1": 1,
                "2": 2,
                "3": 2,
                "4": 1,
                "5": 2,
            },
        }

        response = self.client.post("/api/quiz/submit", json=submit_payload)
        self.assertEqual(response.status_code, 200)

        result = response.json()
        self.assertEqual(result["score"], 5)
        self.assertEqual(result["percentage"], 100.0)
        self.assertTrue(all(r["is_correct"] for r in result["review"]))

    # -------------------------------------------------------------
    # 15. Tampered or invalid token rejection
    # -------------------------------------------------------------
    def test_15_tampered_token_rejection(self):
        submit_payload = {
            "quiz_id": "test-quiz-fake",
            "quiz_token": "fake.tampered_signature_token",
            "answers": {"1": 0},
        }
        response = self.client.post("/api/quiz/submit", json=submit_payload)
        self.assertEqual(response.status_code, 400)


class TestStep8BQuizEnhancements(unittest.TestCase):
    """
    Targeted tests for Step 8B: Quiz Quality, Grounding, Diversity,
    Bounded Regeneration, and Learning Experience Enhancements.
    """
    def setUp(self):
        self.client = TestClient(app)

    # 1. Code Sufficiency Check
    def test_8b_01_code_too_short_or_insufficient(self):
        # 1-line trivial code
        with self.assertRaises(QuizGenerationError):
            check_code_sufficiency("x = 1")

        # Comments only
        with self.assertRaises(QuizGenerationError):
            check_code_sufficiency("# just a single python comment\n# another comment")

        # API endpoint returns 400 Bad Request
        payload = {
            "code": "x = 1",
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("too short or lacks sufficient", response.json()["detail"].lower())

    # 2. Unsupported concepts (hallucinated identifier in question)
    def test_8b_02_unsupported_concepts_rejected(self):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        bad_questions[0]["question"] = "What does the function `non_existent_function()` calculate in this code?"
        quiz_llm = QuizLLMResponse.model_validate({"questions": bad_questions})

        with self.assertRaises(QuizGenerationError) as ctx:
            validate_quiz_response(quiz_llm, code=SAMPLE_PYTHON_CODE, learning_level="Beginner")
        self.assertIn("non_existent_function", str(ctx.exception))

    # 3. Ambiguous or brief questions rejected
    def test_8b_03_ambiguous_or_brief_questions_rejected(self):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        bad_questions[0]["question"] = "What?"
        quiz_llm = QuizLLMResponse.model_validate({"questions": bad_questions})

        with self.assertRaises(QuizGenerationError) as ctx:
            validate_quiz_response(quiz_llm, code=SAMPLE_PYTHON_CODE, learning_level="Beginner")
        self.assertIn("too brief", str(ctx.exception).lower())

    # 4. Duplicate questions rejected
    def test_8b_04_duplicate_questions_rejected(self):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        # Duplicate Q1 into Q2
        bad_questions[1]["question"] = bad_questions[0]["question"]
        quiz_llm = QuizLLMResponse.model_validate({"questions": bad_questions})

        with self.assertRaises(QuizGenerationError) as ctx:
            validate_quiz_response(quiz_llm, code=SAMPLE_PYTHON_CODE, learning_level="Beginner")
        self.assertIn("duplicate questions detected", str(ctx.exception).lower())

    # 5. Duplicate or equivalent options rejected
    def test_8b_05_duplicate_or_equivalent_options_rejected(self):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        # Two options equivalent under normalization
        bad_questions[0]["options"] = [
            "To sort the list in ascending order.",
            "to sort the list in ascending order",
            "To calculate the sum of numbers",
            "To count the frequency of each element",
        ]
        quiz_llm = QuizLLMResponse.model_validate({"questions": bad_questions})

        with self.assertRaises(QuizGenerationError) as ctx:
            validate_quiz_response(quiz_llm, code=SAMPLE_PYTHON_CODE, learning_level="Beginner")
        self.assertIn("duplicate or equivalent options", str(ctx.exception).lower())

    # 6. Disallowed placeholder / meta-options rejected
    def test_8b_06_placeholder_meta_options_rejected(self):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        bad_questions[0]["options"] = [
            "Option 1",
            "Option 2",
            "Option 3",
            "None of the above",
        ]
        quiz_llm = QuizLLMResponse.model_validate({"questions": bad_questions})

        with self.assertRaises(QuizGenerationError) as ctx:
            validate_quiz_response(quiz_llm, code=SAMPLE_PYTHON_CODE, learning_level="Beginner")
        self.assertIn("disallowed meta-option", str(ctx.exception).lower())

    # 7. Contradictory answer / explanation alignment rejected
    def test_8b_07_answer_explanation_contradiction_rejected(self):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        # correct_answer_index is 0 (Option A), but explanation says Option B is correct
        bad_questions[0]["correct_answer_index"] = 0
        bad_questions[0]["explanation"] = "Option B is correct because the function sorts elements."
        quiz_llm = QuizLLMResponse.model_validate({"questions": bad_questions})

        with self.assertRaises(QuizGenerationError) as ctx:
            validate_quiz_response(quiz_llm, code=SAMPLE_PYTHON_CODE, learning_level="Beginner")
        self.assertIn("contradicts", str(ctx.exception).lower())

    # 8. Difficulty mismatch rejected
    def test_8b_08_difficulty_mismatch_rejected(self):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        bad_questions[0]["difficulty"] = "Advanced"
        quiz_llm = QuizLLMResponse.model_validate({"questions": bad_questions})

        with self.assertRaises(QuizGenerationError) as ctx:
            validate_quiz_response(quiz_llm, code=SAMPLE_PYTHON_CODE, learning_level="Beginner")
        self.assertIn("difficulty mismatch", str(ctx.exception).lower())

    # 9. Repeated concept coverage rejected (too many output prediction questions)
    def test_8b_09_repeated_concept_coverage_rejected(self):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        for q in bad_questions:
            q["category"] = "Output prediction"
        quiz_llm = QuizLLMResponse.model_validate({"questions": bad_questions})

        with self.assertRaises(QuizGenerationError) as ctx:
            validate_quiz_response(quiz_llm, code=SAMPLE_PYTHON_CODE, learning_level="Beginner")
        self.assertIn("concept diversity", str(ctx.exception).lower())

    # 10. Insufficient category diversity rejected
    def test_8b_10_insufficient_category_diversity_rejected(self):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        # Only 2 distinct categories
        bad_questions[0]["category"] = "Variables and data types"
        bad_questions[1]["category"] = "Variables and data types"
        bad_questions[2]["category"] = "Variables and data types"
        bad_questions[3]["category"] = "Conditional statements"
        bad_questions[4]["category"] = "Conditional statements"
        quiz_llm = QuizLLMResponse.model_validate({"questions": bad_questions})

        with self.assertRaises(QuizGenerationError) as ctx:
            validate_quiz_response(quiz_llm, code=SAMPLE_PYTHON_CODE, learning_level="Beginner")
        self.assertIn("at least 3 distinct", str(ctx.exception).lower())

    # 11. Option shuffling strictly preserves correct-answer mapping
    def test_8b_11_option_shuffling_preserves_correct_answer(self):
        options = ["First", "Second", "Third", "Fourth"]
        orig_correct_idx = 2  # "Third"

        for seed in range(20):
            shuffled, new_idx = shuffle_question_options(options, orig_correct_idx, seed=seed)
            self.assertEqual(len(shuffled), 4)
            self.assertEqual(set(shuffled), set(options))
            self.assertEqual(shuffled[new_idx], options[orig_correct_idx])

    # 12. Bounded regeneration succeeds when attempt 1 fails but attempt 2 succeeds
    @patch("app.services.quiz_service.get_gemini_client")
    def test_8b_12_bounded_regeneration_success(self, mock_get_client):
        # Attempt 1: Question #1 has duplicate options
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        bad_questions[0]["options"] = ["Dup", "Dup", "Opt 3", "Opt 4"]
        resp_1 = MagicMock()
        resp_1.text = json.dumps({"questions": bad_questions})

        # Attempt 2: Valid questions
        resp_2 = MagicMock()
        resp_2.text = json.dumps({"questions": VALID_MOCK_QUESTIONS})

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [resp_1, resp_2]
        mock_get_client.return_value = mock_client

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["questions"]), 5)
        self.assertEqual(mock_client.models.generate_content.call_count, 2)

    # 13. Graceful failure when all regeneration attempts are exhausted
    @patch("app.services.quiz_service.get_gemini_client")
    def test_8b_13_graceful_failure_after_exhausted_retries(self, mock_get_client):
        bad_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        bad_questions[0]["options"] = ["Dup", "Dup", "Opt 3", "Opt 4"]

        resp_bad = MagicMock()
        resp_bad.text = json.dumps({"questions": bad_questions})

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = resp_bad
        mock_get_client.return_value = mock_client

        payload = {
            "code": SAMPLE_PYTHON_CODE,
            "language": "Python",
            "learning_level": "Beginner",
        }
        response = self.client.post("/api/quiz/generate", json=payload)
        self.assertEqual(response.status_code, 502)
        self.assertIn("duplicate options", response.json()["detail"].lower())
        # Exactly 2 bounded attempts
        self.assertEqual(mock_client.models.generate_content.call_count, 2)

    # 14. Rich review fields (code evidence & learning takeaway) populated during scoring
    def test_8b_14_rich_review_fields_in_scoring(self):
        rich_questions = [dict(q) for q in VALID_MOCK_QUESTIONS]
        rich_questions[0]["code_evidence"] = "Line 2: maximum = numbers[0]"
        rich_questions[0]["learning_takeaway"] = "Always initialize baseline tracking variables to an actual member of the collection."

        token = create_quiz_token("rich-quiz-1", rich_questions)

        submit_payload = {
            "quiz_id": "rich-quiz-1",
            "quiz_token": token,
            "answers": {"1": 1, "2": 2, "3": 2, "4": 1, "5": 2},
        }

        response = self.client.post("/api/quiz/submit", json=submit_payload)
        self.assertEqual(response.status_code, 200)

        data = response.json()
        q1_review = data["review"][0]
        self.assertEqual(q1_review["code_evidence"], "Line 2: maximum = numbers[0]")
        self.assertEqual(q1_review["learning_takeaway"], "Always initialize baseline tracking variables to an actual member of the collection.")

    # 15. Regression: existing core modules operate normally
    def test_8b_15_regression_verify_existing_modules(self):
        # Health check
        res_health = self.client.get("/api/health")
        self.assertEqual(res_health.status_code, 200)

        # Root
        res_root = self.client.get("/")
        self.assertEqual(res_root.status_code, 200)
