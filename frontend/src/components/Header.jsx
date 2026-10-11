import React from 'react';

export default function Header({ historyCount = 0, onToggleHistory }) {
  return (
    <header className="app-header">
      <div className="header-container">
        <div className="logo-group">
          <div className="logo-icon">
            <svg
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="16 18 22 12 16 6" />
              <polyline points="8 6 2 12 8 18" />
            </svg>
          </div>
          <div className="brand-text">
            <span className="brand-title">AI CodeMentor</span>
            <span className="brand-badge">Step 9 — Progress</span>
          </div>
        </div>

        <nav className="header-nav">
          <button
            id="nav-history-btn"
            type="button"
            className="nav-history-btn"
            onClick={onToggleHistory}
            aria-label={`View Learning History (${historyCount} sessions)`}
            title="View Learning Progress & Session History"
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            <span>History</span>
            {historyCount > 0 && (
              <span className="nav-history-badge">{historyCount}</span>
            )}
          </button>
          <span className="nav-tag">FastAPI + React</span>
        </nav>
      </div>
    </header>
  );
}
