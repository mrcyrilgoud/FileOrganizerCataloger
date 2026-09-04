import React, { useState } from 'react';
import axios from 'axios';
import './App.css';

const API_URL = 'http://localhost:8000';

function App() {
  const [directory, setDirectory] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [indexStats, setIndexStats] = useState(null);
  const [explanations, setExplanations] = useState({});
  const [loading, setLoading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [explainingPath, setExplainingPath] = useState(null);
  const [error, setError] = useState(null);
  const [statusMsg, setStatusMsg] = useState(null);

  const handleBrowse = async () => {
    try {
      const res = await axios.post(`${API_URL}/browse`);
      if (res.data.path) setDirectory(res.data.path);
    } catch (err) {
      alert('Failed to open folder picker: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleIndex = async () => {
    if (!directory) return;
    setLoading(true);
    setError(null);
    setStatusMsg(null);
    setIndexStats(null);
    try {
      const res = await axios.post(`${API_URL}/index`, { directory });
      setIndexStats(res.data);
      setStatusMsg(
        `Indexed ${res.data.indexed} new, updated ${res.data.updated}, skipped ${res.data.skipped}. Store total: ${res.data.total_in_store}.`
      );
    } catch (err) {
      setError(err.response?.data?.detail || 'Index failed');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;
    setSearching(true);
    setError(null);
    try {
      const res = await axios.post(`${API_URL}/search`, {
        query: query.trim(),
        limit: 20,
      });
      setResults(res.data.results || []);
      if (!(res.data.results || []).length) {
        setStatusMsg('No matches. Index a directory first, or try a different query.');
      } else {
        setStatusMsg(`Found ${res.data.count} result(s).`);
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  const handleExplain = async (path) => {
    setExplainingPath(path);
    setError(null);
    try {
      const res = await axios.post(`${API_URL}/explain`, { path });
      setExplanations((prev) => ({ ...prev, [path]: res.data.explanation }));
    } catch (err) {
      const detail = err.response?.data?.detail || err.message;
      setExplanations((prev) => ({
        ...prev,
        [path]: `Explain unavailable: ${detail}`,
      }));
    } finally {
      setExplainingPath(null);
    }
  };

  const handleOpen = async (path) => {
    try {
      await axios.post(`${API_URL}/open`, { file_path: path });
    } catch (err) {
      alert('Failed to open: ' + (err.response?.data?.detail || err.message));
    }
  };

  const handleDelete = async (path) => {
    if (!window.confirm(`Move to Trash?\n${path}`)) return;
    try {
      await axios.post(`${API_URL}/delete`, { file_path: path });
      setResults((prev) => prev.filter((r) => r.path !== path));
    } catch (err) {
      alert('Failed to delete: ' + (err.response?.data?.detail || err.message));
    }
  };

  const formatBytes = (bytes) => {
    if (!+bytes) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  return (
    <div className="app-shell">
      <div className="orb orb-a" aria-hidden="true" />
      <div className="orb orb-b" aria-hidden="true" />
      <div className="orb orb-c" aria-hidden="true" />

      <div className="container">
        <header className="header">
          <div className="logo-row">
            <div className="logo-mark" aria-hidden="true" />
            <h1>Sonic Telescope</h1>
          </div>
          <p className="tagline">Local semantic file library — search in plain English</p>
          <span className="phase-chip">Phase 1</span>
        </header>

        <div className="panels-row">
          <section className="panel">
            <h2>
              <span className="panel-step">1</span>
              Index a folder
            </h2>
            <div className="controls">
              <input
                type="text"
                placeholder="/Users/you/Documents..."
                value={directory}
                onChange={(e) => setDirectory(e.target.value)}
                className="dir-input"
              />
              <button type="button" onClick={handleBrowse} className="browse-btn">
                Browse
              </button>
              <button
                type="button"
                onClick={handleIndex}
                disabled={loading || !directory}
                className="primary-btn"
              >
                {loading ? 'Indexing…' : 'Index'}
              </button>
            </div>
          </section>

          <section className="panel">
            <h2>
              <span className="panel-step">2</span>
              Search
            </h2>
            <form className="controls" onSubmit={handleSearch}>
              <input
                type="text"
                placeholder='e.g. "tax docs from last year" or "passport photos"'
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="dir-input search-input"
              />
              <button
                type="submit"
                disabled={searching || !query.trim()}
                className="primary-btn"
              >
                {searching ? 'Searching…' : 'Search'}
              </button>
            </form>
          </section>
        </div>

        {error && <div className="error">{error}</div>}
        {statusMsg && <div className="status">{statusMsg}</div>}

        {indexStats && indexStats.error_count > 0 && (
          <div className="status warn">
            {indexStats.error_count} file(s) had errors during index (first few logged server-side).
          </div>
        )}

        <section className="results-section">
          <h2>Results</h2>
          {results.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon" aria-hidden="true" />
              <p>Point the telescope at a folder, then search in natural language.</p>
              <p className="empty-hint-sub">Index a directory first — matches appear here as glass cards.</p>
            </div>
          ) : (
            <div className="file-list">
              {results.map((file) => (
                <div key={file.path} className="file-card">
                  <div className="file-info">
                    <h3>{file.filename}</h3>
                    <div className="meta-row">
                      <span className="score-badge">score {file.score}</span>
                      {file.mime && <span className="mime">{file.mime}</span>}
                      {file.size != null && (
                        <span className="file-size">{formatBytes(file.size)}</span>
                      )}
                    </div>
                    {file.snippet && <p className="snippet">{file.snippet}</p>}
                    {file.reasons && <p className="reasons">{file.reasons}</p>}
                    <small className="path">{file.path}</small>
                    {explanations[file.path] && (
                      <div className="explanation">
                        <strong>Why it might matter</strong>
                        <p>{explanations[file.path]}</p>
                      </div>
                    )}
                  </div>
                  <div className="file-actions">
                    <button
                      type="button"
                      className="explain-btn"
                      onClick={() => handleExplain(file.path)}
                      disabled={explainingPath === file.path}
                    >
                      {explainingPath === file.path ? 'Explaining…' : 'Explain'}
                    </button>
                    <button
                      type="button"
                      className="open-btn"
                      onClick={() => handleOpen(file.path)}
                    >
                      Open
                    </button>
                    <button
                      type="button"
                      className="delete-btn"
                      onClick={() => handleDelete(file.path)}
                    >
                      Trash
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <footer className="footer">
          <span>Local only · Ollama explain uses loopback · nothing leaves this machine</span>
        </footer>
      </div>
    </div>
  );
}

export default App;
