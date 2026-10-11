import React from 'react';

export default function FeedbackBanner({ feedback, onClose }) {
  if (!feedback || !feedback.message) return null;

  const iconMap = {
    error: '⚠️',
    info: 'ℹ️',
    success: '✅',
  };

  return (
    <div
      id="feedback-banner"
      className={`feedback-banner banner-${feedback.type || 'info'}`}
      role={feedback.type === 'error' ? 'alert' : 'status'}
    >
      <div className="banner-content">
        <span className="banner-icon" aria-hidden="true">
          {iconMap[feedback.type] || 'ℹ️'}
        </span>
        <span className="banner-text">{feedback.message}</span>
      </div>
      {onClose && (
        <button
          className="banner-close-btn"
          onClick={onClose}
          aria-label="Dismiss message"
        >
          ×
        </button>
      )}
    </div>
  );
}
