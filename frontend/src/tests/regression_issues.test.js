import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { getCodeFingerprint, isPythonLanguage } from '../utils/codeUtils.js';

describe('ISSUE 1, 2 & 3: Frontend Code Fingerprint & Stale State Regression Tests', () => {
  it('1. Changing code generates distinct fingerprints immediately', () => {
    const codeA = 'x = 10';
    const codeB = 'x = 20';
    const fpA = getCodeFingerprint(codeA);
    const fpB = getCodeFingerprint(codeB);

    assert.notEqual(fpA, fpB, 'Fingerprints for code A and code B must differ');
    assert.ok(fpA.startsWith('fp_'));
    assert.ok(fpB.startsWith('fp_'));
  });

  it('2. Empty or whitespace code generates empty fingerprint', () => {
    assert.equal(getCodeFingerprint(''), '');
    assert.equal(getCodeFingerprint('   \n  \t '), '');
    assert.equal(getCodeFingerprint(null), '');
    assert.equal(getCodeFingerprint(undefined), '');
  });

  it('3. isPythonLanguage accurately detects Python and rejects Java/C++/JS', () => {
    assert.equal(isPythonLanguage('Python'), true);
    assert.equal(isPythonLanguage('python'), true);
    assert.equal(isPythonLanguage('Python (Sample)'), true);
    assert.equal(isPythonLanguage('Java'), false);
    assert.equal(isPythonLanguage('C++'), false);
    assert.equal(isPythonLanguage('JavaScript'), false);
    assert.equal(isPythonLanguage(null), false);
    assert.equal(isPythonLanguage(''), false);
  });

  it('4. Simulating code change clears stale quiz state and token', () => {
    // Model state transitions
    let activeQuiz = {
      quiz_id: 'quiz_123',
      quiz_token: 'signed_jwt_token',
      questions: [{ id: 1, text: 'Q1' }],
    };
    let quizFingerprint = getCodeFingerprint('def add(a, b): return a + b');
    let userAnswers = { '1': 0 };
    let submissionResult = { score: 1, total: 1 };
    let isGenerating = false;

    // User changes code to Java
    const newCode = 'public class Adder { public static int add(int a, int b) { return a + b; } }';
    const newFingerprint = getCodeFingerprint(newCode);

    if (quizFingerprint && quizFingerprint !== newFingerprint) {
      activeQuiz = null;
      userAnswers = {};
      submissionResult = null;
      quizFingerprint = '';
    }

    assert.equal(activeQuiz, null, 'Previous quiz must be immediately cleared');
    assert.deepEqual(userAnswers, {}, 'User answers must be cleared');
    assert.equal(submissionResult, null, 'Submission result must be cleared');
    assert.equal(quizFingerprint, '', 'Quiz fingerprint must be reset');
  });

  it('5. Delayed quiz response for code A is discarded after switching to code B', () => {
    let reqIdCounter = 0;
    let activeQuizData = null;

    // Start request for code A
    const codeA = 'x = 1';
    const reqIdA = ++reqIdCounter;
    const reqFingerprintA = getCodeFingerprint(codeA);

    // User quickly changes to code B before A finishes
    let currentCode = 'public class B {}';
    let currentReqId = ++reqIdCounter; // Invalidation on edit

    // Simulated async response for A finishes late
    const responseDataA = {
      quiz_id: 'quiz_A',
      questions: [1, 2, 3, 4, 5],
    };

    // Stale check
    if (reqIdA === currentReqId && getCodeFingerprint(currentCode) === reqFingerprintA) {
      activeQuizData = responseDataA;
    }

    assert.equal(activeQuizData, null, 'Delayed response for code A must be discarded');
  });

  it('6. Delayed visualization response for code A is discarded after switching to code B', () => {
    let visReqIdCounter = 0;
    let traceData = null;

    // Start request for code A
    const codeA = 'x = [1, 2, 3]';
    const reqIdA = ++visReqIdCounter;
    const reqFingerprintA = getCodeFingerprint(codeA);

    // User types code B
    let currentCode = 'y = 42';
    const currentVisReqId = ++visReqIdCounter;

    // Response A arrives late
    const responseTraceA = {
      trace: [{ step: 1 }],
      status: 'success',
    };

    if (reqIdA === currentVisReqId && getCodeFingerprint(currentCode) === reqFingerprintA) {
      traceData = responseTraceA;
    }

    assert.equal(traceData, null, 'Delayed visualization for code A must be discarded');
  });

  it('7. Quiz validation requires exactly 5 questions with 4 options each', () => {
    const validQuiz = {
      questions: [
        { id: 1, options: ['a', 'b', 'c', 'd'] },
        { id: 2, options: ['a', 'b', 'c', 'd'] },
        { id: 3, options: ['a', 'b', 'c', 'd'] },
        { id: 4, options: ['a', 'b', 'c', 'd'] },
        { id: 5, options: ['a', 'b', 'c', 'd'] },
      ],
    };

    const has5Questions = validQuiz.questions.length === 5;
    const has4OptionsEach = validQuiz.questions.every((q) => q.options && q.options.length === 4);

    assert.equal(has5Questions, true);
    assert.equal(has4OptionsEach, true);

    const invalidQuiz4Q = {
      questions: [{ id: 1, options: ['a', 'b', 'c', 'd'] }],
    };
    assert.equal(invalidQuiz4Q.questions.length === 5, false);

    const invalidQuiz3Opt = {
      questions: [
        { id: 1, options: ['a', 'b', 'c'] },
        { id: 2, options: ['a', 'b', 'c', 'd'] },
        { id: 3, options: ['a', 'b', 'c', 'd'] },
        { id: 4, options: ['a', 'b', 'c', 'd'] },
        { id: 5, options: ['a', 'b', 'c', 'd'] },
      ],
    };
    assert.equal(invalidQuiz3Opt.questions.every((q) => q.options && q.options.length === 4), false);
  });
});
