import React, { useState } from 'react';

export default function AnalysisResult({
  analysisData,
  isLoading,
  learningLevel,
  error,
  onDismiss,
  isCodeModified = false,
}) {
  const [copied, setCopied] = useState(false);

  // 1. Loading State
  if (isLoading) {
    return (
      <section
        id="analysis-result-section"
        className="analysis-result-card loading-state"
        aria-live="polite"
        aria-label="AI CodeMentor is analyzing code"
      >
        <div className="analysis-loading-container">
          <div className="analysis-spinner-glow">
            <div className="analysis-spinner-ring" />
            <svg
              className="analysis-spinner-icon"
              width="28"
              height="28"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            </svg>
          </div>
          <div className="analysis-loading-text-group">
            <h3 className="analysis-loading-title">Analyzing your code...</h3>
            <p className="analysis-loading-subtitle">
              AI CodeMentor is inspecting code structure, detecting the programming language, and
              generating a structured <span className="highlight-level">{learningLevel?.label || learningLevel}</span> explanation.
            </p>
          </div>
          <div className="analysis-skeleton-lines">
            <div className="skeleton-line line-full" />
            <div className="skeleton-line line-three-quarters" />
            <div className="skeleton-line line-half" />
          </div>
        </div>
      </section>
    );
  }

  // 2. Error State
  if (error && !analysisData) {
    return (
      <section
        id="analysis-result-section"
        className="analysis-result-card error-state"
        aria-live="assertive"
        aria-label="Analysis Error"
      >
        <div className="analysis-error-header">
          <div className="analysis-error-icon">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
          </div>
          <h3 className="analysis-error-title">Analysis Failed</h3>
          {onDismiss && (
            <button
              type="button"
              className="analysis-close-btn"
              onClick={onDismiss}
              aria-label="Dismiss error"
            >
              &times;
            </button>
          )}
        </div>
        <p className="analysis-error-message">{error}</p>
      </section>
    );
  }

  // 3. No analysis yet
  if (!analysisData) {
    return null;
  }

  const {
    status,
    detected_language,
    confidence,
    message,
    overall_purpose,
    how_it_works,
    line_by_line = [],
    variables = [],
    functions = [],
    algorithm_logic,
    time_complexity,
    space_complexity,
    potential_issues = [],
    key_learning_points = [],
    static_analysis,
  } = analysisData;

  // 4. Ambiguous / Short Snippet State (e.g. x = 10)
  if (status === 'ambiguous') {
    return (
      <section
        id="analysis-result-section"
        className="analysis-result-card ambiguous-state"
        aria-live="polite"
        aria-label="Ambiguous code snippet notice"
      >
        <div className="ambiguous-box">
          <div className="ambiguous-badge">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12.01" y2="8" />
            </svg>
            Language Undetermined
          </div>
          <h3 className="ambiguous-title">More Code Needed</h3>
          <p className="ambiguous-message">
            {message ||
              'The code snippet is too short to confidently determine the programming language. Please provide a few more lines of code so I can identify the language and explain it accurately.'}
          </p>
          <div className="ambiguous-tip">
            <strong>Tip:</strong> Short snippets like <code>x = 10</code> exist in multiple languages (Python, Ruby, Lua, Swift, etc.). Adding a function definition, loop, type annotation, or standard library call will allow AI CodeMentor to accurately recognize and explain your code.
          </div>
        </div>
      </section>
    );
  }

  // 5. Unsupported Language State
  if (status === 'unsupported') {
    return (
      <section
        id="analysis-result-section"
        className="analysis-result-card unsupported-state"
        aria-live="polite"
        aria-label="Unsupported programming language notice"
      >
        <div className="unsupported-box">
          <div className="unsupported-badge">
            <svg
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="4.93" y1="4.93" x2="19.07" y2="19.07" />
            </svg>
            Unsupported Language
          </div>
          <h3 className="unsupported-title">Language Not Supported</h3>
          <p className="unsupported-message">
            {message || 'This programming language is not currently supported by AI CodeMentor.'}
          </p>
          <div className="supported-langs-pill-list">
            <span className="pill-list-label">Officially supported languages:</span>
            <div className="pill-tags">
              {[
                'Python', 'Java', 'C', 'C++', 'JavaScript', 'TypeScript',
                'C#', 'Go', 'Rust', 'PHP', 'Kotlin', 'Swift', 'SQL',
              ].map((lang) => (
                <span key={lang} className="lang-mini-pill">{lang}</span>
              ))}
            </div>
          </div>
        </div>
      </section>
    );
  }

  // 6. Success State: Format copyable markdown summary
  const handleCopy = async () => {
    try {
      const structureLines = static_analysis?.structure
        ? [
            '## Code Structure',
            static_analysis.structure.functions !== null ? `- Functions: ${static_analysis.structure.functions}` : null,
            static_analysis.structure.variables !== null ? `- Variables: ${static_analysis.structure.variables}` : null,
            static_analysis.structure.loops !== null ? `- Loops: ${static_analysis.structure.loops}` : null,
            static_analysis.structure.conditionals !== null ? `- Conditions: ${static_analysis.structure.conditionals}` : null,
            static_analysis.structure.recursion !== null ? `- Recursion: ${static_analysis.structure.recursion ? 'Yes' : 'No'}` : null,
            '',
          ].filter(Boolean)
        : [];

      const summaryText = [
        `# AI CodeMentor Explanation`,
        `Detected Language: ${detected_language} (${confidence} confidence)`,
        `Learning Level: ${learningLevel?.label || learningLevel}`,
        '',
        ...structureLines,
        `## Overall Purpose`,
        overall_purpose,
        '',
        `## How It Works`,
        how_it_works,
        '',
        `## Line-by-Line Explanation`,
        ...line_by_line.map((item) => `Line ${item.line}: \`${item.code}\`\n-> ${item.explanation}`),
        '',
        `## Variables`,
        variables.length > 0
          ? variables.map((v) => `- **${v.name}**: ${v.purpose}`).join('\n')
          : 'None',
        '',
        `## Functions`,
        functions.length > 0
          ? functions.map((f) => `- **${f.name}**(${f.parameters?.join(', ') || ''}): ${f.purpose}`).join('\n')
          : 'None',
        '',
        `## Algorithm / Logic`,
        algorithm_logic,
        '',
        `## Complexity`,
        `- Time Complexity: ${time_complexity}`,
        `- Space Complexity: ${space_complexity}`,
        '',
        `## Potential Issues`,
        potential_issues.length > 0
          ? potential_issues.map((i) => `- [${i.severity.toUpperCase()}] ${i.description}`).join('\n')
          : 'None detected',
        '',
        `## Key Learning Points`,
        ...key_learning_points.map((p) => `- ${p}`),
      ].join('\n');

      await navigator.clipboard.writeText(summaryText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy explanation:', err);
    }
  };

  const isModerate = confidence?.toLowerCase() === 'moderate';
  const displayLangText = isModerate
    ? `Likely ${detected_language}`
    : detected_language || 'Detected';
  const confidenceBadgeText = isModerate ? 'Moderate' : 'High';

  return (
    <section
      id="analysis-result-section"
      className="analysis-result-card structured-view"
      aria-label="Structured AI Code Explanation"
    >
      {/* Top Banner / Detection & Meta Header */}
      <div className="analysis-header">
        <div className="analysis-header-left">
          <div className="analysis-badge-mentor">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
            </svg>
            AI Code Explanation
          </div>
          <div className="analysis-tags">
            <div className="detection-tag-wrapper">
              <span className="detection-label">Detected Language:</span>
              <span className="analysis-tag-lang">{displayLangText}</span>
            </div>
            <div className="confidence-tag-wrapper">
              <span className="confidence-label">Confidence:</span>
              <span className={`analysis-tag-conf conf-${confidence?.toLowerCase()}`}>
                {confidenceBadgeText}
              </span>
            </div>
            <span className={`analysis-tag-level level-${(learningLevel?.label || learningLevel || 'beginner').toLowerCase()}`}>
              {learningLevel?.label || learningLevel || 'Beginner'}
            </span>
          </div>
        </div>

        <div className="analysis-header-right">
          <button
            id="copy-analysis-btn"
            type="button"
            className={`btn-action-copy ${copied ? 'copied' : ''}`}
            onClick={handleCopy}
            title="Copy structured explanation"
          >
            {copied ? (
              <>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                Copied!
              </>
            ) : (
              <>
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                Copy Explanation
              </>
            )}
          </button>
          {onDismiss && (
            <button
              type="button"
              className="analysis-close-btn"
              onClick={onDismiss}
              aria-label="Close explanation"
              title="Close explanation"
            >
              &times;
            </button>
          )}
        </div>
      </div>

      {isCodeModified && (
        <div className="analysis-stale-banner" role="status" aria-label="Code modified warning">
          <span className="stale-icon">⚠️</span>
          <span className="stale-text">
            Editor code was modified after this explanation was generated. Click <strong>Analyze Code</strong> to refresh explanations and insights for your latest code.
          </span>
        </div>
      )}

      {isModerate && (
        <div className="moderate-confidence-notice">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          Language identified as <strong>{detected_language}</strong> with moderate confidence. Explanation is provided based on the most probable interpretation of this syntax.
        </div>
      )}

      {/* Structured Content Grid */}
      <div className="structured-content-grid">
        {/* Code Structure (Deterministic Static Analysis) */}
        {static_analysis?.structure && static_analysis?.parse_status !== 'unavailable' && (
          <div className="structured-card code-structure-card full-width" id="code-structure-card">
            <div className="card-header">
              <div className="card-icon cyan">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 6h16M4 12h16M4 18h7" />
                </svg>
              </div>
              <h4 className="card-title">Code Structure</h4>
              <span className="items-count-badge">Static Analysis</span>
            </div>
            <div className="card-body">
              <div className="structure-metrics-grid">
                {static_analysis.structure.functions !== null && static_analysis.structure.functions !== undefined && (
                  <div className="structure-metric-item">
                    <span className="metric-label">Functions</span>
                    <span className="metric-value">{static_analysis.structure.functions}</span>
                  </div>
                )}
                {static_analysis.structure.variables !== null && static_analysis.structure.variables !== undefined && (
                  <div className="structure-metric-item">
                    <span className="metric-label">Variables</span>
                    <span className="metric-value">{static_analysis.structure.variables}</span>
                  </div>
                )}
                {static_analysis.structure.loops !== null && static_analysis.structure.loops !== undefined && (
                  <div className="structure-metric-item">
                    <span className="metric-label">Loops</span>
                    <span className="metric-value">{static_analysis.structure.loops}</span>
                  </div>
                )}
                {static_analysis.structure.conditionals !== null && static_analysis.structure.conditionals !== undefined && (
                  <div className="structure-metric-item">
                    <span className="metric-label">Conditions</span>
                    <span className="metric-value">{static_analysis.structure.conditionals}</span>
                  </div>
                )}
                {static_analysis.structure.recursion !== null && static_analysis.structure.recursion !== undefined && (
                  <div className="structure-metric-item">
                    <span className="metric-label">Recursion</span>
                    <span className={`metric-value ${static_analysis.structure.recursion ? 'value-recursion-yes' : ''}`}>
                      {static_analysis.structure.recursion ? 'Yes' : 'No'}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* 1. Overall Purpose */}
        <div className="structured-card purpose-card">
          <div className="card-header">
            <div className="card-icon blue">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 16v-4" />
                <path d="M12 8h.01" />
              </svg>
            </div>
            <h4 className="card-title">Overall Purpose</h4>
          </div>
          <div className="card-body">
            <p className="purpose-text">{overall_purpose}</p>
          </div>
        </div>

        {/* 2. How the Code Works */}
        <div className="structured-card flow-card">
          <div className="card-header">
            <div className="card-icon purple">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
            </div>
            <h4 className="card-title">How It Works</h4>
          </div>
          <div className="card-body">
            <p className="flow-text">{how_it_works}</p>
          </div>
        </div>

        {/* 3. Line-by-Line Explanation */}
        <div className="structured-card line-by-line-card full-width">
          <div className="card-header">
            <div className="card-icon cyan">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="8" y1="6" x2="21" y2="6" />
                <line x1="8" y1="12" x2="21" y2="12" />
                <line x1="8" y1="18" x2="21" y2="18" />
                <line x1="3" y1="6" x2="3.01" y2="6" />
                <line x1="3" y1="12" x2="3.01" y2="12" />
                <line x1="3" y1="18" x2="3.01" y2="18" />
              </svg>
            </div>
            <h4 className="card-title">Line-by-Line Explanation</h4>
            <span className="items-count-badge">{line_by_line.length} lines</span>
          </div>
          <div className="card-body">
            <div className="line-breakdown-list">
              {line_by_line.map((item, idx) => (
                <div key={idx} className="line-breakdown-row">
                  <div className="line-number-col">
                    <span className="line-num-badge">L{item.line}</span>
                  </div>
                  <div className="line-code-col">
                    <code>{item.code}</code>
                  </div>
                  <div className="line-exp-col">
                    <span>{item.explanation}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 4. Variables & Functions */}
        <div className="structured-card variables-card">
          <div className="card-header">
            <div className="card-icon emerald">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="4" y="4" width="16" height="16" rx="2" />
                <line x1="9" y1="9" x2="15" y2="15" />
                <line x1="15" y1="9" x2="9" y2="15" />
              </svg>
            </div>
            <h4 className="card-title">Variables</h4>
            <span className="items-count-badge">{variables.length}</span>
          </div>
          <div className="card-body">
            {variables.length > 0 ? (
              <div className="identifier-list">
                {variables.map((v, idx) => (
                  <div key={idx} className="identifier-item">
                    <span className="identifier-name variable">{v.name}</span>
                    <span className="identifier-purpose">{v.purpose}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-subtext">No variables were detected in this snippet.</p>
            )}
          </div>
        </div>

        <div className="structured-card functions-card">
          <div className="card-header">
            <div className="card-icon indigo">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                <polyline points="14 2 14 8 20 8" />
              </svg>
            </div>
            <h4 className="card-title">Functions</h4>
            <span className="items-count-badge">{functions.length}</span>
          </div>
          <div className="card-body">
            {functions.length > 0 ? (
              <div className="identifier-list">
                {functions.map((fn, idx) => (
                  <div key={idx} className="function-item">
                    <div className="func-signature">
                      <span className="identifier-name function">{fn.name}</span>
                      <span className="func-params">
                        ({fn.parameters && fn.parameters.length > 0 ? fn.parameters.join(', ') : 'no parameters'})
                      </span>
                      {fn.return_value && (
                        <span className="func-return">→ {fn.return_value}</span>
                      )}
                    </div>
                    <span className="identifier-purpose">{fn.purpose}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="empty-subtext">No functions were found in this snippet.</p>
            )}
          </div>
        </div>

        {/* 5. Algorithm / Logic */}
        <div className="structured-card logic-card full-width">
          <div className="card-header">
            <div className="card-icon violet">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
            </div>
            <h4 className="card-title">Algorithm / Logic</h4>
          </div>
          <div className="card-body">
            <p className="logic-text">{algorithm_logic}</p>
          </div>
        </div>

        {/* 6. Complexity (Time & Space) */}
        <div className="structured-card complexity-card">
          <div className="card-header">
            <div className="card-icon amber">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
            </div>
            <h4 className="card-title">Time Complexity</h4>
          </div>
          <div className="card-body">
            <div className="complexity-badge-wrapper">
              <span className="complexity-value">{time_complexity}</span>
            </div>
          </div>
        </div>

        <div className="structured-card complexity-card">
          <div className="card-header">
            <div className="card-icon orange">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
              </svg>
            </div>
            <h4 className="card-title">Space Complexity</h4>
          </div>
          <div className="card-body">
            <div className="complexity-badge-wrapper">
              <span className="complexity-value">{space_complexity}</span>
            </div>
          </div>
        </div>

        {/* 7. Potential Bugs or Issues */}
        <div className="structured-card issues-card full-width">
          <div className="card-header">
            <div className="card-icon rose">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </div>
            <h4 className="card-title">Potential Bugs & Issues</h4>
            <span className="items-count-badge">{potential_issues.length}</span>
          </div>
          <div className="card-body">
            {potential_issues.length > 0 ? (
              <div className="issues-list">
                {potential_issues.map((issue, idx) => {
                  const sev = (issue.severity || 'possible').toLowerCase();
                  const isDefinite = sev === 'definite' || sev === 'high';
                  return (
                    <div key={idx} className={`issue-row ${isDefinite ? 'definite-issue' : 'possible-issue'}`}>
                      <span className={`issue-severity-pill ${sev}`}>
                        {sev.toUpperCase()}
                      </span>
                      <span className="issue-desc">{issue.description}</span>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="empty-subtext positive">No syntax bugs, runtime errors, or suspicious issues detected in this snippet.</p>
            )}
          </div>
        </div>

        {/* 8. Key Learning Points */}
        <div className="structured-card learning-card full-width">
          <div className="card-header">
            <div className="card-icon teal">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                <polyline points="22 4 12 14.01 9 11.01" />
              </svg>
            </div>
            <h4 className="card-title">Key Learning Points</h4>
          </div>
          <div className="card-body">
            {key_learning_points.length > 0 ? (
              <ul className="learning-points-list">
                {key_learning_points.map((pt, idx) => (
                  <li key={idx} className="learning-point-item">
                    <span className="point-bullet">{idx + 1}</span>
                    <span className="point-text">{pt}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="empty-subtext">No additional learning points.</p>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
