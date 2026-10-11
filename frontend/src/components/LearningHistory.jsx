import React, { useState } from 'react';

/**
 * Format ISO date string into readable local format.
 */
function formatSessionDate(isoString) {
  if (!isoString) return 'Recent';
  try {
    const date = new Date(isoString);
    if (isNaN(date.getTime())) return 'Recent';
    return date.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch (e) {
    return 'Recent';
  }
}

/**
 * Learning History & Progress Dashboard Component (Step 9)
 */
export default function LearningHistory({
  sessions = [],
  activeSessionId = null,
  onReopenSession,
  onDeleteSession,
  onClearHistory,
  isStorageOk = true,
  onNewSession,
}) {
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [sessionToDelete, setSessionToDelete] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterLang, setFilterLang] = useState('ALL');

  // Filtered session list
  const filteredSessions = sessions.filter((session) => {
    const matchesSearch =
      !searchTerm ||
      (session.title && session.title.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (session.language && session.language.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (session.sourceCode && session.sourceCode.toLowerCase().includes(searchTerm.toLowerCase()));

    const matchesLang =
      filterLang === 'ALL' || (session.language && session.language.toLowerCase() === filterLang.toLowerCase());

    return matchesSearch && matchesLang;
  });

  // Extract unique languages for filter dropdown
  const uniqueLanguages = Array.from(
    new Set(sessions.map((s) => s.language).filter(Boolean))
  );

  const handleConfirmClear = () => {
    onClearHistory();
    setShowClearConfirm(false);
  };

  const handleConfirmDelete = () => {
    if (sessionToDelete) {
      onDeleteSession(sessionToDelete.id);
      setSessionToDelete(null);
    }
  };

  return (
    <section
      id="learning-history-section"
      className="learning-history-section"
      aria-label="Learning Progress and Session History"
    >
      {/* Section Header */}
      <div className="history-header">
        <div className="history-title-group">
          <div className="history-badge">Step 9 Progress</div>
          <h2 className="history-title">Learning History & Sessions</h2>
          <span className="history-count-pill" aria-label={`${sessions.length} saved sessions`}>
            {sessions.length} {sessions.length === 1 ? 'Session' : 'Sessions'} Saved
          </span>
        </div>

        <div className="history-header-actions">
          {sessions.length > 0 && (
            <button
              id="clear-all-history-btn"
              type="button"
              className="btn btn-danger-outline"
              onClick={() => setShowClearConfirm(true)}
              aria-label="Clear all session history"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
              Clear All History
            </button>
          )}

          {activeSessionId && (
            <button
              type="button"
              className="btn btn-secondary-sm"
              onClick={onNewSession}
              title="Start a new blank session"
            >
              + New Session
            </button>
          )}
        </div>
      </div>

      {/* Storage Alert if local storage is restricted/in-memory */}
      {!isStorageOk && (
        <div className="history-storage-warning" role="alert">
          <span className="warning-icon">ℹ️</span>
          <span>
            Browser storage is restricted in this environment. Sessions will be preserved in memory for this session only.
          </span>
        </div>
      )}

      {/* Filter and Search Bar (shown when 2+ sessions exist) */}
      {sessions.length >= 2 && (
        <div className="history-filter-bar">
          <div className="history-search-input-wrapper">
            <svg className="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              id="history-search-input"
              type="text"
              className="history-search-input"
              placeholder="Search sessions by title, language, or code..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              aria-label="Search learning history"
            />
            {searchTerm && (
              <button
                type="button"
                className="clear-search-btn"
                onClick={() => setSearchTerm('')}
                aria-label="Clear search"
              >
                ✕
              </button>
            )}
          </div>

          {uniqueLanguages.length > 1 && (
            <div className="history-lang-filter">
              <label htmlFor="history-lang-select" className="sr-only">Filter by language</label>
              <select
                id="history-lang-select"
                className="history-select"
                value={filterLang}
                onChange={(e) => setFilterLang(e.target.value)}
              >
                <option value="ALL">All Languages ({sessions.length})</option>
                {uniqueLanguages.map((lang) => (
                  <option key={lang} value={lang}>{lang}</option>
                ))}
              </select>
            </div>
          )}
        </div>
      )}

      {/* Empty State */}
      {sessions.length === 0 ? (
        <div className="history-empty-state" role="status">
          <div className="empty-icon-circle">📜</div>
          <h3 className="empty-state-title">No Learning Sessions Saved Yet</h3>
          <p className="empty-state-desc">
            Your learning progress is saved locally when you analyze code, complete dynamic quizzes, or run algorithm visualizations.
            Sessions allow you to revisit explanations and test scores anytime.
          </p>
        </div>
      ) : filteredSessions.length === 0 ? (
        <div className="history-empty-state" role="status">
          <div className="empty-icon-circle">🔍</div>
          <h3 className="empty-state-title">No Matching Sessions Found</h3>
          <p className="empty-state-desc">
            No saved sessions match &quot;{searchTerm}&quot;. Try adjusting your search query or language filter.
          </p>
          <button
            type="button"
            className="btn btn-secondary-sm"
            onClick={() => { setSearchTerm(''); setFilterLang('ALL'); }}
          >
            Reset Filters
          </button>
        </div>
      ) : (
        /* Sessions List Grid */
        <div className="history-grid" role="feed" aria-label="Saved learning sessions">
          {filteredSessions.map((session) => {
            const isActive = activeSessionId === session.id;
            const hasAnalysis = Boolean(session.analysisResult && session.analysisResult.status === 'success');
            const hasQuiz = session.quizStatus === 'completed' && session.quizScore !== null;
            const hasVisualization = session.visualizationStatus === 'completed';

            // Extract a clean 2-line snippet preview
            const snippetLines = (session.sourceCode || '')
              .split('\n')
              .map((l) => l.trim())
              .filter(Boolean)
              .slice(0, 2)
              .join(' ');

            return (
              <article
                key={session.id}
                className={`history-card ${isActive ? 'history-card-active' : ''}`}
                aria-label={`Session: ${session.title}`}
              >
                {/* Card Header */}
                <div className="history-card-header">
                  <div className="history-card-meta">
                    <span className="history-lang-badge">{session.language || 'Code'}</span>
                    <span className="history-level-badge">{session.learningLevel || 'Beginner'}</span>
                    {isActive && <span className="history-active-pill">● Active</span>}
                  </div>
                  <time className="history-time-stamp" dateTime={session.updatedAt || session.createdAt}>
                    {formatSessionDate(session.updatedAt || session.createdAt)}
                  </time>
                </div>

                {/* Card Body */}
                <div className="history-card-body">
                  <h3 className="history-session-title" title={session.title}>
                    {session.title || 'Untitled Session'}
                  </h3>

                  {snippetLines && (
                    <code className="history-snippet-preview">
                      {snippetLines.length > 120 ? `${snippetLines.slice(0, 120)}...` : snippetLines}
                    </code>
                  )}

                  {/* Progress Indicators */}
                  <div className="history-indicators-group">
                    <span
                      className={`indicator-pill ${hasAnalysis ? 'indicator-success' : 'indicator-muted'}`}
                      title={hasAnalysis ? 'Structured code analysis completed' : 'No analysis saved'}
                    >
                      {hasAnalysis ? '✓ Analyzed' : '○ Pending'}
                    </span>

                    {hasQuiz ? (
                      <span
                        className="indicator-pill indicator-quiz"
                        title={`Quiz Assessment: ${session.quizScore} of ${session.quizTotalQuestions} correct (${session.quizPercentage}%)`}
                      >
                        🎯 Quiz: {session.quizScore}/{session.quizTotalQuestions} ({session.quizPercentage}%)
                      </span>
                    ) : (
                      <span className="indicator-pill indicator-muted" title="Quiz assessment not completed">
                        ○ Quiz: Not Taken
                      </span>
                    )}

                    <span
                      className={`indicator-pill ${hasVisualization ? 'indicator-vis' : 'indicator-muted'}`}
                      title={hasVisualization ? 'Algorithm visualization completed' : 'Visualizer not run'}
                    >
                      {hasVisualization ? '⚡ Visualized' : '○ Visualizer: Ready'}
                    </span>
                  </div>
                </div>

                {/* Card Actions */}
                <div className="history-card-actions">
                  <button
                    type="button"
                    className="btn btn-reopen"
                    onClick={() => onReopenSession(session)}
                    aria-label={`Reopen session ${session.title}`}
                  >
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                    {isActive ? 'Current Session' : 'Reopen Session'}
                  </button>

                  <button
                    type="button"
                    className="btn btn-icon-delete"
                    onClick={() => setSessionToDelete(session)}
                    aria-label={`Delete session ${session.title}`}
                    title="Delete session"
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {/* Confirmation Modal for Clearing All History */}
      {showClearConfirm && (
        <div className="history-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="clear-modal-title">
          <div className="history-modal-card">
            <div className="modal-icon-danger">⚠️</div>
            <h3 id="clear-modal-title" className="modal-title">Clear All Learning History?</h3>
            <p className="modal-desc">
              This will permanently delete all {sessions.length} saved learning sessions and quiz scores from your browser. This action cannot be undone.
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => setShowClearConfirm(false)}
              >
                Cancel
              </button>
              <button
                id="confirm-clear-all-btn"
                type="button"
                className="btn btn-danger-solid"
                onClick={handleConfirmClear}
              >
                Yes, Clear All History
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Confirmation Modal for Deleting Single Session */}
      {sessionToDelete && (
        <div className="history-modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="delete-modal-title">
          <div className="history-modal-card">
            <div className="modal-icon-danger">🗑️</div>
            <h3 id="delete-modal-title" className="modal-title">Delete Learning Session?</h3>
            <p className="modal-desc">
              Are you sure you want to delete &quot;{sessionToDelete.title}&quot;?
            </p>
            <div className="modal-actions">
              <button
                type="button"
                className="btn btn-outline"
                onClick={() => setSessionToDelete(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger-solid"
                onClick={handleConfirmDelete}
              >
                Delete Session
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
