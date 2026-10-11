import React, { useState, useEffect, useRef } from 'react';
import Header from '../components/Header';
import HealthStatus from '../components/HealthStatus';
import LevelSelector from '../components/LevelSelector';
import CodeEditor from '../components/CodeEditor';
import ActionControls from '../components/ActionControls';
import FeedbackBanner from '../components/FeedbackBanner';
import AnalysisResult from '../components/AnalysisResult';
import AlgorithmVisualizer from '../components/AlgorithmVisualizer';
import AiTutor from '../components/AiTutor';
import QuizSection from '../components/QuizSection';
import LearningHistory from '../components/LearningHistory';
import { analyzeCode } from '../services/api';
import historyStorage, { generateSessionTitle } from '../services/historyStorage';
import {
  LEARNING_LEVELS,
  DEFAULT_SAMPLE_CODE,
  getMonacoLang,
} from '../constants/editorConfig';
import { getCodeFingerprint } from '../utils/codeUtils';

export default function LandingPage() {
  const [sourceCode, setSourceCode] = useState(DEFAULT_SAMPLE_CODE);
  const [learningLevel, setLearningLevel] = useState(LEARNING_LEVELS[0]); // Beginner
  const [uploadedFileName, setUploadedFileName] = useState(null);
  const [monacoLang, setMonacoLang] = useState('python');
  const [displayLang, setDisplayLang] = useState('Python (Sample)');
  const [feedback, setFeedback] = useState(null);

  // Analysis state
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analysisData, setAnalysisData] = useState(null);
  const [analysisError, setAnalysisError] = useState(null);
  const [lastAnalyzedCode, setLastAnalyzedCode] = useState('');

  // Interactive AI Tutor state
  const [tutorMessages, setTutorMessages] = useState([]);

  // Step 9: History and Session Tracking State
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [historySessions, setHistorySessions] = useState(() => historyStorage.getHistory());
  const [restoredQuizProgress, setRestoredQuizProgress] = useState(null);
  const [visualizationStatus, setVisualizationStatus] = useState('not_started');
  const isStorageOk = historyStorage.isStorageAvailable();

  // Step 10: Request cancellation / identity ref to prevent stale async responses
  const analysisReqIdRef = useRef(0);

  // Determine if code in editor was modified since last analysis
  const isCodeModified = Boolean(lastAnalyzedCode && sourceCode.trim() !== lastAnalyzedCode.trim());

  // Keep history list refreshed on initial mount
  useEffect(() => {
    setHistorySessions(historyStorage.getHistory());
  }, []);

  const refreshHistory = () => {
    setHistorySessions(historyStorage.getHistory());
  };

  // Invalidate in-flight requests and update code state
  const handleCodeChange = (newCode) => {
    analysisReqIdRef.current++;
    setSourceCode(newCode);
  };

  const handleClear = () => {
    analysisReqIdRef.current++;
    setSourceCode('');
    setUploadedFileName(null);
    setMonacoLang('plaintext');
    setDisplayLang('Auto Detect');
    setAnalysisData(null);
    setAnalysisError(null);
    setLastAnalyzedCode('');
    setTutorMessages([]);
    setActiveSessionId(null);
    setRestoredQuizProgress(null);
    setVisualizationStatus('not_started');
    setFeedback({
      type: 'info',
      message: 'Editor cleared. Ready for new code or new session.',
    });
  };

  const handleNewSession = () => {
    handleClear();
  };

  const handleFileUploaded = (fileName, detectedLang) => {
    analysisReqIdRef.current++;
    setUploadedFileName(fileName);
    // When a new file is uploaded, reset active session ID to avoid mutating previous session
    setActiveSessionId(null);
    setRestoredQuizProgress(null);
    setVisualizationStatus('not_started');
    setAnalysisData(null);
    setLastAnalyzedCode('');
    setTutorMessages([]);

    if (detectedLang) {
      setMonacoLang(detectedLang.monacoLang);
      setDisplayLang(detectedLang.label);
    } else {
      setMonacoLang('plaintext');
      setDisplayLang('Auto Detect');
    }
  };

  const handleAnalyze = async () => {
    if (isAnalyzing) return;

    if (!sourceCode || sourceCode.trim() === '') {
      setFeedback({
        type: 'error',
        message: 'Please enter or upload some code before analyzing.',
      });
      return;
    }

    const reqId = ++analysisReqIdRef.current;
    const reqFingerprint = getCodeFingerprint(sourceCode);
    setIsAnalyzing(true);
    setAnalysisError(null);
    setFeedback(null);
    // Clear old tutor conversation and restored progress when new analysis begins
    setTutorMessages([]);
    setRestoredQuizProgress(null);
    setVisualizationStatus('not_started');

    try {
      const response = await analyzeCode(
        sourceCode,
        learningLevel.label,
        uploadedFileName
      );

      // Check if this request is still the active one and code hasn't changed
      if (reqId !== analysisReqIdRef.current || getCodeFingerprint(sourceCode) !== reqFingerprint) {
        return;
      }

      if (response.success && response.data) {
        setAnalysisData(response.data);
        setAnalysisError(null);

        const status = response.data.status;
        if (status === 'success') {
          setLastAnalyzedCode(sourceCode);
          const detected = response.data.detected_language;
          if (detected) {
            setMonacoLang(getMonacoLang(detected));
            setDisplayLang(detected);
          }

          // Step 9: Persist or update session in history upon meaningful analysis
          const title = generateSessionTitle({
            code: sourceCode,
            fileName: uploadedFileName,
            language: detected,
          });

          const saveResult = historyStorage.saveSession({
            id: activeSessionId || undefined,
            title,
            language: detected || displayLang,
            learningLevel: learningLevel.label,
            sourceCode,
            analysisResult: response.data,
            quizStatus: restoredQuizProgress ? 'completed' : 'not_started',
            quizScore: restoredQuizProgress?.score ?? null,
            quizTotalQuestions: restoredQuizProgress?.total ?? null,
            quizPercentage: restoredQuizProgress?.percentage ?? null,
            quizCompletedAt: restoredQuizProgress?.completedAt ?? null,
            visualizationStatus: visualizationStatus || 'not_started',
          });

          if (saveResult.success && saveResult.session) {
            setActiveSessionId(saveResult.session.id);
            refreshHistory();
          }

          setFeedback({
            type: 'success',
            message: `Code analyzed successfully! Language detected: ${detected} (${response.data.confidence} confidence). Session saved.`,
          });
        } else if (status === 'ambiguous') {
          setFeedback({
            type: 'info',
            message: 'Snippet is too short or ambiguous to identify the language.',
          });
        } else if (status === 'unsupported') {
          setFeedback({
            type: 'error',
            message: 'This programming language is not currently supported.',
          });
        }
      } else {
        const errorMsg = response.error || 'Unable to analyze the code right now. Please try again.';
        setAnalysisError(errorMsg);
        setAnalysisData(null);
        setFeedback({
          type: 'error',
          message: errorMsg,
        });
      }
    } catch (err) {
      if (reqId !== analysisReqIdRef.current) return;
      const fallbackMsg = 'Unable to analyze the code right now. Please try again.';
      setAnalysisError(fallbackMsg);
      setAnalysisData(null);
      setFeedback({
        type: 'error',
        message: fallbackMsg,
      });
    } finally {
      if (reqId === analysisReqIdRef.current) {
        setIsAnalyzing(false);
      }
    }
  };

  // Step 9: Reopen a saved session
  const handleReopenSession = (session) => {
    if (!session) return;

    analysisReqIdRef.current++;
    setActiveSessionId(session.id);
    setSourceCode(session.sourceCode || '');
    setUploadedFileName(session.title && session.title.includes('.') ? session.title : null);

    const lang = session.language || 'Python';
    setDisplayLang(lang);
    setMonacoLang(getMonacoLang(lang));

    const matchedLevel =
      LEARNING_LEVELS.find((l) => l.label.toLowerCase() === (session.learningLevel || '').toLowerCase()) ||
      LEARNING_LEVELS[0];
    setLearningLevel(matchedLevel);

    setAnalysisData(session.analysisResult || null);
    setLastAnalyzedCode(session.sourceCode || '');
    setAnalysisError(null);
    setTutorMessages([]);

    // Restore quiz score and completion status
    if (session.quizStatus === 'completed' && session.quizScore !== null) {
      setRestoredQuizProgress({
        score: session.quizScore,
        total: session.quizTotalQuestions || 5,
        percentage: session.quizPercentage ?? Math.round((session.quizScore / (session.quizTotalQuestions || 5)) * 100),
        completedAt: session.quizCompletedAt,
      });
    } else {
      setRestoredQuizProgress(null);
    }

    setVisualizationStatus(session.visualizationStatus || 'not_started');

    setFeedback({
      type: 'success',
      message: `Restored session "${session.title || 'Untitled Session'}". Code and saved explanations loaded.`,
    });

    // Scroll smoothly to the workspace card
    const workspaceEl = document.querySelector('.workspace-card');
    if (workspaceEl) {
      workspaceEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  // Step 9: Delete individual session
  const handleDeleteSession = (sessionId) => {
    historyStorage.deleteSession(sessionId);
    if (activeSessionId === sessionId) {
      setActiveSessionId(null);
    }
    refreshHistory();
    setFeedback({
      type: 'info',
      message: 'Session removed from learning history.',
    });
  };

  // Step 9: Clear all history
  const handleClearHistory = () => {
    historyStorage.clearAllHistory();
    setActiveSessionId(null);
    refreshHistory();
    setFeedback({
      type: 'info',
      message: 'All learning history and saved sessions have been cleared.',
    });
  };

  // Step 9: Quiz completion integration
  const handleQuizCompleted = (quizData) => {
    setRestoredQuizProgress(quizData);

    if (activeSessionId) {
      historyStorage.updateSessionProgress(activeSessionId, {
        quizStatus: 'completed',
        quizScore: quizData.score,
        quizTotalQuestions: quizData.totalQuestions,
        quizPercentage: quizData.percentage,
        quizCompletedAt: quizData.completedAt,
      });
      refreshHistory();
    } else {
      // Create session for standalone quiz completion
      const title = generateSessionTitle({
        code: sourceCode,
        fileName: uploadedFileName,
        language: displayLang,
      });

      const saveRes = historyStorage.saveSession({
        title,
        language: displayLang || 'Python',
        learningLevel: learningLevel.label,
        sourceCode,
        analysisResult: analysisData,
        quizStatus: 'completed',
        quizScore: quizData.score,
        quizTotalQuestions: quizData.totalQuestions,
        quizPercentage: quizData.percentage,
        quizCompletedAt: quizData.completedAt,
        visualizationStatus: visualizationStatus || 'not_started',
      });

      if (saveRes.success && saveRes.session) {
        setActiveSessionId(saveRes.session.id);
        refreshHistory();
      }
    }

    setFeedback({
      type: 'success',
      message: `Quiz assessment completed! Score ${quizData.score}/${quizData.totalQuestions} saved to your learning history.`,
    });
  };

  // Step 9: Visualization completion integration
  const handleVisualizationCompleted = (visData) => {
    setVisualizationStatus('completed');

    if (activeSessionId) {
      historyStorage.updateSessionProgress(activeSessionId, {
        visualizationStatus: 'completed',
        visualizationCompletedAt: visData.completedAt,
      });
      refreshHistory();
    } else {
      const title = generateSessionTitle({
        code: sourceCode,
        fileName: uploadedFileName,
        language: displayLang,
      });

      const saveRes = historyStorage.saveSession({
        title,
        language: displayLang || 'Python',
        learningLevel: learningLevel.label,
        sourceCode,
        analysisResult: analysisData,
        quizStatus: restoredQuizProgress ? 'completed' : 'not_started',
        quizScore: restoredQuizProgress?.score ?? null,
        quizTotalQuestions: restoredQuizProgress?.total ?? null,
        quizPercentage: restoredQuizProgress?.percentage ?? null,
        quizCompletedAt: restoredQuizProgress?.completedAt ?? null,
        visualizationStatus: 'completed',
        visualizationCompletedAt: visData.completedAt,
      });

      if (saveRes.success && saveRes.session) {
        setActiveSessionId(saveRes.session.id);
        refreshHistory();
      }
    }
  };

  // Navigation jump to history
  const handleScrollToHistory = () => {
    const historyEl = document.getElementById('learning-history-section');
    if (historyEl) {
      historyEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="page-wrapper">
      <Header
        historyCount={historySessions.length}
        onToggleHistory={handleScrollToHistory}
      />

      <main className="main-content">
        <section className="hero-section">
          <div className="hero-badge">Interactive Code Learning</div>
          <h1 className="hero-title">AI CodeMentor</h1>
          <p className="hero-description">
            Paste or upload code in any of 13 supported languages. AI CodeMentor automatically detects the language and explains how it works.
          </p>
          <div className="hero-status-wrapper">
            <HealthStatus />
          </div>
        </section>

        <section className="workspace-card" aria-label="Code Analysis Studio">
          {/* Top Controls Bar: Learning Level Only (LanguageSelector completely removed) */}
          <div className="workspace-controls-bar single-control">
            <div className="level-control-container">
              <LevelSelector
                selectedLevel={learningLevel}
                onLevelChange={setLearningLevel}
              />
            </div>
            {activeSessionId && (
              <div className="active-session-indicator">
                <span className="active-dot">●</span>
                <span className="active-text">Session Active</span>
                <button
                  type="button"
                  className="btn-new-session-text"
                  onClick={handleNewSession}
                  title="Clear active session and start fresh"
                >
                  Start New
                </button>
              </div>
            )}
          </div>

          {/* User Feedback & Notification Banner */}
          <FeedbackBanner
            feedback={feedback}
            onClose={() => setFeedback(null)}
          />

          {/* Monaco Editor Container */}
          <div className="workspace-editor-area">
            <CodeEditor
              value={sourceCode}
              onChange={handleCodeChange}
              monacoLang={monacoLang}
              displayLang={displayLang}
              fileName={uploadedFileName || 'snippet'}
            />
          </div>

          {/* Action Bar: Upload, Clear, Analyze */}
          <ActionControls
            sourceCode={sourceCode}
            onCodeChange={handleCodeChange}
            onFileUploaded={handleFileUploaded}
            onClear={handleClear}
            onFeedback={setFeedback}
            onAnalyze={handleAnalyze}
            isAnalyzing={isAnalyzing}
          />
        </section>

        {/* Structured AI Explanation & Output */}
        <AnalysisResult
          analysisData={analysisData}
          isLoading={isAnalyzing}
          learningLevel={learningLevel}
          error={analysisError}
          isCodeModified={isCodeModified}
          onDismiss={() => {
            setAnalysisData(null);
            setAnalysisError(null);
          }}
        />

        {/* Step 7A: Deterministic Algorithm Visualizer */}
        <AlgorithmVisualizer
          sourceCode={sourceCode}
          detectedLanguage={analysisData?.detected_language || (monacoLang === 'python' ? 'Python' : null)}
          hasAnalyzed={Boolean(analysisData && analysisData.status === 'success')}
          onVisualizationCompleted={handleVisualizationCompleted}
          initialStatus={visualizationStatus}
        />

        {/* Interactive AI Tutor / Code Q&A */}
        {analysisData && analysisData.status === 'success' && (
          <AiTutor
            analyzedCode={lastAnalyzedCode || sourceCode}
            detectedLanguage={analysisData.detected_language}
            learningLevel={learningLevel}
            staticAnalysis={analysisData.static_analysis}
            analysisData={analysisData}
            hasAnalyzed={Boolean(analysisData && analysisData.status === 'success')}
            messages={tutorMessages}
            setMessages={setTutorMessages}
            isCodeModified={isCodeModified}
          />
        )}

        {/* Step 8A: Dynamic AI Quiz & Learning Assessment */}
        <QuizSection
          sourceCode={sourceCode}
          detectedLanguage={analysisData?.detected_language || (monacoLang === 'python' ? 'Python' : null)}
          learningLevel={learningLevel}
          analysisData={analysisData}
          staticAnalysis={analysisData?.static_analysis}
          onQuizCompleted={handleQuizCompleted}
          restoredQuizProgress={restoredQuizProgress}
          isCodeModified={isCodeModified}
        />

        {/* Step 9: Learning Progress & Session History Dashboard */}
        <LearningHistory
          sessions={historySessions}
          activeSessionId={activeSessionId}
          onReopenSession={handleReopenSession}
          onDeleteSession={handleDeleteSession}
          onClearHistory={handleClearHistory}
          isStorageOk={isStorageOk}
          onNewSession={handleNewSession}
        />
      </main>

      <footer className="app-footer">
        <p>© {new Date().getFullYear()} AI CodeMentor. An interactive code explanation and learning platform.</p>
      </footer>
    </div>
  );
}
