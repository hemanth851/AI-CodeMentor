import React, { useState, useEffect, useRef } from 'react';
import { generateQuiz, submitQuiz } from '../services/api';
import { getCodeFingerprint } from '../utils/codeUtils';

const OPTION_LETTERS = ['A', 'B', 'C', 'D'];

function renderFormattedText(text) {
  if (!text) return null;
  const parts = text.split(/(`[^`]+`)/g);
  return parts.map((part, i) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return (
        <code key={i} className="quiz-inline-code">
          {part.slice(1, -1)}
        </code>
      );
    }
    return part;
  });
}

export default function QuizSection({
  sourceCode,
  detectedLanguage,
  learningLevel,
  analysisData,
  staticAnalysis,
  onQuizCompleted,
  restoredQuizProgress,
  isCodeModified = false,
}) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [quizData, setQuizData] = useState(null);
  const [userAnswers, setUserAnswers] = useState({});
  const [submissionResult, setSubmissionResult] = useState(null);
  const [quizError, setQuizError] = useState(null);
  const [dismissRestored, setDismissRestored] = useState(false);

  const quizFingerprintRef = useRef('');
  const quizReqIdRef = useRef(0);
  const quizSubmitReqIdRef = useRef(0);
  const currentFingerprint = getCodeFingerprint(sourceCode);

  const levelStr = typeof learningLevel === 'string' ? learningLevel : (learningLevel?.label || 'Beginner');

  // Immediately invalidate stale quiz state when sourceCode or detectedLanguage changes
  useEffect(() => {
    if (quizFingerprintRef.current && quizFingerprintRef.current !== currentFingerprint) {
      quizReqIdRef.current++;
      quizSubmitReqIdRef.current++;
      setIsGenerating(false);
      setIsSubmitting(false);
      setQuizData(null);
      setUserAnswers({});
      setSubmissionResult(null);
      setQuizError(null);
      setDismissRestored(true);
      quizFingerprintRef.current = '';
    } else if (!quizFingerprintRef.current && isCodeModified) {
      // Invalidate if code in editor was modified
      setQuizData(null);
      setUserAnswers({});
      setSubmissionResult(null);
      setQuizError(null);
      setDismissRestored(true);
    }
  }, [sourceCode, detectedLanguage, currentFingerprint, isCodeModified]);

  const handleGenerate = async () => {
    if (isGenerating) return;

    if (!sourceCode || sourceCode.trim() === '') {
      setQuizError('Please analyze or enter some code first to generate a quiz.');
      return;
    }

    const reqId = ++quizReqIdRef.current;
    const reqFingerprint = getCodeFingerprint(sourceCode);

    setIsGenerating(true);
    // Immediately clear previous quiz so old questions/score are never displayed during generation
    setQuizData(null);
    setUserAnswers({});
    setSubmissionResult(null);
    setQuizError(null);
    setDismissRestored(true);

    try {
      const response = await generateQuiz({
        code: sourceCode,
        language: detectedLanguage || 'Python',
        learningLevel: levelStr,
        analysis: analysisData || null,
        staticAnalysis: staticAnalysis || null,
      });

      // Discard response if request is stale or code has changed
      if (reqId !== quizReqIdRef.current || getCodeFingerprint(sourceCode) !== reqFingerprint) {
        return;
      }

      if (response.success && response.data) {
        const questions = response.data.questions || [];

        // Verify exactly 5 questions with 4 options each
        if (questions.length !== 5) {
          setQuizError(`Assessment format error: expected exactly 5 questions, received ${questions.length}. Please try again.`);
          setQuizData(null);
          return;
        }

        const invalidOptions = questions.some((q) => !q.options || q.options.length !== 4);
        if (invalidOptions) {
          setQuizError('Assessment format error: each question must contain exactly 4 options. Please try again.');
          setQuizData(null);
          return;
        }

        quizFingerprintRef.current = reqFingerprint;
        setQuizData(response.data);
        setUserAnswers({});
        setSubmissionResult(null);
        setQuizError(null);
      } else {
        // Show error and keep quiz area empty. Never restore previous quiz.
        setQuizError(response.error || 'Failed to generate quiz. Please try again.');
        setQuizData(null);
      }
    } catch (err) {
      if (reqId !== quizReqIdRef.current) return;
      // Show error and keep quiz area empty. Never restore previous quiz.
      setQuizError('Unable to communicate with the quiz assessment service.');
      setQuizData(null);
    } finally {
      if (reqId === quizReqIdRef.current) {
        setIsGenerating(false);
      }
    }
  };

  const handleSelectOption = (questionId, optionIndex) => {
    if (submissionResult) return;

    setUserAnswers((prev) => ({
      ...prev,
      [String(questionId)]: optionIndex,
    }));
  };

  const unansweredQuestions = (quizData?.questions || [])
    .filter((q) => userAnswers[String(q.id)] === undefined)
    .map((_, idx) => `#${idx + 1}`);

  const handleSubmit = async () => {
    if (isSubmitting) return;
    if (!quizData) return;

    const totalQuestions = quizData.questions.length;
    const answeredCount = Object.keys(userAnswers).length;

    if (answeredCount < totalQuestions) {
      const pendingStr = unansweredQuestions.length > 0 ? ` (${unansweredQuestions.join(', ')} pending)` : '';
      setQuizError(`Please answer all ${totalQuestions} questions before submitting${pendingStr}.`);
      return;
    }

    const submitReqId = ++quizSubmitReqIdRef.current;
    const submitFingerprint = quizFingerprintRef.current;

    setIsSubmitting(true);
    setQuizError(null);

    try {
      const response = await submitQuiz({
        quizId: quizData.quiz_id,
        quizToken: quizData.quiz_token,
        answers: userAnswers,
      });

      // Discard response if request is stale or code has changed
      if (submitReqId !== quizSubmitReqIdRef.current || getCodeFingerprint(sourceCode) !== submitFingerprint) {
        return;
      }

      if (response.success && response.data) {
        setSubmissionResult(response.data);
        setQuizError(null);
        if (onQuizCompleted) {
          onQuizCompleted({
            score: response.data.score,
            totalQuestions: response.data.total,
            percentage: response.data.percentage,
            completedAt: new Date().toISOString(),
          });
        }
      } else {
        setQuizError(response.error || 'Unable to score quiz. Please try again.');
      }
    } catch (err) {
      if (submitReqId !== quizSubmitReqIdRef.current) return;
      setQuizError('Unable to score the quiz. Please try again.');
    } finally {
      if (submitReqId === quizSubmitReqIdRef.current) {
        setIsSubmitting(false);
      }
    }
  };

  const handleRetake = () => {
    setUserAnswers({});
    setSubmissionResult(null);
    setQuizError(null);
    setDismissRestored(true);
  };

  const answeredCount = Object.keys(userAnswers).length;
  const totalQuestions = quizData?.questions?.length || 5;
  const allAnswered = answeredCount === totalQuestions;

  return (
    <section className="quiz-section-card" aria-label="Step 8B Dynamic Quiz Assessment">
      {/* Quiz Header */}
      <div className="quiz-header">
        <div className="quiz-title-group">
          <div className="quiz-badge">Step 8B Assessment</div>
          <h2 className="quiz-title">Interactive Code Quiz</h2>
          <span className="quiz-subtext">5 Code-Grounded Questions</span>
        </div>

        <div className="quiz-header-actions">
          <button
            type="button"
            className="btn btn-generate-quiz"
            onClick={() => {
              setDismissRestored(true);
              handleGenerate();
            }}
            disabled={isGenerating || !sourceCode}
          >
            {isGenerating ? (
              <>
                <span className="quiz-spinner" aria-hidden="true" />
                Generating Questions...
              </>
            ) : (
              <>
                <span className="btn-icon">🎯</span>
                {quizData ? 'Generate New Quiz' : 'Generate Quiz for Current Code'}
              </>
            )}
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {quizError && (
        <div className="quiz-error-banner" role="alert">
          <span className="error-icon">⚠️</span>
          <span>{quizError}</span>
        </div>
      )}

      {/* Restored Quiz Progress Banner from Reopened Session */}
      {restoredQuizProgress && !dismissRestored && !quizData && !submissionResult && !isGenerating && (
        <div className="quiz-restored-banner" role="region" aria-label="Saved Quiz Assessment Progress">
          <div className="restored-banner-inner">
            <div className="restored-badge-group">
              <span className="restored-pill-label">Saved Progress</span>
              <span className="restored-score-pill">
                Score: {restoredQuizProgress.score} / {restoredQuizProgress.total} ({restoredQuizProgress.percentage}%)
              </span>
            </div>
            <p className="restored-timestamp-text">
              Assessment completed on {new Date(restoredQuizProgress.completedAt || Date.now()).toLocaleString()}
            </p>
          </div>
          <div className="restored-action-group">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setDismissRestored(true);
                handleGenerate();
              }}
              disabled={!sourceCode}
            >
              🔄 Retake Assessment Quiz
            </button>
          </div>
        </div>
      )}

      {/* Empty / Initial Invitation State */}
      {!quizData && !isGenerating && (!restoredQuizProgress || dismissRestored) && (
        <div className="quiz-empty-state">
          <div className="empty-state-icon">📋</div>
          <h3 className="empty-state-title">Test Your Understanding</h3>
          <p className="empty-state-desc">
            Generate a quiz for the current code.
          </p>
          <button
            type="button"
            className="btn btn-empty-generate"
            onClick={handleGenerate}
            disabled={!sourceCode}
          >
            🎯 Generate Quiz for Current Code
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {isGenerating && (
        <div className="quiz-loading-container">
          <div className="quiz-loading-spinner" />
          <p className="quiz-loading-text">
            Analyzing code structure and formulating dynamic multiple-choice questions for <strong>{levelStr}</strong> level...
          </p>
        </div>
      )}

      {/* Submission Score & Feedback Banner */}
      {submissionResult && (
        <div className={`quiz-score-banner score-grade-${submissionResult.score >= 4 ? 'high' : submissionResult.score >= 3 ? 'mid' : 'low'}`}>
          <div className="score-summary">
            <div className="score-circle">
              <span className="score-number">{submissionResult.score}</span>
              <span className="score-denominator">/ {submissionResult.total}</span>
            </div>
            <div className="score-details">
              <div className="score-percentage-row">
                <span className="score-percentage">{submissionResult.percentage}% Correct</span>
                <span className="score-badge">
                  {submissionResult.score === 5 ? '🏆 Perfect Score' : submissionResult.score >= 4 ? '🌟 Great Job' : submissionResult.score >= 3 ? '👍 Good Effort' : '📚 Practice Mode'}
                </span>
              </div>
              <p className="score-feedback-text">{submissionResult.feedback}</p>
            </div>
          </div>

          <div className="score-actions">
            <button
              type="button"
              className="btn btn-retake-quiz"
              onClick={handleRetake}
            >
              🔄 Retake This Quiz
            </button>
            <button
              type="button"
              className="btn btn-new-quiz-secondary"
              onClick={handleGenerate}
            >
              ✨ Generate New Questions
            </button>
          </div>
        </div>
      )}

      {/* Active Questions List */}
      {quizData && !isGenerating && (
        <div className="quiz-questions-wrapper">
          {/* Progress Indicator (when taking quiz) */}
          {!submissionResult && (
            <div className="quiz-progress-bar-container">
              <div className="quiz-progress-info">
                <span>Progress: {answeredCount} of {totalQuestions} answered</span>
                <span className="progress-pct">{Math.round((answeredCount / totalQuestions) * 100)}%</span>
              </div>
              <div className="quiz-progress-track">
                <div
                  className="quiz-progress-fill"
                  style={{ width: `${(answeredCount / totalQuestions) * 100}%` }}
                />
              </div>
            </div>
          )}

          {/* Render 5 Questions */}
          <div className="quiz-questions-list">
            {quizData.questions.map((q, qIndex) => {
              const qIdStr = String(q.id);
              const selectedIdx = userAnswers[qIdStr];
              const reviewItem = submissionResult?.review?.find((r) => r.question_id === q.id);

              return (
                <div
                  key={q.id}
                  className={`question-card ${reviewItem ? (reviewItem.is_correct ? 'reviewed-correct' : 'reviewed-incorrect') : ''}`}
                >
                  <div className="question-header">
                    <span className="question-number-pill">Question {qIndex + 1} of {totalQuestions}</span>
                    <span className="question-category-pill">{q.category}</span>
                    {reviewItem && (
                      <span className={`review-status-tag ${reviewItem.is_correct ? 'status-correct' : 'status-incorrect'}`}>
                        {reviewItem.is_correct ? '✓ Correct' : '✕ Incorrect'}
                      </span>
                    )}
                  </div>

                  <h3 className="question-text">{renderFormattedText(q.question)}</h3>

                  {/* 4 Multiple Choice Options */}
                  <div className="options-grid" role="group" aria-label={`Options for Question ${qIndex + 1}`}>
                    {q.options.map((opt, optIndex) => {
                      const isSelected = selectedIdx === optIndex;
                      let optionClass = 'option-btn';

                      if (submissionResult && reviewItem) {
                        const isCorrectAnswer = reviewItem.correct_index === optIndex;
                        if (isCorrectAnswer) {
                          optionClass += ' option-revealed-correct';
                        } else if (isSelected && !reviewItem.is_correct) {
                          optionClass += ' option-revealed-wrong';
                        } else {
                          optionClass += ' option-disabled';
                        }
                      } else {
                        if (isSelected) {
                          optionClass += ' option-selected';
                        }
                      }

                      return (
                        <button
                          key={optIndex}
                          type="button"
                          className={optionClass}
                          onClick={() => handleSelectOption(q.id, optIndex)}
                          disabled={Boolean(submissionResult)}
                          aria-pressed={isSelected}
                          aria-label={`Option ${OPTION_LETTERS[optIndex]}: ${opt}`}
                        >
                          <span className="option-letter">{OPTION_LETTERS[optIndex]}</span>
                          <span className="option-text">{renderFormattedText(opt)}</span>
                          {submissionResult && reviewItem && reviewItem.correct_index === optIndex && (
                            <span className="correct-check-icon" aria-label="Correct answer">✓</span>
                          )}
                          {submissionResult && reviewItem && isSelected && !reviewItem.is_correct && (
                            <span className="wrong-x-icon" aria-label="Your incorrect answer">✕</span>
                          )}
                        </button>
                      );
                    })}
                  </div>

                  {/* Revealed Explanation After Submission */}
                  {submissionResult && reviewItem && (
                    <div className="question-explanation-box">
                      <div className="explanation-header">
                        <span className="explanation-icon">💡</span>
                        <strong>Pedagogical Explanation:</strong>
                      </div>
                      <p className="explanation-body">{renderFormattedText(reviewItem.explanation)}</p>

                      {reviewItem.code_evidence && (
                        <div className="explanation-meta-item">
                          <span className="meta-icon">🔍</span>
                          <strong>Code Evidence:</strong>
                          <span className="meta-content">{renderFormattedText(reviewItem.code_evidence)}</span>
                        </div>
                      )}

                      {reviewItem.learning_takeaway && (
                        <div className="explanation-meta-item">
                          <span className="meta-icon">🎯</span>
                          <strong>Key Takeaway:</strong>
                          <span className="meta-content">{renderFormattedText(reviewItem.learning_takeaway)}</span>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Submission Bar */}
          {!submissionResult && (
            <div className="quiz-submit-bar">
              <div className="submit-guidance">
                {allAnswered ? (
                  <span className="guidance-ready">✓ All 5 questions answered. Ready to submit!</span>
                ) : (
                  <span className="guidance-pending">
                    Please answer all {totalQuestions} questions to submit ({totalQuestions - answeredCount} remaining
                    {unansweredQuestions.length > 0 ? `: Question${unansweredQuestions.length > 1 ? 's' : ''} ${unansweredQuestions.join(', ')}` : ''}).
                  </span>
                )}
              </div>

              <button
                type="button"
                className="btn btn-submit-quiz"
                onClick={handleSubmit}
                disabled={!allAnswered || isSubmitting}
              >
                {isSubmitting ? (
                  <>
                    <span className="quiz-spinner" aria-hidden="true" />
                    Evaluating Answers...
                  </>
                ) : (
                  'Submit Quiz & View Results'
                )}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
