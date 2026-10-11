import React, { useState, useEffect, useRef } from 'react';
import { visualizeCode } from '../services/api';
import { getCodeFingerprint } from '../utils/codeUtils';

const EVENT_BADGE_CONFIG = {
  initialization: { label: 'INIT', className: 'badge-init', icon: '⚙️' },
  assignment: { label: 'ASSIGN', className: 'badge-assign', icon: '📝' },
  condition_true: { label: 'COND: TRUE', className: 'badge-cond-true', icon: '✅' },
  condition_false: { label: 'COND: FALSE', className: 'badge-cond-false', icon: '❌' },
  loop_start: { label: 'LOOP START', className: 'badge-loop-start', icon: '🔄' },
  loop_iteration: { label: 'ITERATION', className: 'badge-loop-iter', icon: '🔁' },
  function_call: { label: 'CALL', className: 'badge-func-call', icon: '📞' },
  return: { label: 'RETURN', className: 'badge-return', icon: '↩️' },
  output: { label: 'PRINT', className: 'badge-output', icon: '💬' },
  completed: { label: 'FINISHED', className: 'badge-completed', icon: '🏁' },
  limit_exceeded: { label: 'LIMIT EXCEEDED', className: 'badge-limit', icon: '⚠️' },
};

export default function AlgorithmVisualizer({
  sourceCode,
  detectedLanguage,
  hasAnalyzed,
  onVisualizationCompleted,
  initialStatus,
}) {
  const [isTracing, setIsTracing] = useState(false);
  const [traceData, setTraceData] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);
  const [currentStepIdx, setCurrentStepIdx] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackSpeed, setPlaybackSpeed] = useState(1); // 0.5x, 1x, 2x

  const playTimerRef = useRef(null);
  const visReqIdRef = useRef(0);
  const lastCodeFingerprintRef = useRef(getCodeFingerprint(sourceCode));
  const codeLines = (sourceCode || '').split('\n');


  // Stop playback on unmount or when reaching the end
  useEffect(() => {
    if (isPlaying) {
      const delay = Math.max(300, 1000 / playbackSpeed);
      playTimerRef.current = setInterval(() => {
        setCurrentStepIdx((prev) => {
          if (!traceData || prev >= traceData.trace.length - 1) {
            setIsPlaying(false);
            return prev;
          }
          return prev + 1;
        });
      }, delay);
    } else {
      if (playTimerRef.current) {
        clearInterval(playTimerRef.current);
      }
    }
    return () => {
      if (playTimerRef.current) {
        clearInterval(playTimerRef.current);
      }
    };
  }, [isPlaying, playbackSpeed, traceData]);

  // Invalidate stale visualizer state immediately when code or language changes
  useEffect(() => {
    const currentFp = getCodeFingerprint(sourceCode);
    if (currentFp !== lastCodeFingerprintRef.current) {
      lastCodeFingerprintRef.current = currentFp;
      visReqIdRef.current++;
      setIsTracing(false);
      setIsPlaying(false);
      setTraceData(null);
      setErrorMessage(null);
      setCurrentStepIdx(0);
    }
  }, [sourceCode, detectedLanguage]);

  const handleStartVisualization = async () => {
    if (isTracing) return;

    if (!sourceCode || sourceCode.trim() === '') {
      setErrorMessage('Please enter some code to visualize.');
      return;
    }

    const reqId = ++visReqIdRef.current;
    const reqFingerprint = getCodeFingerprint(sourceCode);

    setIsTracing(true);
    setErrorMessage(null);
    setIsPlaying(false);

    try {
      const lang = detectedLanguage || 'Python';
      const result = await visualizeCode(sourceCode, lang);

      // Asynchronous race condition guard: discard if request is stale or code changed
      if (reqId !== visReqIdRef.current || getCodeFingerprint(sourceCode) !== reqFingerprint) {
        return;
      }

      if (result.success && result.data) {
        if (!result.data.supported) {
          setErrorMessage(result.data.error || 'Unable to visualize this code snippet.');
          setTraceData(null);
        } else if (result.data.status === 'error') {
          setErrorMessage(result.data.error || 'An error occurred during execution.');
          setTraceData(null);
        } else {
          setTraceData(result.data);
          setCurrentStepIdx(0);
          setErrorMessage(null);
          if (onVisualizationCompleted) {
            onVisualizationCompleted({
              completedAt: new Date().toISOString(),
              totalSteps: result.data.trace?.length || 0,
              terminationReason: result.data.termination_reason || 'completed',
            });
          }
        }
      } else {
        setErrorMessage(result.error || 'Unable to visualize execution. Please try again.');
        setTraceData(null);
      }
    } catch (err) {
      if (reqId !== visReqIdRef.current) return;
      setErrorMessage('Unable to communicate with the visualization service.');
      setTraceData(null);
    } finally {
      if (reqId === visReqIdRef.current) {
        setIsTracing(false);
      }
    }
  };

  const totalSteps = traceData?.trace?.length || 0;
  const currentStep = traceData?.trace?.[currentStepIdx] || null;
  const prevStep = currentStepIdx > 0 ? traceData?.trace?.[currentStepIdx - 1] : null;

  // Stepper handlers
  const handleFirstStep = () => {
    setIsPlaying(false);
    setCurrentStepIdx(0);
  };

  const handlePrevStep = () => {
    setIsPlaying(false);
    setCurrentStepIdx((prev) => Math.max(0, prev - 1));
  };

  const handleTogglePlay = () => {
    if (currentStepIdx >= totalSteps - 1) {
      setCurrentStepIdx(0);
    }
    setIsPlaying((prev) => !prev);
  };

  const handleNextStep = () => {
    setIsPlaying(false);
    setCurrentStepIdx((prev) => Math.min(totalSteps - 1, prev + 1));
  };

  const handleLastStep = () => {
    setIsPlaying(false);
    setCurrentStepIdx(Math.max(0, totalSteps - 1));
  };

  const handleReset = () => {
    setIsPlaying(false);
    setCurrentStepIdx(0);
  };

  const handleSliderChange = (e) => {
    setIsPlaying(false);
    setCurrentStepIdx(Number(e.target.value));
  };

  // Find variables modified in the current step for highlight
  const getChangedVars = () => {
    if (!currentStep) return new Set();
    if (!prevStep) return new Set(Object.keys(currentStep.variable_state || {}));

    const changed = new Set();
    const currVars = currentStep.variable_state || {};
    const prevVars = prevStep.variable_state || {};

    for (const [k, v] of Object.entries(currVars)) {
      if (JSON.stringify(v) !== JSON.stringify(prevVars[k])) {
        changed.add(k);
      }
    }
    return changed;
  };

  const changedVars = getChangedVars();
  const badgeInfo = currentStep ? (EVENT_BADGE_CONFIG[currentStep.event_type] || {
    label: currentStep.event_type.toUpperCase(),
    className: 'badge-default',
    icon: '⚡',
  }) : null;

  const currentLineCode = currentStep?.line_number && codeLines[currentStep.line_number - 1] !== undefined
    ? codeLines[currentStep.line_number - 1].trim()
    : null;

  return (
    <section className="algorithm-visualizer-section" aria-label="Algorithm Visualizer">
      {/* Visualizer Header */}
      <div className="visualizer-header">
        <div className="visualizer-title-group">
          <div className="visualizer-badge">Multi-Language Module</div>
          <h2 className="visualizer-title">Algorithm Visualizer</h2>
          <span className="visualizer-subtext">Interactive Execution Tracing</span>
        </div>

        <div className="visualizer-actions">
          {initialStatus === 'completed' && !traceData && (
            <span className="visualizer-restored-pill" title="Visualization was previously run for this session">
              ✓ Visualized
            </span>
          )}
          <button
            type="button"
            className="btn btn-visualize-trigger"
            onClick={handleStartVisualization}
            disabled={isTracing || !sourceCode}
          >
            {isTracing ? (
              <>
                <span className="visualizer-spinner" aria-hidden="true" />
                Tracing Execution...
              </>
            ) : (
              <>
                <span className="btn-icon">⚡</span>
                {traceData ? 'Retrace Execution' : 'Visualize Algorithm'}
              </>
            )}
          </button>
          {detectedLanguage && (
            <span className="visualizer-lang-pill">
              {detectedLanguage}
            </span>
          )}
        </div>
      </div>

      {/* Error / Unsupported Message */}
      {errorMessage && (
        <div className="visualizer-error-banner" role="alert">
          <span className="error-icon">⚠️</span>
          <div className="error-content">
            <strong>Visualization Notice:</strong>
            <p>{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Limit Exceeded or Special Termination Banner */}
      {traceData && traceData.termination_reason !== 'completed' && (
        <div className="visualizer-limit-banner">
          <span className="limit-icon">⏱️</span>
          <div>
            <strong>Execution Truncated:</strong> {traceData.error || `Stopped due to ${traceData.termination_reason}.`}
          </div>
        </div>
      )}

      {/* Active Visualization Studio */}
      {traceData && currentStep && (
        <div className="visualizer-studio">
          {/* Controls Bar */}
          <div className="visualizer-controls-bar">
            {/* Step navigation buttons */}
            <div className="stepper-buttons-group">
              <button
                type="button"
                className="step-ctrl-btn"
                onClick={handleFirstStep}
                disabled={currentStepIdx === 0}
                title="First Step (|<<)"
              >
                ⏮
              </button>
              <button
                type="button"
                className="step-ctrl-btn"
                onClick={handlePrevStep}
                disabled={currentStepIdx === 0}
                title="Previous Step (<)"
              >
                ◀
              </button>
              <button
                type="button"
                className={`step-ctrl-btn play-btn ${isPlaying ? 'playing' : ''}`}
                onClick={handleTogglePlay}
                title={isPlaying ? 'Pause' : 'Play'}
              >
                {isPlaying ? '⏸' : '▶'}
              </button>
              <button
                type="button"
                className="step-ctrl-btn"
                onClick={handleNextStep}
                disabled={currentStepIdx >= totalSteps - 1}
                title="Next Step (>)"
              >
                ▶
              </button>
              <button
                type="button"
                className="step-ctrl-btn"
                onClick={handleLastStep}
                disabled={currentStepIdx >= totalSteps - 1}
                title="Last Step (>>|)"
              >
                ⏭
              </button>
              <button
                type="button"
                className="step-ctrl-btn reset-btn"
                onClick={handleReset}
                title="Reset to Beginning"
              >
                ↺
              </button>
            </div>

            {/* Step Counter & Progress Slider */}
            <div className="stepper-progress-group">
              <div className="stepper-counter-label">
                Step <span className="step-highlight">{currentStepIdx + 1}</span> of {totalSteps}
              </div>
              <input
                id="visualizer-step-slider"
                name="step_scrubber"
                type="range"
                min="0"
                max={Math.max(0, totalSteps - 1)}
                value={currentStepIdx}
                onChange={handleSliderChange}
                className="visualizer-slider"
                aria-label="Execution step scrubber"
              />
            </div>

            {/* Playback Speed selector */}
            <div className="playback-speed-group">
              <span className="speed-label">Speed:</span>
              {[0.5, 1, 2].map((spd) => (
                <button
                  key={spd}
                  type="button"
                  className={`speed-pill ${playbackSpeed === spd ? 'active' : ''}`}
                  onClick={() => setPlaybackSpeed(spd)}
                >
                  {spd}x
                </button>
              ))}
            </div>
          </div>

          {/* Current Step Event & Line Context Card */}
          <div className="current-step-card">
            <div className="current-step-meta">
              <span className={`event-type-badge ${badgeInfo.className}`}>
                <span className="badge-icon">{badgeInfo.icon}</span>
                {badgeInfo.label}
              </span>

              {currentStep.line_number && (
                <span className="line-number-pill">
                  Line {currentStep.line_number}
                </span>
              )}

              {currentStep.current_function && (
                <span className="func-frame-pill">
                  In function: <code>{currentStep.current_function}()</code>
                </span>
              )}

              {currentStep.loop_iteration !== null && currentStep.loop_iteration !== undefined && (
                <span className="loop-iter-pill">
                  Iteration #{currentStep.loop_iteration}
                </span>
              )}
            </div>

            {/* Description */}
            <p className="step-description">{currentStep.description}</p>

            {/* Source code line snippet */}
            {currentLineCode && (
              <div className="active-code-snippet">
                <span className="code-line-prefix">L{currentStep.line_number}:</span>
                <code>{currentLineCode}</code>
              </div>
            )}
          </div>

          {/* Interactive State Panels Grid */}
          <div className="visualizer-grid">
            {/* Variables Inspector Card */}
            <div className="state-panel variables-panel">
              <div className="panel-header">
                <span className="panel-title">Variables in Scope</span>
                <span className="panel-counter">{Object.keys(currentStep.variable_state || {}).length} variables</span>
              </div>

              <div className="panel-body">
                {Object.keys(currentStep.variable_state || {}).length === 0 ? (
                  <div className="empty-state-text">No variables initialized yet.</div>
                ) : (
                  <div className="vars-table-wrapper">
                    <table className="vars-table">
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Value</th>
                          <th>Type</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(currentStep.variable_state || {}).map(([name, val]) => {
                          const isChanged = changedVars.has(name);
                          const valType = Array.isArray(val) ? 'list' : typeof val;
                          const displayVal = Array.isArray(val)
                            ? `[${val.join(', ')}]`
                            : String(val);

                          return (
                            <tr key={name} className={isChanged ? 'row-updated' : ''}>
                              <td className="var-name-cell">
                                <code>{name}</code>
                                {isChanged && <span className="updated-tag">Updated</span>}
                              </td>
                              <td className="var-value-cell">
                                <code className="var-val-code">{displayVal}</code>
                              </td>
                              <td className="var-type-cell">
                                <span className={`type-tag type-${valType}`}>{valType}</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>

            {/* Lists / Arrays Visualizer Card */}
            <div className="state-panel lists-panel">
              <div className="panel-header">
                <span className="panel-title">Array / List Visualizer</span>
                <span className="panel-counter">
                  {Object.keys(currentStep.list_state || {}).length} lists
                </span>
              </div>

              <div className="panel-body">
                {Object.keys(currentStep.list_state || {}).length === 0 ? (
                  <div className="empty-state-text">No lists currently in scope.</div>
                ) : (
                  <div className="lists-container">
                    {Object.entries(currentStep.list_state || {}).map(([listName, items]) => (
                      <div key={listName} className="list-visual-item">
                        <div className="list-name-bar">
                          <strong>{listName}</strong>
                          <span className="list-len-badge">len: {items.length}</span>
                        </div>
                        <div className="list-cells-track">
                          {items.map((item, idx) => (
                            <div key={idx} className="list-cell-wrapper">
                              <div className="list-cell-box">
                                {String(item)}
                              </div>
                              <span className="cell-index">[{idx}]</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Console Output Panel (if print was used) */}
          {currentStep.output && (
            <div className="visualizer-console-panel">
              <div className="console-header">
                <span>Output Console</span>
                <span className="console-dot" />
              </div>
              <pre className="console-output">{currentStep.output}</pre>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
