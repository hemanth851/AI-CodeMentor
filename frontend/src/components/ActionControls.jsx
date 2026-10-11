import React, { useRef } from 'react';
import {
  MAX_FILE_SIZE_BYTES,
  MAX_FILE_SIZE_LABEL,
  ACCEPTED_FILE_EXTENSIONS,
  detectLanguageFromFilename,
} from '../constants/editorConfig';

export default function ActionControls({
  sourceCode,
  onCodeChange,
  onFileUploaded,
  onClear,
  onFeedback,
  onAnalyze,
  isAnalyzing = false,
}) {
  const fileInputRef = useRef(null);

  const handleUploadClick = () => {
    if (isAnalyzing) return;
    if (fileInputRef.current) {
      fileInputRef.current.value = ''; // Reset so uploading same file works
      fileInputRef.current.click();
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // 1. Validation: File size limit (100 KB)
    if (file.size > MAX_FILE_SIZE_BYTES) {
      const sizeInKb = (file.size / 1024).toFixed(1);
      onFeedback({
        type: 'error',
        message: `File size exceeds the ${MAX_FILE_SIZE_LABEL} limit (${sizeInKb} KB). Please upload a smaller file.`,
      });
      return;
    }

    // 2. Read file contents
    const reader = new FileReader();

    reader.onload = (event) => {
      const content = event.target?.result;
      if (typeof content === 'string') {
        onCodeChange(content);
        const detected = detectLanguageFromFilename(file.name);
        onFileUploaded(file.name, detected);
        onFeedback({
          type: 'success',
          message: `Loaded "${file.name}". Click Analyze Code to examine.`,
        });
      } else {
        onFeedback({
          type: 'error',
          message: `Could not parse the contents of "${file.name}".`,
        });
      }
    };

    reader.onerror = () => {
      onFeedback({
        type: 'error',
        message: `Failed to read file "${file.name}". Please check file permissions and try again.`,
      });
    };

    reader.readAsText(file);
  };

  const handleAnalyzeClick = () => {
    if (isAnalyzing) return;

    if (!sourceCode || sourceCode.trim() === '') {
      onFeedback({
        type: 'error',
        message: 'Please enter or upload some code before analyzing.',
      });
      return;
    }

    if (onAnalyze) {
      onAnalyze();
    }
  };

  return (
    <div className="action-controls-bar">
      <input
        ref={fileInputRef}
        id="code-file-input"
        name="code_file"
        type="file"
        accept={ACCEPTED_FILE_EXTENSIONS}
        style={{ display: 'none' }}
        onChange={handleFileChange}
        aria-label="Upload code file"
      />

      <div className="action-buttons-group">
        <button
          id="upload-code-btn"
          type="button"
          className="btn btn-secondary"
          onClick={handleUploadClick}
          disabled={isAnalyzing}
          title={isAnalyzing ? 'Analysis in progress' : 'Upload code file'}
        >
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
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          Upload Code
        </button>

        <button
          id="clear-code-btn"
          type="button"
          className="btn btn-outline"
          onClick={onClear}
          disabled={isAnalyzing}
          title={isAnalyzing ? 'Analysis in progress' : 'Clear current code from the editor'}
        >
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
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
          </svg>
          Clear
        </button>
      </div>

      <div className="action-primary-group">
        <button
          id="analyze-code-btn"
          type="button"
          className={`btn btn-primary ${isAnalyzing ? 'btn-loading' : ''}`}
          onClick={handleAnalyzeClick}
          disabled={isAnalyzing}
        >
          {isAnalyzing ? (
            <>
              <svg
                className="btn-spinner"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
              Analyzing your code...
            </>
          ) : (
            <>
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
                <polygon points="5 3 19 12 5 21 5 3" />
              </svg>
              Analyze Code
            </>
          )}
        </button>
      </div>
    </div>
  );
}
