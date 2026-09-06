import { useState } from 'react';
import axios from 'axios';
import './App.css';

const API_URL = 'http://localhost:8000';

const apiDetail = (err, fallback) => err.response?.data?.detail || err.message || fallback;
const post = (path, body) => axios.post(`${API_URL}${path}`, body);
const formatBytes = (bytes) => {
  if (!+bytes) return '0 B';
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / 1024 ** i).toFixed(1)} ${['B', 'KB', 'MB', 'GB'][i]}`;
};

function App() {
  const [directory, setDirectory] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [indexErrors, setIndexErrors] = useState(0);
  const [explanations, setExplanations] = useState({});
  const [busy, setBusy] = useState('');
  const [error, setError] = useState(null);
  const [statusMsg, setStatusMsg] = useState(null);

  const handleBrowse = async () => {
    try {
      const { data } = await post('/browse');
      if (data.path) setDirectory(data.path);
    } catch (err) {
      alert(`Failed to open folder picker: ${apiDetail(err, 'browse failed')}`);
    }
  };

  const handleIndex = async () => {
    if (!directory) return;
    setBusy('index');
    setError(null);
    setStatusMsg(null);
    setIndexErrors(0);
    try {
      const { data } = await post('/index', { directory });
      setIndexErrors(data.error_count || 0);
      setStatusMsg(`Indexed ${data.indexed} new, updated ${data.updated}, skipped ${data.skipped}. Store total: ${data.total_in_store}.`);
    } catch (err) {
      setError(apiDetail(err, 'Index failed'));
    } finally {
      setBusy('');
    }
  };

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;
    setBusy('search');
    setError(null);
    try {
      const { data } = await post('/search', { query: query.trim(), limit: 20 });
      const hits = data.results || [];
      setResults(hits);
      setStatusMsg(hits.length ? `Found ${data.count} result(s).` : 'No matches. Index a directory first, or try a different query.');
    } catch (err) {
      setError(apiDetail(err, 'Search failed'));
    } finally {
      setBusy('');
    }
  };

  const handleExplain = async (path) => {
    setBusy(path);
    setError(null);
    try {
      const { data } = await post('/explain', { path });
      setExplanations((prev) => ({ ...prev, [path]: data.explanation }));
    } catch (err) {
      setExplanations((prev) => ({ ...prev, [path]: `Explain unavailable: ${apiDetail(err, err.message)}` }));
    } finally {
      setBusy('');
    }
  };

  const handleOpen = async (path) => {
    try {
      await post('/open', { file_path: path });
    } catch (err) {
      alert(`Failed to open: ${apiDetail(err, 'open failed')}`);
    }
  };

  const handleDelete = async (path) => {
    if (!window.confirm(`Move to Trash?\n${path}`)) return;
    try {
      await post('/delete', { file_path: path });
      setResults((prev) => prev.filter((r) => r.path !== path));
    } catch (err) {
      alert(`Failed to delete: ${apiDetail(err, 'delete failed')}`);
    }
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
          <section className="panel glass">
            <h2><span className="panel-step">1</span> Index a folder</h2>
            <div className="controls">
              <input
                type="text"
                placeholder="/Users/you/Documents..."
                value={directory}
                onChange={(e) => setDirectory(e.target.value)}
                className="dir-input"
              />
              <button type="button" onClick={handleBrowse} className="btn browse-btn">Browse</button>
              <button
                type="button"
                onClick={handleIndex}
                disabled={busy === 'index' || !directory}
                className="btn primary-btn"
              >
                {busy === 'index' ? 'Indexing…' : 'Index'}
              </button>
            </div>
          </section>

          <section className="panel glass">
            <h2><span className="panel-step">2</span> Search</h2>
            <form className="controls" onSubmit={handleSearch}>
              <input
                type="text"
                placeholder='e.g. "tax docs from last year" or "passport photos"'
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="dir-input"
              />
              <button type="submit" disabled={busy === 'search' || !query.trim()} className="btn primary-btn">
                {busy === 'search' ? 'Searching…' : 'Search'}
              </button>
            </form>
          </section>
        </div>

        {error && <div className="banner error">{error}</div>}
        {statusMsg && <div className="banner status">{statusMsg}</div>}
        {indexErrors > 0 && (
          <div className="banner status warn">{indexErrors} file(s) had errors during index (first few logged server-side).</div>
        )}

        <section className="results-section">
          <h2>Results</h2>
          {results.length === 0 ? (
            <div className="empty-state glass">
              <div className="empty-icon" aria-hidden="true" />
              <p>Point the telescope at a folder, then search in natural language.</p>
              <p className="empty-hint-sub">Index a directory first — matches appear here as glass cards.</p>
            </div>
          ) : (
            <div className="file-list">
              {results.map((file) => (
                <div key={file.path} className="file-card glass">
                  <div className="file-info">
                    <h3>{file.filename}</h3>
                    <div className="meta-row">
                      <span className="score-badge">score {file.score}</span>
                      {file.mime && <span className="mime">{file.mime}</span>}
                      {file.size != null && <span className="file-size">{formatBytes(file.size)}</span>}
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
                      className="btn explain-btn"
                      onClick={() => handleExplain(file.path)}
                      disabled={busy === file.path}
                    >
                      {busy === file.path ? 'Explaining…' : 'Explain'}
                    </button>
                    <button type="button" className="btn open-btn" onClick={() => handleOpen(file.path)}>Open</button>
                    <button type="button" className="btn delete-btn" onClick={() => handleDelete(file.path)}>Trash</button>
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
