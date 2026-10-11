/**
 * API Service for AI CodeMentor
 * Handles communication with the FastAPI backend with timeout protection,
 * robust error parsing, and safe response handling.
 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';
const DEFAULT_TIMEOUT_MS = 45000;

/**
 * Create an AbortSignal with timeout if supported.
 * @param {number} ms
 * @returns {AbortSignal|undefined}
 */
function createTimeoutSignal(ms = DEFAULT_TIMEOUT_MS) {
  try {
    if (typeof AbortSignal !== 'undefined' && typeof AbortSignal.timeout === 'function') {
      return AbortSignal.timeout(ms);
    }
  } catch (e) {
    // Unsupported or restricted environment
  }
  return undefined;
}

/**
 * Safely parse JSON from a response, handling non-JSON error pages (like 502/504 HTML).
 * @param {Response} response
 * @param {string} fallbackMsg
 * @returns {Promise<{ success: boolean, data?: any, error?: string }>}
 */
async function parseResponse(response, fallbackMsg) {
  let data = null;
  try {
    data = await response.json();
  } catch (parseErr) {
    // Non-JSON response (e.g. HTML 502 Bad Gateway from reverse proxy)
  }

  if (!response.ok) {
    let errorMsg = fallbackMsg;

    if (typeof data?.detail === 'string') {
      errorMsg = data.detail;
    } else if (Array.isArray(data?.detail) && data.detail.length > 0) {
      errorMsg = data.detail[0]?.msg || errorMsg;
    } else if (data?.error) {
      errorMsg = data.error;
    } else if (response.status) {
      errorMsg = `${fallbackMsg} (HTTP ${response.status} ${response.statusText || ''})`.trim();
    }

    return {
      success: false,
      error: errorMsg,
    };
  }

  return {
    success: true,
    data,
  };
}

/**
 * Handle fetch errors (network down, abort/timeout, etc.)
 * @param {Error} error
 * @param {string} endpointName
 * @returns {{ success: boolean, error: string }}
 */
function handleFetchError(error, endpointName) {
  console.error(`AI CodeMentor API error on ${endpointName}:`, error);

  if (error?.name === 'TimeoutError') {
    return {
      success: false,
      error: 'The request timed out after 45 seconds. The server may be busy; please try again.',
    };
  }

  if (error?.name === 'AbortError') {
    return {
      success: false,
      error: 'The request was cancelled.',
    };
  }

  return {
    success: false,
    error: 'Unable to connect to the backend server. Please verify the backend is running.',
  };
}

/**
 * Check health of the backend API
 * @returns {Promise<{ success: boolean, data?: object, error?: string }>}
 */
export async function checkBackendHealth() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/health`, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
      },
      signal: createTimeoutSignal(10000),
    });

    return await parseResponse(response, 'Backend health check failed');
  } catch (error) {
    return handleFetchError(error, 'health');
  }
}

/**
 * Send code to the backend for automatic language detection and structured AI explanation.
 * The user does not select a language; the backend detects it automatically.
 * 
 * @param {string} code - The source code to analyze
 * @param {string} learningLevel - Target learning depth (Beginner, Intermediate, Advanced)
 * @param {string|null} filename - Optional filename for uploaded files to assist detection
 * @returns {Promise<{ success: boolean, data?: object, error?: string }>}
 */
export async function analyzeCode(code, learningLevel = 'Beginner', filename = null) {
  try {
    const payload = {
      code,
      learning_level: learningLevel,
    };
    if (filename) {
      payload.filename = filename;
    }

    const response = await fetch(`${API_BASE_URL}/api/analyze`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });

    return await parseResponse(response, 'Unable to analyze the code right now. Please try again.');
  } catch (error) {
    return handleFetchError(error, 'analyze');
  }
}

/**
 * Ask the interactive AI Tutor a question grounded in the current code and analysis.
 * 
 * @param {Object} params
 * @param {string} params.code - Source code currently analyzed
 * @param {string} params.language - Detected programming language
 * @param {string|Object} params.learningLevel - Learning depth (Beginner, Intermediate, Advanced)
 * @param {string} params.question - User's question
 * @param {Object|null} params.staticAnalysis - Optional static analysis facts
 * @param {Object|null} params.analysis - Optional existing structured explanation
 * @param {Array} params.history - Recent in-session conversation history
 * @returns {Promise<{ success: boolean, data?: object, error?: string }>}
 */
export async function askTutor({
  code,
  language,
  learningLevel = 'Beginner',
  question,
  staticAnalysis = null,
  analysis = null,
  history = [],
}) {
  try {
    const payload = {
      code,
      language: language || 'Python',
      learning_level: typeof learningLevel === 'string' ? learningLevel : (learningLevel?.label || 'Beginner'),
      question: (question || '').trim(),
      static_analysis: staticAnalysis,
      analysis: analysis,
      history: (history || []).map((msg) => ({
        role: msg.role === 'user' ? 'user' : 'tutor',
        content: msg.content,
      })),
    };

    const response = await fetch(`${API_BASE_URL}/api/tutor`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });

    return await parseResponse(response, 'The AI Tutor could not answer right now. Please try again.');
  } catch (error) {
    return handleFetchError(error, 'tutor');
  }
}

/**
 * Deterministically trace Python algorithm execution for step-by-step visualization.
 * 
 * @param {string} code - The source code to trace
 * @param {string} language - Target language (Python in Step 7A)
 * @returns {Promise<{ success: boolean, data?: object, error?: string }>}
 */
export async function visualizeCode(code, language = 'Python') {
  try {
    const payload = {
      code,
      language,
    };

    const response = await fetch(`${API_BASE_URL}/api/visualize`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });

    return await parseResponse(response, 'Unable to visualize code execution.');
  } catch (error) {
    return handleFetchError(error, 'visualize');
  }
}

/**
 * Generate a dynamic 5-question code assessment quiz grounded in submitted code.
 * 
 * @param {Object} params
 * @param {string} params.code - Source code to assess
 * @param {string} params.language - Programming language
 * @param {string|Object} params.learningLevel - Target depth (Beginner, Intermediate, Advanced)
 * @param {Object|null} params.analysis - Optional existing explanation
 * @param {Object|null} params.staticAnalysis - Optional static facts
 * @returns {Promise<{ success: boolean, data?: object, error?: string }>}
 */
export async function generateQuiz({
  code,
  language = 'Python',
  learningLevel = 'Beginner',
  analysis = null,
  staticAnalysis = null,
}) {
  try {
    const payload = {
      code,
      language,
      learning_level: typeof learningLevel === 'string' ? learningLevel : (learningLevel?.label || 'Beginner'),
      analysis,
      static_analysis: staticAnalysis,
    };

    const response = await fetch(`${API_BASE_URL}/api/quiz/generate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: createTimeoutSignal(DEFAULT_TIMEOUT_MS),
    });

    return await parseResponse(response, 'Unable to generate assessment quiz. Please try again.');
  } catch (error) {
    return handleFetchError(error, 'quiz/generate');
  }
}

/**
 * Submit quiz answers and receive deterministic score and pedagogical review.
 * 
 * @param {Object} params
 * @param {string} params.quizId - Unique quiz identifier
 * @param {string} params.quizToken - Signed token from generation
 * @param {Object} params.answers - Map of question ID to selected option index
 * @returns {Promise<{ success: boolean, data?: object, error?: string }>}
 */
export async function submitQuiz({ quizId, quizToken, answers }) {
  try {
    const payload = {
      quiz_id: quizId,
      quiz_token: quizToken,
      answers,
    };

    const response = await fetch(`${API_BASE_URL}/api/quiz/submit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: JSON.stringify(payload),
      signal: createTimeoutSignal(15000), // Scoring is deterministic and fast
    });

    return await parseResponse(response, 'Unable to score quiz submission. Please try again.');
  } catch (error) {
    return handleFetchError(error, 'quiz/submit');
  }
}

export default {
  checkBackendHealth,
  analyzeCode,
  askTutor,
  visualizeCode,
  generateQuiz,
  submitQuiz,
  API_BASE_URL,
};
