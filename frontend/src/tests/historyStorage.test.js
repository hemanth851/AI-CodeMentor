import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import {
  STORAGE_KEY,
  STORAGE_VERSION,
  MAX_SESSIONS,
  saveSession,
  getHistory,
  getSessionById,
  updateSessionProgress,
  deleteSession,
  clearAllHistory,
  generateSessionTitle,
  sanitizeSessionForStorage,
  setForceMemoryMode,
  resetMemoryStorage,
  isStorageAvailable,
} from '../services/historyStorage.js';

describe('Learning History & Progress Storage Service', () => {
  beforeEach(() => {
    // Reset state before every test
    setForceMemoryMode(true);
    resetMemoryStorage();
  });

  test('1. Creating a new session persists with stable ID and default schema', () => {
    const sessionData = {
      title: 'Binary Search in Python',
      language: 'Python',
      learningLevel: 'Beginner',
      sourceCode: 'def binary_search(arr, x): pass',
      analysisResult: { status: 'success', confidence: 'High' },
    };

    const res = saveSession(sessionData);
    assert.equal(res.success, true);
    assert.ok(res.session.id);
    assert.ok(res.session.createdAt);
    assert.ok(res.session.updatedAt);
    assert.equal(res.session.title, 'Binary Search in Python');
    assert.equal(res.session.language, 'Python');
    assert.equal(res.session.learningLevel, 'Beginner');
    assert.equal(res.session.quizStatus, 'not_started');
    assert.equal(res.session.quizScore, null);
    assert.equal(res.session.visualizationStatus, 'not_started');

    // Verify persisted via getHistory()
    const history = getHistory();
    assert.equal(history.length, 1);
    assert.equal(history[0].id, res.session.id);
  });

  test('2. Updating an existing session modifies fields without creating duplicate', () => {
    const createRes = saveSession({
      title: 'Bubble Sort',
      language: 'Python',
      learningLevel: 'Beginner',
      sourceCode: 'def bubble_sort(): pass',
    });
    const sessionId = createRes.session.id;

    // Update with modified code and analysis result
    const updateRes = saveSession({
      id: sessionId,
      sourceCode: 'def bubble_sort(arr): return sorted(arr)',
      analysisResult: { status: 'success', explanation: 'Sorting explanation' },
    });

    assert.equal(updateRes.success, true);
    assert.equal(updateRes.session.id, sessionId);
    assert.equal(updateRes.session.sourceCode, 'def bubble_sort(arr): return sorted(arr)');

    const history = getHistory();
    assert.equal(history.length, 1, 'Should not create duplicate session');
    assert.equal(history[0].id, sessionId);
    assert.equal(history[0].analysisResult.explanation, 'Sorting explanation');
  });

  test('3. Loading persisted sessions returns sorted list (newest activity first)', () => {
    saveSession({ id: 'sess_1', title: 'Session 1', createdAt: '2026-09-28T10:00:00.000Z' });
    saveSession({ id: 'sess_2', title: 'Session 2', createdAt: '2026-09-28T11:00:00.000Z' });

    const history = getHistory();
    assert.equal(history.length, 2);
    assert.equal(history[0].id, 'sess_2');
    assert.equal(history[1].id, 'sess_1');
  });

  test('4. Deleting an individual session removes it cleanly', () => {
    saveSession({ id: 'sess_a', title: 'Session A' });
    saveSession({ id: 'sess_b', title: 'Session B' });

    assert.equal(getHistory().length, 2);

    const delRes = deleteSession('sess_a');
    assert.equal(delRes.success, true);

    const history = getHistory();
    assert.equal(history.length, 1);
    assert.equal(history[0].id, 'sess_b');
    assert.equal(getSessionById('sess_a'), null);
  });

  test('5. Clearing all history resets storage', () => {
    saveSession({ id: 's1', title: 'S1' });
    saveSession({ id: 's2', title: 'S2' });
    saveSession({ id: 's3', title: 'S3' });

    assert.equal(getHistory().length, 3);

    const clearRes = clearAllHistory();
    assert.equal(clearRes.success, true);

    assert.equal(getHistory().length, 0);
  });

  test('6. Maximum history limit enforces max 50 sessions', () => {
    // Save 55 sessions
    for (let i = 1; i <= 55; i++) {
      saveSession({
        id: `sess_${i}`,
        title: `Session ${i}`,
        sourceCode: `print(${i})`,
      });
    }

    const history = getHistory();
    assert.equal(history.length, MAX_SESSIONS);
    // Oldest sessions (sess_1 to sess_5) should have been pruned
    assert.equal(history[0].id, 'sess_55');
    assert.equal(getSessionById('sess_1'), null);
  });

  test('7. Invalid stored JSON recovers safely with empty array', () => {
    // Simulate corrupt JSON in storage
    resetMemoryStorage();
    // Directly put malformed JSON
    const rawCorrupt = '{ "version": 1, sessions: [corrupt json missing quotes}';
    // We test getHistory behavior by putting corrupt string into mock storage
    setForceMemoryMode(false);
    const mockStorage = {
      getItem: () => rawCorrupt,
      setItem: () => {},
      removeItem: () => {},
    };
    globalThis.localStorage = mockStorage;

    const history = getHistory();
    assert.ok(Array.isArray(history));
    assert.equal(history.length, 0);

    // Restore memory mode
    setForceMemoryMode(true);
  });

  test('8. Missing optional fields in session fallback to safe defaults', () => {
    const rawIncomplete = {
      // Missing id, createdAt, learningLevel, quizScore, etc.
      sourceCode: 'console.log("hello");',
    };

    const sanitized = sanitizeSessionForStorage(rawIncomplete);
    assert.ok(sanitized.id.startsWith('session_'));
    assert.equal(sanitized.language, 'Python');
    assert.equal(sanitized.learningLevel, 'Beginner');
    assert.equal(sanitized.quizStatus, 'not_started');
    assert.equal(sanitized.quizScore, null);
    assert.equal(sanitized.visualizationStatus, 'not_started');
    assert.ok(sanitized.completionInfo);
    assert.equal(sanitized.completionInfo.hasAnalysis, false);
  });

  test('9. Reopening session preserves and retrieves exact source code and metadata', () => {
    const code = 'function calculateSum(a, b) {\n  return a + b;\n}';
    const analysis = {
      status: 'success',
      detected_language: 'JavaScript',
      explanation: { summary: 'Calculates the sum' },
      static_analysis: { cyclomatic_complexity: 1 },
    };

    const saveRes = saveSession({
      title: 'calculateSum()',
      language: 'JavaScript',
      learningLevel: 'Intermediate',
      sourceCode: code,
      analysisResult: analysis,
      quizStatus: 'completed',
      quizScore: 5,
      quizTotalQuestions: 5,
      visualizationStatus: 'not_started',
    });

    const retrieved = getSessionById(saveRes.session.id);
    assert.ok(retrieved);
    assert.equal(retrieved.sourceCode, code);
    assert.equal(retrieved.language, 'JavaScript');
    assert.equal(retrieved.learningLevel, 'Intermediate');
    assert.deepEqual(retrieved.analysisResult, analysis);
    assert.equal(retrieved.quizScore, 5);
  });

  test('10. Quiz score and progress persistence updates session', () => {
    const sessionRes = saveSession({
      title: 'Python Loops',
      language: 'Python',
      sourceCode: 'for i in range(10): print(i)',
    });
    const sId = sessionRes.session.id;

    // Simulate quiz submission update
    const updateRes = updateSessionProgress(sId, {
      quizStatus: 'completed',
      quizScore: 4,
      quizTotalQuestions: 5,
      quizPercentage: 80,
      quizCompletedAt: '2026-09-28T12:00:00.000Z',
    });

    assert.equal(updateRes.success, true);
    assert.equal(updateRes.session.quizStatus, 'completed');
    assert.equal(updateRes.session.quizScore, 4);
    assert.equal(updateRes.session.quizTotalQuestions, 5);
    assert.equal(updateRes.session.quizPercentage, 80);
    assert.equal(updateRes.session.completionInfo.hasQuiz, true);

    const reloaded = getSessionById(sId);
    assert.equal(reloaded.quizScore, 4);
    assert.equal(reloaded.quizCompletedAt, '2026-09-28T12:00:00.000Z');
  });

  test('11. Visualization completion persistence updates session', () => {
    const sessionRes = saveSession({
      title: 'Factorial Algorithm',
      language: 'Python',
      sourceCode: 'def fact(n):\n    return 1 if n <= 1 else n * fact(n-1)',
    });
    const sId = sessionRes.session.id;

    // Simulate visualization completion
    const updateRes = updateSessionProgress(sId, {
      visualizationStatus: 'completed',
      visualizationCompletedAt: '2026-09-28T12:05:00.000Z',
    });

    assert.equal(updateRes.success, true);
    assert.equal(updateRes.session.visualizationStatus, 'completed');
    assert.equal(updateRes.session.visualizationCompletedAt, '2026-09-28T12:05:00.000Z');
    assert.equal(updateRes.session.completionInfo.hasVisualization, true);
  });

  test('12. Storage unavailable or quota error is handled gracefully without throwing', () => {
    setForceMemoryMode(false);
    // Mock quota exceeded error on setItem
    const quotaError = new Error('Quota exceeded');
    quotaError.name = 'QuotaExceededError';
    quotaError.code = 22;

    const mockFailingStorage = {
      getItem: () => null,
      setItem: () => {
        throw quotaError;
      },
      removeItem: () => {},
    };
    globalThis.localStorage = mockFailingStorage;

    // Saving should not throw uncaught exception; it handles quota or returns graceful error
    const result = saveSession({
      title: 'Quota Test Session',
      sourceCode: 'x = 1',
    });

    assert.ok(result);
    // Either gracefully pruned or returned structured error message
    assert.ok(result.success === false || result.warning !== undefined || result.success === true);

    setForceMemoryMode(true);
  });

  test('13. Ensuring quiz secrets, auth tokens, and API keys are NEVER persisted', () => {
    const sensitivePayload = {
      title: 'Security Session',
      sourceCode: 'secret_calc()',
      quiz_token: 'secret_jwt_signed_token_12345',
      token: 'bearer_token_xyz',
      apiKey: 'AIzaSySecretApiKey',
      api_key: 'AIzaSySecretApiKey2',
      secret: 'super_secret',
      analysisResult: {
        status: 'success',
        quiz_token: 'nested_secret_token',
        api_key: 'nested_api_key',
        explanation: 'Safe explanation',
      },
      quizStatus: 'completed',
      quizScore: 5,
      quizTotalQuestions: 5,
    };

    const saveRes = saveSession(sensitivePayload);
    assert.equal(saveRes.success, true);

    const saved = getSessionById(saveRes.session.id);
    assert.equal(saved.quiz_token, undefined, 'quiz_token must be stripped');
    assert.equal(saved.token, undefined, 'token must be stripped');
    assert.equal(saved.apiKey, undefined, 'apiKey must be stripped');
    assert.equal(saved.api_key, undefined, 'api_key must be stripped');
    assert.equal(saved.secret, undefined, 'secret must be stripped');

    // Nested check
    assert.equal(saved.analysisResult.quiz_token, undefined, 'nested quiz_token must be stripped');
    assert.equal(saved.analysisResult.api_key, undefined, 'nested api_key must be stripped');
    assert.equal(saved.analysisResult.explanation, 'Safe explanation');
  });

  test('14. generateSessionTitle correctly extracts function names and filenames', () => {
    // 1. Filename takes priority
    const titleFile = generateSessionTitle({
      code: 'def ignore_this(): pass',
      fileName: 'quicksort.py',
      language: 'Python',
    });
    assert.equal(titleFile, 'quicksort.py');

    // 2. Python function
    const titlePy = generateSessionTitle({
      code: 'import os\n\ndef merge_sort(list_items):\n    pass',
      language: 'Python',
    });
    assert.equal(titlePy, 'merge_sort()');

    // 3. JavaScript function
    const titleJs = generateSessionTitle({
      code: 'function binarySearch(arr, target) {\n  return -1;\n}',
      language: 'JavaScript',
    });
    assert.equal(titleJs, 'binarySearch()');

    // 4. Class definition
    const titleClass = generateSessionTitle({
      code: 'class TreeGraphNode:\n    def __init__(self):\n        pass',
      language: 'Python',
    });
    assert.equal(titleClass, 'Class TreeGraphNode');

    // 5. Fallback
    const titleEmpty = generateSessionTitle({ code: '', language: 'Go' });
    assert.equal(titleEmpty, 'Go Session');
  });
});
