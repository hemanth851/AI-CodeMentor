import React, { useState, useRef, useEffect } from 'react';
import { askTutor } from '../services/api';

const SUGGESTED_QUESTIONS = [
  'Why is this loop necessary?',
  'Explain this function in simple terms.',
  'What is the time complexity and why?',
  'What happens if I remove this condition?',
  'Which variable stores the result?',
  'Can this algorithm be made faster?',
];

export default function AiTutor({
  analyzedCode,
  detectedLanguage,
  learningLevel,
  staticAnalysis,
  analysisData,
  hasAnalyzed,
  messages,
  setMessages,
  isCodeModified = false,
}) {
  const [question, setQuestion] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [tutorError, setTutorError] = useState(null);
  const [copiedCodeIdx, setCopiedCodeIdx] = useState(null);
  const chatBottomRef = useRef(null);
  const textareaRef = useRef(null);

  // Auto-scroll to bottom of chat when new message is added
  useEffect(() => {
    if (chatBottomRef.current && messages.length > 0) {
      chatBottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isThinking]);

  const levelStr = typeof learningLevel === 'string' ? learningLevel : (learningLevel?.label || 'Beginner');

  const handleAsk = async (questionText) => {
    if (isThinking) return;

    const query = (questionText || question).trim();

    if (!hasAnalyzed || !analyzedCode) {
      setTutorError('Analyze some code first to start asking the AI Tutor questions.');
      return;
    }

    if (!query) {
      setTutorError('Please enter a question.');
      return;
    }

    setTutorError(null);
    setIsThinking(true);

    const userMessage = {
      id: Date.now(),
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    };

    // Append user message immediately
    const updatedHistory = [...messages, userMessage];
    setMessages(updatedHistory);
    setQuestion('');

    try {
      const response = await askTutor({
        code: analyzedCode,
        language: detectedLanguage || 'Python',
        learningLevel: levelStr,
        question: query,
        staticAnalysis: staticAnalysis || null,
        analysis: analysisData || null,
        // Send previous conversation context (bounded)
        history: updatedHistory.slice(0, -1),
      });

      if (response.success && response.data) {
        const tutorReply = {
          id: Date.now() + 1,
          role: 'tutor',
          content: response.data.answer,
          key_points: response.data.key_points || [],
          related_code: response.data.related_code || null,
          grounded: response.data.grounded !== false,
          timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        };
        setMessages([...updatedHistory, tutorReply]);
      } else {
        const errMsg = response.error || 'The AI Tutor could not answer right now. Please try again.';
        setTutorError(errMsg);
      }
    } catch (err) {
      setTutorError('The AI Tutor could not answer right now. Please try again.');
    } finally {
      setIsThinking(false);
      if (textareaRef.current) {
        textareaRef.current.focus();
      }
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!isThinking) {
        handleAsk();
      }
    }
  };

  const handleChipClick = (suggestion) => {
    setQuestion(suggestion);
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  };

  const handleCopyCode = (codeStr, idx) => {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(codeStr);
    setCopiedCodeIdx(idx);
    setTimeout(() => setCopiedCodeIdx(null), 2000);
  };

  const handleClearHistory = () => {
    setMessages([]);
    setTutorError(null);
  };

  return (
    <section
      id="ai-tutor-section"
      className="workspace-card ai-tutor-section"
      aria-label="Ask AI Tutor"
    >
      {/* Header */}
      <div className="tutor-header">
        <div className="tutor-header-title-group">
          <div className="tutor-avatar-icon">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a3 3 0 0 0-3 3v1a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
              <path d="M19 11v-1a7 7 0 0 0-14 0v1" />
              <rect x="5" y="11" width="14" height="10" rx="2" />
              <circle cx="9" cy="16" r="1" />
              <circle cx="15" cy="16" r="1" />
            </svg>
          </div>
          <div>
            <div className="tutor-badge-row">
              <h3 className="tutor-title">Ask AI Tutor</h3>
              <span className="tutor-mode-badge">Interactive Q&A</span>
              {hasAnalyzed && (
                <span className="tutor-grounded-pill">
                  <span className="grounded-dot" />
                  Grounded in Code
                </span>
              )}
              {isCodeModified && (
                <span className="tutor-stale-pill" title="Editor code has changed. The tutor answers are grounded in the last analyzed code.">
                  ⚠️ Reflects Previous Code
                </span>
              )}
            </div>
            <p className="tutor-subtitle">
              Ask questions about the analyzed code. Grounded in your code structure, static facts, and explanation.
            </p>
          </div>
        </div>

        {messages.length > 0 && (
          <button
            type="button"
            className="tutor-clear-btn"
            onClick={handleClearHistory}
            title="Clear tutor conversation"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
            Clear Chat
          </button>
        )}
      </div>

      {/* Suggested Quick Question Chips */}
      {hasAnalyzed && (
        <div className="tutor-suggestions-container">
          <span className="suggestions-label">Suggested:</span>
          <div className="suggestions-chips-scroll">
            {SUGGESTED_QUESTIONS.map((suggestion, idx) => (
              <button
                key={idx}
                type="button"
                className="suggestion-chip"
                onClick={() => handleChipClick(suggestion)}
                disabled={isThinking}
              >
                {suggestion}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Tutor Error Notification */}
      {tutorError && (
        <div className="tutor-error-banner" role="alert">
          <div className="tutor-error-content">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            <span>{tutorError}</span>
          </div>
          <button
            type="button"
            className="tutor-error-dismiss"
            onClick={() => setTutorError(null)}
            aria-label="Dismiss error"
          >
            &times;
          </button>
        </div>
      )}

      {/* Conversation Thread */}
      <div className="tutor-conversation-container">
        {messages.length === 0 ? (
          <div className="tutor-empty-state">
            <div className="tutor-empty-icon">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                <path d="M8 9h8" />
                <path d="M8 13h5" />
              </svg>
            </div>
            {hasAnalyzed ? (
              <>
                <h4 className="tutor-empty-title">Ready for your questions</h4>
                <p className="tutor-empty-sub">
                  Ask about loops, variables, functions, time complexity, or edge cases. Click a suggestion above or type below.
                </p>
              </>
            ) : (
              <>
                <h4 className="tutor-empty-title">No code analyzed yet</h4>
                <p className="tutor-empty-sub">
                  Analyze some code first to start asking the AI Tutor questions.
                </p>
              </>
            )}
          </div>
        ) : (
          <div className="tutor-messages-list">
            {messages.map((msg, idx) => (
              <div
                key={msg.id || idx}
                className={`tutor-message-row ${msg.role === 'user' ? 'user-row' : 'tutor-row'}`}
              >
                {/* User Message */}
                {msg.role === 'user' ? (
                  <div className="user-message-card">
                    <div className="user-meta">
                      <span className="user-author">You</span>
                      <span className="message-time">{msg.timestamp}</span>
                    </div>
                    <div className="message-content user-text">{msg.content}</div>
                  </div>
                ) : (
                  /* Tutor Message */
                  <div className="tutor-message-card">
                    <div className="tutor-meta">
                      <div className="tutor-meta-left">
                        <span className="tutor-author">AI Tutor</span>
                        <span className="tutor-level-pill">{levelStr}</span>
                        {!msg.grounded && (
                          <span className="ungrounded-warning-pill" title="This question assumes elements not found in the code">
                            Ungrounded Premise
                          </span>
                        )}
                      </div>
                      <span className="message-time">{msg.timestamp}</span>
                    </div>

                    {/* Answer text */}
                    <div className="tutor-answer-body">
                      {msg.content.split('\n\n').map((paragraph, pIdx) => (
                        <p key={pIdx} className="tutor-paragraph">
                          {paragraph}
                        </p>
                      ))}
                    </div>

                    {/* Relevant Code Reference */}
                    {msg.related_code && (
                      <div className="tutor-related-code-card">
                        <div className="related-code-header">
                          <span className="related-code-label">Relevant Code</span>
                          <button
                            type="button"
                            className="related-code-copy-btn"
                            onClick={() => handleCopyCode(msg.related_code, idx)}
                          >
                            {copiedCodeIdx === idx ? 'Copied!' : 'Copy'}
                          </button>
                        </div>
                        <pre className="related-code-block">
                          <code>{msg.related_code}</code>
                        </pre>
                      </div>
                    )}

                    {/* Key Points */}
                    {msg.key_points && msg.key_points.length > 0 && (
                      <div className="tutor-key-points">
                        <span className="key-points-title">Key Takeaways:</span>
                        <ul className="key-points-list">
                          {msg.key_points.map((point, kIdx) => (
                            <li key={kIdx} className="key-point-item">
                              <span className="key-point-bullet">•</span>
                              <span>{point}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* Thinking / Loading indicator */}
            {isThinking && (
              <div className="tutor-message-row tutor-row thinking-row">
                <div className="tutor-message-card thinking-card">
                  <div className="tutor-meta">
                    <span className="tutor-author">AI Tutor</span>
                    <span className="thinking-text">Thinking...</span>
                  </div>
                  <div className="tutor-thinking-animation">
                    <span className="pulse-dot dot-1" />
                    <span className="pulse-dot dot-2" />
                    <span className="pulse-dot dot-3" />
                  </div>
                </div>
              </div>
            )}

            <div ref={chatBottomRef} />
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="tutor-input-container">
        <div className="tutor-input-wrapper">
          <textarea
            ref={textareaRef}
            id="tutor-question-input"
            name="tutor_question"
            aria-label="Ask a question about this code"
            className="tutor-textarea"
            rows="2"
            placeholder={
              hasAnalyzed
                ? 'Ask a question about this code... (e.g., Why is this loop used?)'
                : 'Analyze some code first to ask the AI Tutor questions'
            }
            value={question}
            onChange={(e) => {
              setQuestion(e.target.value);
              if (tutorError) setTutorError(null);
            }}
            onKeyDown={handleKeyDown}
            disabled={isThinking || !hasAnalyzed}
          />
          <button
            type="button"
            className="tutor-submit-btn"
            onClick={() => handleAsk()}
            disabled={isThinking || !question.trim() || !hasAnalyzed}
            title="Ask Tutor (Enter)"
          >
            {isThinking ? (
              <>
                <span className="tutor-btn-spinner" />
                <span>Thinking...</span>
              </>
            ) : (
              <>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
                <span>Ask Tutor</span>
              </>
            )}
          </button>
        </div>
        <div className="tutor-input-hints">
          <span className="hint-item">Press <kbd>Enter</kbd> to ask, <kbd>Shift + Enter</kbd> for new line</span>
          <span className="hint-item">Grounded in: <strong>{detectedLanguage || 'current code'}</strong> ({levelStr})</span>
        </div>
      </div>
    </section>
  );
}
