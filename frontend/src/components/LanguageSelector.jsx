import React from 'react';
import { SUPPORTED_LANGUAGES } from '../constants/editorConfig';

export default function LanguageSelector({ selectedLanguage, onLanguageChange }) {
  const handleChange = (e) => {
    const lang = SUPPORTED_LANGUAGES.find((l) => l.id === e.target.value);
    if (lang) {
      onLanguageChange(lang);
    }
  };

  return (
    <div className="selector-group">
      <label htmlFor="language-select" className="selector-label">
        Programming Language
      </label>
      <div className="select-wrapper">
        <select
          id="language-select"
          name="programming_language"
          className="custom-select"
          value={selectedLanguage.id}
          onChange={handleChange}
          aria-label="Select Programming Language"
        >
          {SUPPORTED_LANGUAGES.map((lang) => (
            <option key={lang.id} value={lang.id}>
              {lang.label}
            </option>
          ))}
        </select>
        <span className="select-arrow" aria-hidden="true">▼</span>
      </div>
    </div>
  );
}
