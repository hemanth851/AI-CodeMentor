/**
 * Generates a fast, stable deterministic fingerprint for a source code string.
 * Used to detect code changes, invalidate stale asynchronous responses,
 * and prevent race conditions.
 *
 * @param {string|null|undefined} code - The source code
 * @returns {string} Unique code fingerprint
 */
export function getCodeFingerprint(code) {
  if (!code || typeof code !== 'string') return '';
  const trimmed = code.trim();
  if (!trimmed) return '';

  let hash = 0;
  for (let i = 0; i < trimmed.length; i++) {
    const char = trimmed.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0; // Convert to 32bit integer
  }
  return `fp_${hash}_${trimmed.length}`;
}

/**
 * Check if the given language string corresponds to Python.
 * 
 * @param {string|null|undefined} lang 
 * @returns {boolean}
 */
export function isPythonLanguage(lang) {
  if (!lang || typeof lang !== 'string') return false;
  return lang.trim().toLowerCase().includes('python');
}
