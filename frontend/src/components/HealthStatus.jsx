import React, { useState, useEffect } from 'react';
import { checkBackendHealth } from '../services/api';

export default function HealthStatus() {
  const [healthData, setHealthData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchHealth = async () => {
    setLoading(true);
    setError(null);
    const result = await checkBackendHealth();
    if (result.success) {
      setHealthData(result.data);
      setError(null);
    } else {
      setError(result.error);
      setHealthData(null);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchHealth();
  }, []);

  return (
    <div id="backend-health-status" className="health-badge-container">
      <div className="health-status-pill">
        <span
          className={`status-indicator-dot ${
            loading ? 'dot-loading' : error ? 'dot-error' : 'dot-online'
          }`}
        />
        <span className="status-label">
          {loading && 'Checking backend status...'}
          {!loading && !error && (
            <>
              <strong>Backend Connected:</strong> {healthData?.message || 'Status OK'}
            </>
          )}
          {!loading && error && (
            <>
              <strong>Backend Offline:</strong> {error}
            </>
          )}
        </span>
      </div>
      <button
        id="refresh-health-btn"
        className="refresh-btn"
        onClick={fetchHealth}
        title="Re-check backend health"
        aria-label="Re-check backend health"
      >
        ↻
      </button>
    </div>
  );
}
