/**
 * Local Storage Utility for AI CodeMentor Learning History & Progress (Step 9)
 * 
 * Provides robust persistence for learning sessions:
 * - Versioned storage schema
 * - Maximum limit retention (50 sessions)
 * - Safe error handling (quota exceeded, disabled storage, corrupt JSON)
 * - Strict privacy: NO API keys, tokens, or answer secrets stored
 * - Automatic title generation and deduplication/updates
 */

export const STORAGE_KEY = 'ai_codementor_history_v1';
export const STORAGE_VERSION = 1;
export const MAX_SESSIONS = 50;

// In-memory fallback if localStorage is disabled or unavailable
let memoryStorageMap = new Map();
let forceMemoryMode = false;

/**
 * Configure memory mode (useful for testing or when storage is restricted)
 */
export function setForceMemoryMode(enable = true) {
  forceMemoryMode = enable;
}

/**
 * Reset memory storage (useful for tests)
 */
export function resetMemoryStorage() {
  memoryStorageMap.clear();
}

/**
 * Safely get the active localStorage object if available.
 */
function getStorage() {
  if (forceMemoryMode) return null;
  try {
    if (typeof window !== 'undefined' && window.localStorage) {
      // Test read/write access (e.g. Safari private browsing or disabled cookies)
      const testKey = '__acm_storage_test__';
      window.localStorage.setItem(testKey, '1');
      window.localStorage.removeItem(testKey);
      return window.localStorage;
    }
    if (typeof globalThis !== 'undefined' && globalThis.localStorage) {
      return globalThis.localStorage;
    }
  } catch (e) {
    // Storage access restricted or disabled
    return null;
  }
  return null;
}

/**
 * Check if browser persistent storage is operational.
 * @returns {boolean}
 */
export function isStorageAvailable() {
  return Boolean(getStorage());
}

/**
 * Generate a descriptive, human-readable session title from code or metadata.
 * 
 * @param {Object} params
 * @param {string} [params.code] - Source code snippet
 * @param {string} [params.fileName] - Uploaded filename if any
 * @param {string} [params.language] - Programming language
 * @returns {string}
 */
export function generateSessionTitle({ code, fileName, language } = {}) {
  if (fileName && fileName !== 'snippet' && fileName !== 'untitled') {
    return fileName;
  }

  const langName = language || 'Code';

  if (!code || typeof code !== 'string') {
    return `${langName} Session`;
  }

  const lines = code.split('\n').map((l) => l.trim()).filter(Boolean);
  if (lines.length === 0) {
    return `${langName} Session`;
  }

  // 1. Look for function / class / method definition
  for (const line of lines.slice(0, 20)) {
    const fnMatch = line.match(/(?:def|function|func|fn)\s+([A-Za-z0-9_]+)/);
    if (fnMatch) {
      return `${fnMatch[1]}()`;
    }
    const classMatch = line.match(/(?:class|struct|interface)\s+([A-Za-z0-9_]+)/);
    if (classMatch) {
      return `Class ${classMatch[1]}`;
    }
    const arrowFnMatch = line.match(/(?:const|let|var)\s+([A-Za-z0-9_]+)\s*=\s*(?:async\s*)?\(/);
    if (arrowFnMatch) {
      return `${arrowFnMatch[1]}()`;
    }
  }

  // 2. Look for descriptive comment or clean initial statement
  for (const line of lines.slice(0, 5)) {
    const clean = line.replace(/^[/#*#-]+\s*/, '').replace(/[*#/]+$/, '').trim();
    if (
      clean.length >= 3 &&
      clean.length <= 45 &&
      !clean.startsWith('import ') &&
      !clean.startsWith('from ') &&
      !clean.startsWith('#include') &&
      !clean.startsWith('package ') &&
      !clean.startsWith('using ')
    ) {
      return clean;
    }
  }

  return `${langName} Learning Session`;
}

/**
 * Sanitize and validate session object to ensure no sensitive secrets
 * (like quiz_token, auth tokens, API keys) are stored.
 * 
 * @param {Object} raw
 * @returns {Object}
 */
export function sanitizeSessionForStorage(raw) {
  if (!raw || typeof raw !== 'object') {
    return null;
  }

  const clean = { ...raw };

  // Explicitly remove any secrets or tokens
  delete clean.token;
  delete clean.quiz_token;
  delete clean.apiKey;
  delete clean.api_key;
  delete clean.secret;
  delete clean.authorization;

  // Sanitize nested analysisResult if present
  if (clean.analysisResult && typeof clean.analysisResult === 'object') {
    const ar = { ...clean.analysisResult };
    delete ar.token;
    delete ar.quiz_token;
    delete ar.apiKey;
    delete ar.api_key;
    clean.analysisResult = ar;
  }

  // Ensure stable session ID
  if (!clean.id || typeof clean.id !== 'string') {
    clean.id = `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
  }

  const nowIso = new Date().toISOString();
  clean.createdAt = clean.createdAt || nowIso;
  clean.updatedAt = clean.updatedAt || nowIso;
  clean.title = clean.title || `${clean.language || 'Code'} Session`;
  clean.language = clean.language || 'Python';
  clean.learningLevel = clean.learningLevel || 'Beginner';
  clean.sourceCode = typeof clean.sourceCode === 'string' ? clean.sourceCode : '';

  // Standardize Quiz Progress fields
  clean.quizStatus = clean.quizStatus || 'not_started';
  clean.quizScore = typeof clean.quizScore === 'number' ? clean.quizScore : null;
  clean.quizTotalQuestions = typeof clean.quizTotalQuestions === 'number' ? clean.quizTotalQuestions : null;
  clean.quizPercentage = typeof clean.quizPercentage === 'number' ? clean.quizPercentage : (
    clean.quizScore !== null && clean.quizTotalQuestions
      ? Math.round((clean.quizScore / clean.quizTotalQuestions) * 100)
      : null
  );
  clean.quizCompletedAt = clean.quizCompletedAt || null;

  // Standardize Visualization Progress fields
  clean.visualizationStatus = clean.visualizationStatus || 'not_started';
  clean.visualizationCompletedAt = clean.visualizationCompletedAt || null;

  // Standardize Completion Information
  clean.completionInfo = clean.completionInfo && typeof clean.completionInfo === 'object' ? clean.completionInfo : {
    hasAnalysis: Boolean(clean.analysisResult && clean.analysisResult.status === 'success'),
    hasQuiz: clean.quizStatus === 'completed',
    hasVisualization: clean.visualizationStatus === 'completed',
    completedAt: clean.quizCompletedAt || clean.visualizationCompletedAt || clean.updatedAt,
  };

  return clean;
}

/**
 * Retrieve all learning sessions from persistent storage.
 * Handles malformed JSON, missing data, and schema migration safely.
 * 
 * @returns {Array<Object>} Sorted list of learning sessions (newest first).
 */
export function getHistory() {
  const storage = getStorage();

  let rawString = null;
  if (storage) {
    try {
      rawString = storage.getItem(STORAGE_KEY);
    } catch (e) {
      console.warn('Failed to read from localStorage:', e);
    }
  } else {
    rawString = memoryStorageMap.get(STORAGE_KEY) || null;
  }

  if (!rawString) {
    return [];
  }

  try {
    const parsed = JSON.parse(rawString);
    let sessionList = [];

    // Support versioned wrapper { version: 1, sessions: [...] }
    if (parsed && typeof parsed === 'object') {
      if (Array.isArray(parsed.sessions)) {
        sessionList = parsed.sessions;
      } else if (Array.isArray(parsed)) {
        // Direct array fallback
        sessionList = parsed;
      }
    }

    // Sanitize every session item and filter out completely invalid entries
    const sanitizedList = sessionList
      .map((item) => sanitizeSessionForStorage(item))
      .filter(Boolean);

    // Sort by updatedAt descending (newest activity first)
    sanitizedList.sort((a, b) => {
      const timeA = new Date(a.updatedAt || a.createdAt || 0).getTime();
      const timeB = new Date(b.updatedAt || b.createdAt || 0).getTime();
      return timeB - timeA;
    });

    return sanitizedList;
  } catch (err) {
    console.error('AI CodeMentor history storage contains invalid JSON. Safely recovering with empty state.', err);
    return [];
  }
}

/**
 * Internal helper to write the session list to storage.
 * Handles QuotaExceededError by pruning older records and retrying.
 * 
 * @param {Array<Object>} sessions
 * @returns {{ success: boolean, error?: string }}
 */
function writeHistoryList(sessions) {
  // Enforce max retention limit
  const prunedList = sessions.slice(0, MAX_SESSIONS);

  const payload = {
    version: STORAGE_VERSION,
    updatedAt: new Date().toISOString(),
    sessions: prunedList,
  };

  const jsonStr = JSON.stringify(payload);
  const storage = getStorage();

  if (!storage) {
    memoryStorageMap.set(STORAGE_KEY, jsonStr);
    return { success: true, isMemoryFallback: true };
  }

  try {
    storage.setItem(STORAGE_KEY, jsonStr);
    return { success: true };
  } catch (error) {
    // Check if error is quota exceeded
    const isQuotaError =
      error &&
      (error.name === 'QuotaExceededError' ||
        error.name === 'NS_ERROR_DOM_QUOTA_REACHED' ||
        error.code === 22 ||
        error.code === 1014);

    if (isQuotaError) {
      console.warn('Storage quota exceeded. Pruning older sessions and retrying...');
      try {
        // Prune down to 25 sessions
        const halvedList = prunedList.slice(0, 25);
        const retryPayload = {
          version: STORAGE_VERSION,
          updatedAt: new Date().toISOString(),
          sessions: halvedList,
        };
        storage.setItem(STORAGE_KEY, JSON.stringify(retryPayload));
        return { success: true, warning: 'Storage quota reached; older sessions were pruned.' };
      } catch (retryErr) {
        return {
          success: false,
          error: 'Browser storage quota exceeded. Please clear some history.',
        };
      }
    }

    return {
      success: false,
      error: error.message || 'Failed to save to local storage.',
    };
  }
}

/**
 * Save a new learning session or update an existing session.
 * 
 * @param {Object} sessionData
 * @returns {{ success: boolean, session?: Object, error?: string }}
 */
export function saveSession(sessionData) {
  if (!sessionData || typeof sessionData !== 'object') {
    return { success: false, error: 'Invalid session payload.' };
  }

  const existingHistory = getHistory();
  const nowIso = new Date().toISOString();

  let targetId = sessionData.id;
  let isUpdate = false;
  let targetSession = null;

  if (targetId) {
    const existingIdx = existingHistory.findIndex((s) => s.id === targetId);
    if (existingIdx !== -1) {
      isUpdate = true;
      targetSession = {
        ...existingHistory[existingIdx],
        ...sessionData,
        id: targetId,
        createdAt: existingHistory[existingIdx].createdAt || nowIso,
        updatedAt: nowIso,
      };
      existingHistory[existingIdx] = targetSession;
    }
  }

  if (!isUpdate) {
    // Generate new stable ID
    targetId = targetId || `session_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
    targetSession = {
      ...sessionData,
      id: targetId,
      createdAt: sessionData.createdAt || nowIso,
      updatedAt: nowIso,
    };
    // Prepend to list
    existingHistory.unshift(targetSession);
  }

  const sanitized = sanitizeSessionForStorage(targetSession);
  if (!sanitized) {
    return { success: false, error: 'Failed to sanitize session data.' };
  }

  // Update in array
  const updatedIdx = existingHistory.findIndex((s) => s.id === targetId);
  if (updatedIdx !== -1) {
    existingHistory[updatedIdx] = sanitized;
  }

  // Sort again
  existingHistory.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());

  const result = writeHistoryList(existingHistory);
  if (!result.success) {
    return { success: false, error: result.error };
  }

  return {
    success: true,
    session: sanitized,
    warning: result.warning,
    isMemoryFallback: result.isMemoryFallback,
  };
}

/**
 * Update specific progress fields of an existing session (quiz, visualization, etc.)
 * 
 * @param {string} sessionId
 * @param {Object} updates
 * @returns {{ success: boolean, session?: Object, error?: string }}
 */
export function updateSessionProgress(sessionId, updates) {
  if (!sessionId) {
    return { success: false, error: 'Session ID is required.' };
  }

  const existingHistory = getHistory();
  const sessionIdx = existingHistory.findIndex((s) => s.id === sessionId);

  if (sessionIdx === -1) {
    return { success: false, error: `Session not found: ${sessionId}` };
  }

  const current = existingHistory[sessionIdx];
  const nowIso = new Date().toISOString();

  const merged = {
    ...current,
    ...updates,
    id: sessionId,
    updatedAt: nowIso,
    completionInfo: {
      ...(current.completionInfo || {}),
      ...(updates.completionInfo || {}),
    },
  };

  // Recalculate completion info flags
  merged.completionInfo.hasAnalysis = Boolean(merged.analysisResult && merged.analysisResult.status === 'success');
  merged.completionInfo.hasQuiz = merged.quizStatus === 'completed';
  merged.completionInfo.hasVisualization = merged.visualizationStatus === 'completed';
  merged.completionInfo.completedAt = updates.quizCompletedAt || updates.visualizationCompletedAt || nowIso;

  const sanitized = sanitizeSessionForStorage(merged);
  existingHistory[sessionIdx] = sanitized;

  existingHistory.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());

  const writeResult = writeHistoryList(existingHistory);
  if (!writeResult.success) {
    return { success: false, error: writeResult.error };
  }

  return {
    success: true,
    session: sanitized,
  };
}

/**
 * Find a single session by its unique ID.
 * 
 * @param {string} sessionId
 * @returns {Object|null}
 */
export function getSessionById(sessionId) {
  if (!sessionId) return null;
  const history = getHistory();
  return history.find((s) => s.id === sessionId) || null;
}

/**
 * Delete an individual learning session.
 * 
 * @param {string} sessionId
 * @returns {{ success: boolean, error?: string }}
 */
export function deleteSession(sessionId) {
  if (!sessionId) {
    return { success: false, error: 'Session ID required.' };
  }

  const history = getHistory();
  const filtered = history.filter((s) => s.id !== sessionId);

  if (filtered.length === history.length) {
    return { success: true }; // Nothing to delete
  }

  const result = writeHistoryList(filtered);
  return result;
}

/**
 * Clear all learning history sessions from storage.
 * 
 * @returns {{ success: boolean, error?: string }}
 */
export function clearAllHistory() {
  const storage = getStorage();

  if (storage) {
    try {
      storage.removeItem(STORAGE_KEY);
    } catch (e) {
      console.warn('Failed to remove history from localStorage:', e);
    }
  }

  memoryStorageMap.delete(STORAGE_KEY);
  return { success: true };
}

export default {
  STORAGE_KEY,
  STORAGE_VERSION,
  MAX_SESSIONS,
  isStorageAvailable,
  generateSessionTitle,
  sanitizeSessionForStorage,
  getHistory,
  getSessionById,
  saveSession,
  updateSessionProgress,
  deleteSession,
  clearAllHistory,
  setForceMemoryMode,
  resetMemoryStorage,
};
