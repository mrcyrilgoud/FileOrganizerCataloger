import { useRef, useState } from 'react';
import axios from 'axios';
import './App.css';

const API_URL = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '');

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
  const [explainingPaths, setExplainingPaths] = useState(() => new Set());
  const [isIndexing, setIsIndexing] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState(null);
  const [statusMsg, setStatusMsg] = useState(null);
  const [indexJob, setIndexJob] = useState(null);
  const [catalogNeedsReset, setCatalogNeedsReset] = useState(false);
  const [resultsAreStale, setResultsAreStale] = useState(false);
  const indexVersion = useRef(0);

  const pause = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

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
    setIsIndexing(true);
    setError(null);
    setStatusMsg(null);
    setIndexErrors(0);
    setResultsAreStale(results.length > 0);
    try {
      const { data: started } = await post('/index', { directory });
      setIndexJob(started);
      let job = started;
      while (job.status === 'queued' || job.status === 'running' || job.status === 'cancelling') {
        await pause(400);
        const { data } = await axios.get(`${API_URL}/jobs/${started.job_id}`);
        job = data;
        setIndexJob(data);
      }
      if (job.status === 'completed') {
        const data = job.result;
        indexVersion.current += 1;
        setResultsAreStale(true);
        setIndexErrors(data.error_count || 0);
        setStatusMsg(`Indexed ${data.indexed} new, updated ${data.updated}, removed ${data.removed || 0} stale, skipped ${data.skipped}. Store total: ${data.total_in_store}.`);
        setIndexJob(null);
      } else if (job.status === 'cancelled') {
        setStatusMsg('Indexing cancelled. No catalog changes were saved.');
        setIndexJob(null);
      } else {
        throw new Error(job.error || 'Index failed');
      }
    } catch (err) {
      const message = apiDetail(err, 'Index failed');
      setError(message);
      setCatalogNeedsReset(err.response?.status === 409 && /embedding|index profile/i.test(message));
      setIndexJob(null);
    } finally {
      setIsIndexing(false);
    }
  };

  const handleResetCatalog = async () => {
    const confirmed = window.confirm(
      'Clear every catalog entry and embedding? Files on disk will stay unchanged, but you will need to re-index each folder. The selected folder will be re-indexed now.'
    );
    if (!confirmed) return;
    try {
      await post('/index/reset', {});
      setResults([]);
      setResultsAreStale(false);
      setExplanations({});
      setCatalogNeedsReset(false);
      setError(null);
      setStatusMsg('Catalog cleared. Re-indexing the selected folder; add other folders again afterward.');
      if (directory) await handleIndex();
    } catch (err) {
      setError(apiDetail(err, 'Could not clear the catalog'));
    }
  };

  const handleCancelIndex = async () => {
    if (!indexJob?.job_id) return;
    try {
      const { data } = await post(`/jobs/${indexJob.job_id}/cancel`, {});
      setIndexJob(data);
    } catch (err) {
      setError(apiDetail(err, 'Could not cancel indexing'));
    }
  };

  const handleSearch = async (e) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;
    setIsSearching(true);
    setError(null);
    setStatusMsg(null);
    const versionAtStart = indexVersion.current;
    try {
      const { data } = await post('/search', { query: query.trim(), limit: 20 });
      const hits = data.results || [];
      setResults(hits);
      setResultsAreStale(versionAtStart !== indexVersion.current);
      setStatusMsg(hits.length ? `Found ${data.count} result(s).` : 'No matches. Index a directory first, or try a different query.');
    } catch (err) {
      const message = apiDetail(err, 'Search failed');
      setError(message);
      setCatalogNeedsReset(err.response?.status === 409 && /embedding|index profile/i.test(message));
    } finally {
      setIsSearching(false);
    }
  };

  const handleExplain = async (path) => {
    setExplainingPaths((prev) => new Set(prev).add(path));
    try {
      const { data } = await post('/explain', { path });
      setExplanations((prev) => ({ ...prev, [path]: data.explanation }));
    } catch (err) {
      setExplanations((prev) => ({ ...prev, [path]: `Explain unavailable: ${apiDetail(err, err.message)}` }));
    } finally {
      setExplainingPaths((prev) => {
        const next = new Set(prev);
        next.delete(path);
        return next;
      });
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
                aria-label="Folder to index"
                placeholder="/Users/you/Documents..."
                value={directory}
                onChange={(e) => setDirectory(e.target.value)}
                className="dir-input"
              />
              <button type="button" onClick={handleBrowse} className="btn browse-btn">Browse</button>
              <button
                type="button"
                onClick={handleIndex}
                disabled={isIndexing || !directory}
                className="btn primary-btn"
              >
                {isIndexing ? `${indexJob?.stage === 'embedding' ? 'Embedding' : 'Indexing'}…` : 'Index'}
              </button>
              {isIndexing && indexJob?.status !== 'cancelling' && indexJob?.stage !== 'saving' && (
                <button type="button" onClick={handleCancelIndex} className="btn">Cancel</button>
              )}
            </div>
            {isIndexing && indexJob && (
              <p className="job-progress" role="status">
                {indexJob.stage === 'embedding' && indexJob.total != null
                  ? `Embedding ${indexJob.completed} of ${indexJob.total} files`
                  : indexJob.stage === 'saving' ? 'Saving catalog changes…' : 'Scanning files…'}
              </p>
            )}
          </section>

          <section className="panel glass">
            <h2><span className="panel-step">2</span> Search</h2>
            <form className="controls" onSubmit={handleSearch}>
              <input
                type="text"
                aria-label="Search query"
                placeholder='e.g. "tax docs from last year" or "passport photos"'
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                className="dir-input"
              />
              <button type="submit" disabled={isSearching || !query.trim()} className="btn primary-btn">
                {isSearching ? 'Searching…' : 'Search'}
              </button>
            </form>
          </section>
        </div>

        {error && <div className="banner error" role="alert" aria-live="assertive">{error}</div>}
        {catalogNeedsReset && (
          <div className="banner status warn">
            <p>The stored vectors cannot be compared safely with the active embedding model.</p>
            <button type="button" className="btn" onClick={handleResetCatalog}>Clear catalog and re-index selected folder</button>
          </div>
        )}
        {statusMsg && <div className="banner status" role="status" aria-live="polite" aria-atomic="true">{statusMsg}</div>}
        {indexErrors > 0 && (
          <div className="banner status warn">{indexErrors} file(s) had errors during index (first few logged server-side).</div>
        )}

        <section className="results-section">
          <h2>Results</h2>
          {resultsAreStale && results.length > 0 && (
            <p className="stale-results" role="status">These results are from before the latest indexing run. Search again to refresh them.</p>
          )}
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
                      disabled={explainingPaths.has(file.path)}
                    >
                      {explainingPaths.has(file.path) ? 'Explaining…' : 'Explain'}
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
