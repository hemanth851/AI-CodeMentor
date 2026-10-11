import React from 'react';
import { LEARNING_LEVELS } from '../constants/editorConfig';

export default function LevelSelector({ selectedLevel, onLevelChange }) {
  const handleChange = (e) => {
    const level = LEARNING_LEVELS.find((l) => l.id === e.target.value);
    if (level) {
      onLevelChange(level);
    }
  };

  return (
    <div className="selector-group">
      <label htmlFor="level-select" className="selector-label">
        Explanation Level
      </label>
      <div className="select-wrapper">
        <select
          id="level-select"
          name="learning_level"
          className="custom-select"
          value={selectedLevel.id}
          onChange={handleChange}
          aria-label="Select Explanation Level"
        >
          {LEARNING_LEVELS.map((level) => (
            <option key={level.id} value={level.id}>
              {level.label}
            </option>
          ))}
        </select>
        <span className="select-arrow" aria-hidden="true">▼</span>
      </div>
    </div>
  );
}
