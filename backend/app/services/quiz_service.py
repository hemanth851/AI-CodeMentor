import os
import json
import time
import uuid
import hmac
import hashlib
import base64
import logging
from typing import Optional, List, Dict, Any, Union
from collections import OrderedDict

from app.models.quiz import (
    QuizQuestionLLM,
    QuizLLMResponse,
    QuizQuestionPublic,
    QuestionReview,
    QuizGenerateResponse,
    QuizSubmitResponse,
    SUPPORTED_QUIZ_CATEGORIES,
)
from app.services.llm_service import (
    get_gemini_client,
    execute_with_retry_and_fallback,
    raise_classified_error,
    sanitize_sensitive_data,
    LLMConfigurationError,
    LLMServiceError,
)

logger = logging.getLogger(__name__)

# Bounded in-memory quiz cache (last 200 quizzes, TTL 2 hours)
QUIZ_CACHE: OrderedDict[str, Dict[str, Any]] = OrderedDict()
MAX_CACHE_SIZE = 200
CACHE_TTL_SECONDS = 7200


class QuizGenerationError(Exception):
    """Raised when generated quiz fails validation or structure checks."""
    pass


def check_code_sufficiency(code: str) -> None:
    """
    Ensure the submitted code contains sufficient statements and substance
    to formulate 5 grounded questions without hallucinating absent concepts.
    """
    if not code:
        raise QuizGenerationError("Source code is empty.")
    
    clean_lines = [
        line.strip()
        for line in code.splitlines()
        if line.strip() and not line.strip().startswith(("#", "//", "/*", "*", "--", ";"))
    ]
    total_substance = sum(len(line) for line in clean_lines)
    if len(clean_lines) < 2 or total_substance < 20:
        raise QuizGenerationError(
            "The submitted code is too short or lacks sufficient statements to generate an authentic "
            "5-question assessment. Please provide code with more logic, functions, or control flow."
        )


def shuffle_question_options(
    options: List[str],
    correct_index: int,
    seed: Optional[int] = None,
) -> tuple[List[str], int]:
    """
    Shuffle options while strictly updating and preserving the correct_answer_index.
    """
    import random
    indexed = list(enumerate(options))
    rng = random.Random(seed) if seed is not None else random.Random()
    rng.shuffle(indexed)
    shuffled_opts = [opt for _, opt in indexed]
    new_correct_idx = next(
        new_i for new_i, (orig_i, _) in enumerate(indexed) if orig_i == correct_index
    )
    return shuffled_opts, new_correct_idx


def get_token_secret() -> bytes:
    """Derive a consistent HMAC secret key from the environment."""
    key = os.getenv("QUIZ_SECRET_KEY") or os.getenv("GEMINI_API_KEY") or "ai-codementor-quiz-secret"
    return hashlib.sha256(key.encode("utf-8")).digest()


def _cipher_bytes(data: bytes, key: bytes, nonce: bytes) -> bytes:
    """XOR data with SHA256 counter-mode keystream derived from key and nonce."""
    out = bytearray(len(data))
    block_index = 0
    for offset in range(0, len(data), 32):
        keystream_block = hashlib.sha256(key + nonce + block_index.to_bytes(4, "big")).digest()
        chunk = data[offset : offset + 32]
        for i, b in enumerate(chunk):
            out[offset + i] = b ^ keystream_block[i]
        block_index += 1
    return bytes(out)


def create_quiz_token(quiz_id: str, internal_questions: List[Dict[str, Any]]) -> str:
    """
    Encrypt and sign the quiz answer key into an authenticated tamper-proof token.
    Prevents inspecting correct answers and explanations client-side before submission.
    """
    payload = {
        "quiz_id": quiz_id,
        "ts": int(time.time()),
        "questions": internal_questions,
    }
    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    
    secret = get_token_secret()
    nonce = os.urandom(16)
    ciphertext = _cipher_bytes(payload_json, secret, nonce)
    
    # Compute HMAC over nonce + ciphertext (Encrypt-then-MAC)
    mac = hmac.new(secret, nonce + ciphertext, hashlib.sha256).digest()
    
    token_bytes = nonce + mac + ciphertext
    return base64.urlsafe_b64encode(token_bytes).decode("utf-8")


def verify_quiz_token(token: str) -> Dict[str, Any]:
    """
    Verify HMAC signature and decrypt the authenticated quiz token.
    
    Raises:
        ValueError: If token is expired, tampered, or invalid.
    """
    try:
        token_bytes = base64.urlsafe_b64decode(token.encode("utf-8"))
        if len(token_bytes) < 48:  # 16 nonce + 32 mac
            raise ValueError("Malformed quiz token.")
        
        nonce = token_bytes[:16]
        mac = token_bytes[16:48]
        ciphertext = token_bytes[48:]
        
        secret = get_token_secret()
        expected_mac = hmac.new(secret, nonce + ciphertext, hashlib.sha256).digest()
        
        if not hmac.compare_digest(mac, expected_mac):
            raise ValueError("Invalid quiz token signature.")
        
        plaintext = _cipher_bytes(ciphertext, secret, nonce)
        payload = json.loads(plaintext.decode("utf-8"))
        
        # Check token expiration (4 hours)
        if time.time() - payload.get("ts", 0) > 14400:
            raise ValueError("Quiz session has expired. Please generate a new quiz.")
        
        return payload
    except Exception as e:
        logger.warning(f"Quiz token verification failed: {e}")
        raise ValueError("Invalid or expired quiz token.")


def store_quiz_in_cache(quiz_id: str, data: Dict[str, Any]):
    """Store quiz data in bounded LRU cache with timestamp."""
    now = time.time()
    # Prune expired entries if cache is growing
    if len(QUIZ_CACHE) >= MAX_CACHE_SIZE:
        oldest_id, oldest_data = next(iter(QUIZ_CACHE.items()))
        if now - oldest_data.get("created_at", 0) > CACHE_TTL_SECONDS or len(QUIZ_CACHE) >= MAX_CACHE_SIZE:
            QUIZ_CACHE.pop(oldest_id, None)
    
    QUIZ_CACHE[quiz_id] = {
        "created_at": now,
        "data": data,
    }
    QUIZ_CACHE.move_to_end(quiz_id)


def get_quiz_from_cache(quiz_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve quiz data from in-memory cache if not expired."""
    entry = QUIZ_CACHE.get(quiz_id)
    if not entry:
        return None
    if time.time() - entry.get("created_at", 0) > CACHE_TTL_SECONDS:
        QUIZ_CACHE.pop(quiz_id, None)
        return None
    QUIZ_CACHE.move_to_end(quiz_id)
    return entry.get("data")


def build_quiz_prompt(
    code: str,
    language: str,
    learning_level: str,
    analysis: Optional[Any] = None,
    static_analysis: Optional[Any] = None,
) -> str:
    """
    Construct educational quiz prompt adhering strictly to Step 8B quality & grounding rules.
    """
    level_guidance = {
        "Beginner": (
            "- Focus on basic program purpose, variable names/values, simple operations, and direct code reading.\n"
            "- Questions should be direct, approachable, and friendly.\n"
            "- Avoid overly tricky distractors or complex multi-step mental traces.\n"
            "- Do not ask speculative algorithmic or complex design questions."
        ),
        "Intermediate": (
            "- Focus on control flow logic, loop conditions, function parameter passing, return values, and data structures.\n"
            "- Include code tracing and output prediction questions.\n"
            "- Assess understanding of how components interact and manage state."
        ),
        "Advanced": (
            "- Focus on algorithmic reasoning, edge cases, boundary conditions, time/space complexity (only if clearly evidenced), and subtle language idioms.\n"
            "- Provide rigorous, technically precise questions and distractors.\n"
            "- Test edge cases such as empty collections, zero division, off-by-one conditions, or recursion limits."
        ),
    }.get(learning_level, "- Tailor questions clearly to the student.")

    static_section = ""
    if static_analysis:
        summary_text = getattr(static_analysis, "to_prompt_summary", None)
        if callable(summary_text):
            evidence = static_analysis.to_prompt_summary()
        elif isinstance(static_analysis, dict):
            evidence = json.dumps(static_analysis, indent=2)
        else:
            evidence = str(static_analysis)
        static_section = f"=== STATIC ANALYSIS FACTS ===\n{evidence}\n\n"

    analysis_section = ""
    if analysis:
        if isinstance(analysis, dict):
            summary = analysis.get("summary") or analysis.get("detailed_explanation", "")
            key_points = analysis.get("key_takeaways") or analysis.get("learning_points", [])
            analysis_section = (
                f"=== EXISTING EXPLANATION CONTEXT ===\n"
                f"Summary: {summary}\n"
                f"Key Takeaways: {', '.join(str(p) for p in key_points)}\n\n"
            )
        else:
            analysis_section = f"=== EXISTING EXPLANATION CONTEXT ===\n{str(analysis)}\n\n"

    categories_list = "\n".join(f"- {cat}" for cat in SUPPORTED_QUIZ_CATEGORIES)

    return (
        "You are the dynamic AI Assessment Engine for AI CodeMentor.\n"
        "Generate an interactive, high-quality multiple choice assessment quiz tailored strictly to the user's source code.\n\n"
        "=== STRICT GENERATION RULES ===\n"
        "1. STRICT CODE GROUNDING: Base all questions and answers STRICTLY on the provided source code, language, and analysis facts.\n"
        "2. NO HALLUCINATIONS: Do NOT invent variables, functions, loops, imports, or behavior not present in the code.\n"
        "3. DYNAMIC CATEGORIES: Assess concepts ACTUALLY present in this specific code. Do NOT force all categories.\n"
        "   Available categories to select dynamically from:\n"
        f"{categories_list}\n"
        "   - If the code has no recursion, DO NOT ask recursion questions.\n"
        "   - If the code has no loops, DO NOT ask loop iteration questions.\n"
        "   - If complexity cannot be determined reliably from the code, avoid speculative Big-O questions.\n"
        "4. QUESTION COUNT: Generate EXACTLY 5 questions.\n"
        "5. OPTIONS: Each question MUST have EXACTLY 4 distinct multiple-choice options.\n"
        "   - Distractors must be plausible misconceptions, not silly or equivalent variants.\n"
        "   - Do NOT use placeholder options like 'All of the above', 'None of the above', or 'Cannot be determined'.\n"
        "6. SINGLE CORRECT ANSWER: Each question must have EXACTLY ONE unambiguously correct answer, indicated by correct_answer_index (0, 1, 2, or 3).\n"
        "7. 4-PART PEDAGOGICAL EXPLANATION: In each question's explanation, include:\n"
        "   (a) Confirmation of the correct answer.\n"
        "   (b) Why this answer is correct and others are incorrect.\n"
        "   (c) Direct code behavior/evidence citing specific lines or variables.\n"
        "   (d) A concise key takeaway for the student.\n"
        "8. CONCEPT DIVERSITY: Avoid testing the same concept repeatedly across the 5 questions.\n"
        "   - Cover at least 3 distinct conceptual categories across the quiz.\n"
        "   - Maximum 2 questions testing direct output prediction or step tracing.\n\n"
        f"=== LEARNING LEVEL GUIDANCE ({learning_level}) ===\n"
        f"{level_guidance}\n\n"
        f"Target Programming Language: {language}\n"
        f"Target Learning Level: {learning_level}\n\n"
        f"{static_section}"
        f"{analysis_section}"
        f"=== SOURCE CODE TO ASSESS ===\n```\n{code}\n```\n\n"
        "Generate exactly 5 questions conforming to the structured output schema."
    )


def validate_quiz_response(
    quiz: QuizLLMResponse,
    code: str = "",
    learning_level: str = "Beginner",
) -> None:
    """
    Validate that Gemini's generated quiz strictly adheres to Step 8B quality,
    grounding, diversity, and formatting specifications.
    
    Raises:
        QuizGenerationError: If questions are malformed, duplicate, ungrounded, or violate rules.
    """
    import re

    if not quiz.questions or len(quiz.questions) != 5:
        raise QuizGenerationError(
            f"Expected exactly 5 questions from model, received {len(quiz.questions) if quiz.questions else 0}."
        )

    disallowed_meta_patterns = [
        r"\ball of the above\b",
        r"\bnone of the above\b",
        r"\bboth [a-d] and [a-d]\b",
        r"\bcannot be determined\b",
    ]

    categories: List[str] = []

    for i, q in enumerate(quiz.questions, start=1):
        # 1. Question text validation
        if not q.question or not q.question.strip():
            raise QuizGenerationError(f"Question #{i} is missing question text.")
        if len(q.question.strip()) < 8:
            raise QuizGenerationError(f"Question #{i} question text is too brief or ambiguous.")

        # 2. Options count and content validation
        if not q.options or len(q.options) != 4:
            raise QuizGenerationError(f"Question #{i} must have exactly 4 options, got {len(q.options) if q.options else 0}.")

        cleaned_opts = [opt.strip() for opt in q.options if opt and opt.strip()]
        if len(cleaned_opts) != 4:
            raise QuizGenerationError(f"Question #{i} has blank or empty options.")

        # Exact duplicates
        if len(set(cleaned_opts)) != 4:
            raise QuizGenerationError(f"Question #{i} contains duplicate options.")

        # Normalized / equivalent options (collapse whitespace, lowercase, strip trailing punctuation)
        norm_opts = [
            re.sub(r'[\.;,]+$', '', " ".join(opt.strip().lower().split())).strip()
            for opt in cleaned_opts
        ]
        if len(set(norm_opts)) != 4:
            raise QuizGenerationError(f"Question #{i} contains duplicate or equivalent options.")

        # Meta / placeholder options
        for opt in cleaned_opts:
            for pat in disallowed_meta_patterns:
                if re.search(pat, opt, re.IGNORECASE):
                    raise QuizGenerationError(f"Question #{i} contains disallowed meta-option '{opt}'.")

        # 3. Correct answer index bounds
        if not isinstance(q.correct_answer_index, int) or not (0 <= q.correct_answer_index <= 3):
            raise QuizGenerationError(
                f"Question #{i} has invalid correct_answer_index '{q.correct_answer_index}'. Must be 0, 1, 2, or 3."
            )

        # 4. Explanation validation
        if not q.explanation or not q.explanation.strip():
            raise QuizGenerationError(f"Question #{i} is missing pedagogical explanation.")
        if len(q.explanation.strip()) < 10:
            raise QuizGenerationError(f"Question #{i} explanation is too brief to be educational.")

        # Check for explanation contradiction with correct_answer_index
        option_letters = ['A', 'B', 'C', 'D']
        expected_letter = option_letters[q.correct_answer_index]
        for other_idx, other_letter in enumerate(option_letters):
            if other_idx != q.correct_answer_index:
                if re.search(rf"\boption\s+{other_letter}\s+is\s+(?:the\s+)?(?:correct|right)\b", q.explanation, re.IGNORECASE):
                    raise QuizGenerationError(
                        f"Question #{i} explanation contradicts marked correct answer index {q.correct_answer_index} ({expected_letter}) by stating Option {other_letter} is correct."
                    )

        # 5. Difficulty alignment
        if learning_level.strip().lower() == "beginner" and q.difficulty.strip().lower() == "advanced":
            raise QuizGenerationError(f"Question #{i} difficulty mismatch: received Advanced question for Beginner assessment.")

        # 6. Code grounding check for quoted identifiers
        if code:
            quoted_idents = re.findall(r'`([a-zA-Z_][a-zA-Z0-9_]*)(?:\(\))?`', q.question)
            common_builtins = {
                "len", "range", "print", "int", "str", "list", "dict", "set", "def", "for", "while",
                "if", "else", "elif", "return", "true", "false", "none", "null", "undefined",
                "const", "let", "var", "function", "public", "static", "void", "class", "import"
            }
            for ident in quoted_idents:
                if len(ident) > 2 and ident.lower() not in common_builtins and ident not in code:
                    raise QuizGenerationError(f"Question #{i} refers to identifier '{ident}' not present in the submitted code.")

        categories.append(q.category.strip())

    # 7. Check for duplicate or near-duplicate questions across the quiz
    for i in range(len(quiz.questions)):
        for j in range(i + 1, len(quiz.questions)):
            q1_clean = re.sub(r'\W+', ' ', quiz.questions[i].question.lower()).strip()
            q2_clean = re.sub(r'\W+', ' ', quiz.questions[j].question.lower()).strip()
            if q1_clean == q2_clean:
                raise QuizGenerationError(f"Duplicate questions detected: Question #{i+1} and Question #{j+1} are identical.")
            words1 = set(q1_clean.split())
            words2 = set(q2_clean.split())
            if len(words1) > 4 and len(words2) > 4:
                jaccard = len(words1 & words2) / len(words1 | words2)
                if jaccard > 0.85:
                    raise QuizGenerationError(f"Near-duplicate questions detected between Question #{i+1} and Question #{j+1}.")

    # 8. Concept diversity checks
    output_pred_count = sum(1 for c in categories if "output prediction" in c.lower() or "tracing" in c.lower())
    if output_pred_count > 2:
        raise QuizGenerationError("Generated quiz lacks concept diversity: too many output prediction or tracing questions.")

    if len(set(categories)) < 3:
        raise QuizGenerationError("Generated quiz lacks concept diversity: expected at least 3 distinct conceptual categories.")


def generate_quiz(
    code: str,
    language: str,
    learning_level: str,
    analysis: Optional[Any] = None,
    static_analysis: Optional[Any] = None,
) -> QuizGenerateResponse:
    """
    Generate an educational assessment quiz via Gemini with strict grounding,
    bounded regeneration upon quality defect, and secure answer tokenization.
    """
    # 1. Pre-flight code sufficiency check
    check_code_sufficiency(code)

    model_name = os.getenv("GEMINI_MODEL", "").strip()
    if not model_name:
        logger.error("GEMINI_MODEL environment variable is not defined.")
        raise LLMConfigurationError("GEMINI_MODEL is not configured. Please define GEMINI_MODEL in backend/.env")

    client = get_gemini_client()
    base_prompt = build_quiz_prompt(
        code=code,
        language=language,
        learning_level=learning_level,
        analysis=analysis,
        static_analysis=static_analysis,
    )

    try:
        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=QuizLLMResponse,
            temperature=0.2,
        )

        max_generation_attempts = 2
        current_prompt = base_prompt
        quiz_llm: Optional[QuizLLMResponse] = None

        for gen_attempt in range(max_generation_attempts):
            logger.info(
                f"Generating assessment quiz: attempt {gen_attempt + 1}/{max_generation_attempts} "
                f"with configured model '{model_name}'..."
            )
            response = execute_with_retry_and_fallback(
                client=client,
                contents=current_prompt,
                config=config,
                primary_model=model_name,
                default_msg="Unable to generate the quiz right now. Please try again.",
            )

            raw_text = None
            if hasattr(response, "text") and response.text:
                raw_text = response.text.strip()

            if not raw_text:
                raise LLMServiceError("Gemini returned an empty response for quiz generation.")

            # Clean potential markdown block formatting
            if raw_text.startswith("```"):
                import re
                raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                raw_text = re.sub(r"\s*```$", "", raw_text)

            candidate_llm = QuizLLMResponse.model_validate_json(raw_text)

            # Validate against strict Step 8B quality requirements
            try:
                validate_quiz_response(candidate_llm, code=code, learning_level=learning_level)
                quiz_llm = candidate_llm
                break
            except QuizGenerationError as val_err:
                logger.warning(f"Quiz validation attempt {gen_attempt + 1} failed: {val_err}")
                if gen_attempt < max_generation_attempts - 1:
                    # Bounded revision prompt
                    current_prompt = (
                        f"{base_prompt}\n\n"
                        f"=== CRITICAL REVISION REQUIRED ===\n"
                        f"Your previous attempt was rejected due to: {val_err}\n"
                        f"Please regenerate the 5 questions strictly correcting this defect.\n"
                        f"Ensure: exactly 5 questions, 4 unique plausible options, distinct categories, and strict code grounding."
                    )
                else:
                    raise val_err

        if not quiz_llm:
            raise QuizGenerationError("Unable to produce a valid quiz meeting strict quality criteria.")

        # Prepare public and internal question structures
        quiz_id = str(uuid.uuid4())
        public_questions: List[QuizQuestionPublic] = []
        internal_questions: List[Dict[str, Any]] = []

        for idx, q in enumerate(quiz_llm.questions, start=1):
            # Shuffle options while strictly mapping and preserving the correct answer index
            shuffled_opts, new_correct_idx = shuffle_question_options(
                q.options,
                q.correct_answer_index,
            )

            public_questions.append(
                QuizQuestionPublic(
                    id=idx,
                    question=q.question.strip(),
                    options=[opt.strip() for opt in shuffled_opts],
                    category=q.category.strip() or "General Comprehension",
                    difficulty=q.difficulty.strip() or learning_level,
                )
            )
            internal_questions.append({
                "id": idx,
                "question": q.question.strip(),
                "options": [opt.strip() for opt in shuffled_opts],
                "correct_answer_index": new_correct_idx,
                "explanation": q.explanation.strip(),
                "category": q.category.strip() or "General Comprehension",
                "difficulty": q.difficulty.strip() or learning_level,
                "code_evidence": getattr(q, "code_evidence", None) or "",
                "learning_takeaway": getattr(q, "learning_takeaway", None) or "",
            })

        # Cache internally & create tamper-proof client token
        store_quiz_in_cache(quiz_id, {"questions": internal_questions})
        quiz_token = create_quiz_token(quiz_id, internal_questions)

        return QuizGenerateResponse(
            success=True,
            quiz_id=quiz_id,
            quiz_token=quiz_token,
            total_questions=len(public_questions),
            questions=public_questions,
            error=None,
        )

    except (LLMConfigurationError, LLMServiceError, QuizGenerationError) as e:
        logger.warning(f"Quiz generation halted with {type(e).__name__}: {sanitize_sensitive_data(str(e))}")
        raise
    except Exception as e:
        logger.error(f"Quiz generation failed: {type(e).__name__} - {sanitize_sensitive_data(str(e))}")
        raise_classified_error(
            e,
            model_name=model_name,
            default_msg="Unable to generate the quiz right now. Please try again.",
        )


def score_quiz(
    quiz_id: str,
    quiz_token: str,
    user_answers: Dict[str, int],
) -> QuizSubmitResponse:
    """
    Score submitted quiz answers deterministically against verified answers.
    Does NOT call Gemini or use eval().
    """
    # 1. Resolve internal questions from cache or token
    cached = get_quiz_from_cache(quiz_id)
    if cached and "questions" in cached:
        internal_questions = cached["questions"]
    else:
        # Fallback to verified signed token
        token_payload = verify_quiz_token(quiz_token)
        internal_questions = token_payload.get("questions", [])

    if not internal_questions:
        raise ValueError("Quiz questions could not be found or verified.")

    # 2. Score deterministically
    correct_count = 0
    total = len(internal_questions)
    reviews: List[QuestionReview] = []

    for idx, q in enumerate(internal_questions, start=1):
        q_id = q.get("id", idx)
        user_choice = user_answers.get(str(q_id))
        if user_choice is None:
            user_choice = user_answers.get(int(q_id))

        correct_choice = q["correct_answer_index"]
        is_correct = (user_choice is not None and user_choice == correct_choice)

        if is_correct:
            correct_count += 1

        reviews.append(
            QuestionReview(
                question_id=q_id,
                question=q["question"],
                options=q["options"],
                selected_index=user_choice,
                correct_index=correct_choice,
                is_correct=is_correct,
                explanation=q["explanation"],
                category=q.get("category", "General Comprehension"),
                difficulty=q.get("difficulty"),
                code_evidence=q.get("code_evidence") or None,
                learning_takeaway=q.get("learning_takeaway") or None,
            )
        )

    percentage = round((correct_count / total) * 100.0, 1)

    # Educational feedback message
    if correct_count == 5:
        feedback = "Outstanding! Perfect score! You have thoroughly mastered all assessed concepts."
    elif correct_count == 4:
        feedback = "Great job! You demonstrated strong comprehension with only minor points to review."
    elif correct_count == 3:
        feedback = "Good effort! You understand the core logic. Review the explanations below to master the remaining details."
    elif correct_count == 2:
        feedback = "Nice attempt! Pay close attention to the code tracing and logic explanations below."
    else:
        feedback = "Keep learning! Carefully study the detailed explanations below to build your foundational understanding."

    return QuizSubmitResponse(
        success=True,
        score=correct_count,
        total=total,
        percentage=percentage,
        review=reviews,
        feedback=feedback,
        error=None,
    )
