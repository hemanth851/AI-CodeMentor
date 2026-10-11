/**
 * Configuration and constants for Code Editor, Languages, and Learning Levels
 */

export const SUPPORTED_LANGUAGES = [
  { id: 'python', label: 'Python', monacoLang: 'python', extensions: ['.py'] },
  { id: 'java', label: 'Java', monacoLang: 'java', extensions: ['.java'] },
  { id: 'c', label: 'C', monacoLang: 'c', extensions: ['.c'] },
  { id: 'cpp', label: 'C++', monacoLang: 'cpp', extensions: ['.cpp', '.cc', '.cxx'] },
  { id: 'javascript', label: 'JavaScript', monacoLang: 'javascript', extensions: ['.js', '.jsx'] },
  { id: 'typescript', label: 'TypeScript', monacoLang: 'typescript', extensions: ['.ts', '.tsx'] },
  { id: 'csharp', label: 'C#', monacoLang: 'csharp', extensions: ['.cs'] },
  { id: 'go', label: 'Go', monacoLang: 'go', extensions: ['.go'] },
  { id: 'rust', label: 'Rust', monacoLang: 'rust', extensions: ['.rs'] },
  { id: 'php', label: 'PHP', monacoLang: 'php', extensions: ['.php'] },
  { id: 'kotlin', label: 'Kotlin', monacoLang: 'kotlin', extensions: ['.kt', '.kts'] },
  { id: 'swift', label: 'Swift', monacoLang: 'swift', extensions: ['.swift'] },
  { id: 'sql', label: 'SQL', monacoLang: 'sql', extensions: ['.sql'] },
];

export const LEARNING_LEVELS = [
  { id: 'beginner', label: 'Beginner' },
  { id: 'intermediate', label: 'Intermediate' },
  { id: 'advanced', label: 'Advanced' },
];

export const DEFAULT_SAMPLE_CODE = `def find_max(numbers):
    maximum = numbers[0]

    for number in numbers:
        if number > maximum:
            maximum = number

    return maximum

numbers = [4, 8, 2, 10, 6]
print(find_max(numbers))
`;

export const MAX_FILE_SIZE_BYTES = 100 * 1024; // 100 KB
export const MAX_FILE_SIZE_LABEL = '100 KB';

export const ACCEPTED_FILE_EXTENSIONS =
  '.py,.java,.c,.cpp,.cc,.cxx,.js,.jsx,.ts,.tsx,.cs,.go,.rs,.php,.kt,.kts,.swift,.sql';

/**
 * Match file extension to supported language definition
 * @param {string} filename
 * @returns {typeof SUPPORTED_LANGUAGES[0] | null}
 */
export function detectLanguageFromFilename(filename) {
  if (!filename) return null;
  const lowerName = filename.toLowerCase();
  for (const lang of SUPPORTED_LANGUAGES) {
    if (lang.extensions.some((ext) => lowerName.endsWith(ext))) {
      return lang;
    }
  }
  return null;
}

/**
 * Map detected language name to Monaco language ID
 * @param {string} langName
 * @returns {string}
 */
export function getMonacoLang(langName) {
  if (!langName) return 'plaintext';
  const clean = langName.toLowerCase().replace(/[^a-z0-9#+]/g, '');
  const match = SUPPORTED_LANGUAGES.find(
    (l) => l.label.toLowerCase() === clean || l.id === clean
  );
  return match ? match.monacoLang : 'plaintext';
}
