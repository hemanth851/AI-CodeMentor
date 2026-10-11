import React from 'react';
import Editor from '@monaco-editor/react';

export default function CodeEditor({
  value,
  onChange,
  monacoLang = 'plaintext',
  displayLang = 'Auto Detect',
  height = '380px',
  fileName = 'snippet',
}) {
  const lineCount = value ? value.split('\n').length : 0;
  const charCount = value ? value.length : 0;

  const editorOptions = {
    minimap: { enabled: false },
    fontSize: 14,
    fontFamily: "'JetBrains Mono', Consolas, 'Fira Code', 'Courier New', monospace",
    lineNumbers: 'on',
    roundedSelection: true,
    scrollBeyondLastLine: false,
    readOnly: false,
    tabSize: 4,
    automaticLayout: true,
    wordWrap: 'on',
    padding: { top: 14, bottom: 14 },
    cursorBlinking: 'smooth',
    smoothScrolling: true,
    renderLineHighlight: 'all',
  };

  const handleEditorDidMount = (editor) => {
    const domNode = editor.getDomNode();
    if (domNode) {
      const textarea = domNode.querySelector('textarea');
      if (textarea) {
        if (!textarea.id) textarea.id = 'monaco-code-textarea';
        if (!textarea.name) textarea.name = 'code_editor';
      }
    }
  };

  return (
    <div className="monaco-frame-container">
      <div className="monaco-top-header">
        <div className="editor-dots-group">
          <span className="window-dot red" />
          <span className="window-dot yellow" />
          <span className="window-dot green" />
          <span className="active-tab-title">{fileName}</span>
        </div>
        <div className="editor-status-indicators">
          <span className="syntax-badge">{displayLang}</span>
        </div>
      </div>

      <div className="monaco-editor-wrapper">
        <Editor
          height={height}
          language={monacoLang}
          value={value}
          onChange={(newVal) => onChange(newVal ?? '')}
          onMount={handleEditorDidMount}
          theme="vs-dark"
          options={editorOptions}
          loading={
            <div className="monaco-loading-placeholder">
              <span className="spinner" />
              <span>Loading Monaco Code Editor...</span>
            </div>
          }
        />

        {(!value || value.trim() === '') && (
          <div className="editor-empty-state-overlay">
            <div className="empty-state-inner">
              <p className="empty-title">Editor is currently empty</p>
              <p className="empty-desc">
                Paste your code snippet or complete program, or click <strong>Upload Code</strong> below.
              </p>
            </div>
          </div>
        )}
      </div>

      <div className="monaco-bottom-bar">
        <div className="bar-meta-left">
          <span>Lines: {lineCount}</span>
          <span>Characters: {charCount}</span>
        </div>
        <div className="bar-meta-right">
          <span>UTF-8</span>
          <span>Spaces: 4</span>
          <span className="editor-lang-indicator">{displayLang}</span>
        </div>
      </div>
    </div>
  );
}
