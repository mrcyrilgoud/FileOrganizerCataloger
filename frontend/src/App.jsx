import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
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
const formatScore = (score) => Number.isFinite(Number(score)) ? Number(score).toFixed(2) : '—';
const shortPath = (path, max = 64) => path?.length > max ? `…${path.slice(-(max - 1))}` : path;

function Icon({ name, size = 18 }) {
  const common = { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true };
  const paths = {
    library: <><rect x="4" y="4" width="16" height="16" rx="3" /><path d="M8 8h8M8 12h8M8 16h5" /></>,
    folder: <><path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" /><path d="M3.5 9h17" /></>,
    search: <><circle cx="10.8" cy="10.8" r="6.3" /><path d="m15.5 15.5 4.3 4.3" /></>,
    file: <><path d="M6 3.8h8l4 4v12.4H6z" /><path d="M14 3.8v4h4M9 12h6M9 15.5h6" /></>,
    open: <><path d="M13 5h6v6M19 5l-9 9" /><path d="M18 13v5a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5" /></>,
    trash: <><path d="M4.5 7h15M9 7V4.5h6V7m2.5 0-.8 13H7.3L6.5 7M10 10.5v6m4-6v6" /></>,
    close: <><path d="m6 6 12 12M18 6 6 18" /></>,
    sparkle: <><path d="m12 3 1.5 6.5L20 11l-6.5 1.5L12 19l-1.5-6.5L4 11l6.5-1.5z" /><path d="m19 15 .7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7z" /></>,
    check: <path d="m5 12.5 4.5 4L19 7" />,
    alert: <><path d="M12 3.5 21 20H3z" /><path d="M12 9v4.5m0 3h.01" /></>,
    pin: <><path d="M12 21s7-6.2 7-12a7 7 0 1 0-14 0c0 5.8 7 12 7 12Z" /><circle cx="12" cy="9" r="2.2" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
  };
  return <svg {...common}>{paths[name] || paths.file}</svg>;
}

function Sidebar({ apiStatus, indexedCount }) {
  return (
    <aside className="sidebar" aria-label="Main navigation">
      <div className="brand-lockup">
        <div className="brand-mark"><Icon name="search" size={19} /></div>
        <div><span className="brand-name">Sonic Telescope</span><span className="brand-caption">Private file library</span></div>
      </div>
      <nav className="primary-nav">
        <a className="nav-item active" href="#library" aria-current="page"><Icon name="library" /><span>Library</span></a>
      </nav>
      <div className="sidebar-bottom">
        <div className="local-card">
          <span className={`status-dot ${apiStatus === 'connected' ? 'is-connected' : ''}`} />
          <div><strong>{apiStatus === 'connected' ? 'Local API connected' : apiStatus === 'checking' ? 'Checking local service' : 'Local API unavailable'}</strong><span>{indexedCount == null ? 'Catalog status pending' : `${indexedCount.toLocaleString()} indexed files`}</span></div>
        </div>
        <p className="privacy-note">Catalog stored on this Mac.</p>
      </div>
    </aside>
  );
}

function SourcePanel({ directory, setDirectory, onBrowse, onIndex, isIndexing, indexJob, onCancel, apiStatus }) {
  const canCancel = isIndexing && indexJob?.status !== 'cancelling' && indexJob?.stage !== 'saving';
  const progress = indexJob?.stage === 'embedding' && indexJob.total > 0
    ? Math.min(100, Math.round((indexJob.completed / indexJob.total) * 100)) : null;
  const stageText = indexJob?.stage === 'embedding' && indexJob.total != null
    ? `Embedding ${indexJob.completed} of ${indexJob.total} files`
    : indexJob?.stage === 'saving' ? 'Saving catalog changes…'
      : indexJob?.status === 'cancelling' ? 'Cancelling indexing…' : 'Scanning files…';

  return (
    <section className="source-panel" aria-labelledby="source-title">
      <div className="source-icon"><Icon name="folder" /></div>
      <div className="source-content">
        <div className="source-heading"><h2 id="source-title">Search in a folder</h2><span className="local-label"><span className={`status-dot ${apiStatus === 'connected' ? 'is-connected' : ''}`} /> {apiStatus === 'connected' ? 'Local index' : 'Local catalog'}</span></div>
        <div className="source-controls">
          <label className="visually-hidden" htmlFor="folder-path">Folder to index</label>
          <input id="folder-path" aria-label="Folder to index" value={directory} onChange={(event) => setDirectory(event.target.value)} placeholder="Choose a folder to get started" title={directory || undefined} disabled={isIndexing} />
          <button type="button" className="button secondary" onClick={onBrowse} disabled={isIndexing}>Choose folder</button>
          <button type="button" className="button primary" onClick={onIndex} disabled={!directory || isIndexing}>{isIndexing ? 'Indexing…' : 'Index folder'}</button>
          {canCancel && <button type="button" className="button quiet" onClick={onCancel}>Cancel</button>}
        </div>
        {isIndexing && indexJob && (
          <div className="job-progress" role="status" aria-live="polite" aria-atomic="true">
            <div className="job-progress-copy"><span>{stageText}</span>{progress != null && <span>{progress}%</span>}</div>
            {progress != null && <div className="progress-track" aria-label={`${progress}% indexed`}><span style={{ width: `${progress}%` }} /></div>}
            {progress == null && <div className="progress-track indeterminate"><span /></div>}
          </div>
        )}
        <p className="source-footnote">Files and search stay on your device. First model use may download model files.</p>
        <span className="service-state visually-hidden" aria-live="polite">{apiStatus === 'connected' ? 'Local API connected' : apiStatus === 'unavailable' ? 'Local API unavailable' : ''}</span>
      </div>
    </section>
  );
}

function SearchBar({ query, setQuery, onSearch, isSearching }) {
  return (
    <form className="search-form" onSubmit={onSearch} role="search">
      <Icon name="search" size={20} />
      <label className="visually-hidden" htmlFor="semantic-query">Search query</label>
      <input id="semantic-query" aria-label="Search query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Describe the file you’re looking for…" />
      <kbd className="enter-hint">↵</kbd>
      <button type="submit" className="button search-button" disabled={isSearching || !query.trim()}>{isSearching ? <><span className="spinner" />Searching</> : 'Search'}</button>
      <span className="visually-hidden" role="status" aria-live="polite">{isSearching ? 'Searching your local index' : ''}</span>
    </form>
  );
}

function ResultRow({ file, selected, explaining, explainDisabled, onSelect, onExplain, onOpen }) {
  return (
    <article className={`result-row${selected ? ' selected' : ''}`}>
      <button type="button" className="result-select" data-file-path={file.path} aria-label={`Select ${file.filename}`} aria-pressed={selected} onClick={onSelect}>
        <span className="file-type-icon"><Icon name="file" size={19} /></span>
        <span className="result-main">
          <span className="result-topline"><strong>{file.filename}</strong><span className="match-score">Match {formatScore(file.score)}</span></span>
          <span className="result-path" title={file.path}>{shortPath(file.path)}</span>
          {file.snippet && <span className="result-snippet">{file.snippet}</span>}
          <span className="result-meta">{file.mime && <span>{file.mime}</span>}{file.size != null && <span>{formatBytes(file.size)}</span>}</span>
        </span>
      </button>
      <div className="row-actions" aria-label={`Actions for ${file.filename}`}>
        <button type="button" className="icon-action explain-action" aria-label={`Explain ${file.filename}`} onClick={onExplain} disabled={explaining || explainDisabled} title={explaining ? 'Preparing explanation' : explainDisabled ? 'Another explanation is in progress' : 'Explain match'}><Icon name="sparkle" size={16} /></button>
        <button type="button" className="icon-action" aria-label={`Open ${file.filename}`} onClick={onOpen} title="Open file"><Icon name="open" size={16} /></button>
      </div>
    </article>
  );
}

function FileDetailPanel({ file, explanation, explaining, onExplain, onOpen, onTrash, onClose, error, notice, isDialog, closeButtonRef }) {
  if (!file) return (
    <aside className="detail-panel detail-empty" aria-label="File details">
      {notice && <p className="action-notice" role="status">{notice}</p>}
      {error && <p className="action-error" role="alert">{error}</p>}
      <div className="detail-empty-icon"><Icon name="file" size={22} /></div>
      <h2>Select a file</h2><p>Choose a search result to see its location, match details, and local explanation.</p>
    </aside>
  );
  return (
    <aside
      className="detail-panel"
      role={isDialog ? 'dialog' : undefined}
      aria-modal={isDialog ? 'true' : undefined}
      aria-label={`File details for ${file.filename}`}
      onKeyDown={(event) => {
        if (!isDialog || event.key !== 'Tab') return;
        const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled), a[href], input:not(:disabled), [tabindex]:not([tabindex="-1"])')];
        if (!controls.length) return;
        const first = controls[0]; const last = controls.at(-1);
        if (!event.currentTarget.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
        else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }}
    >
      <div className="detail-header"><span>File details</span><button ref={closeButtonRef} type="button" className="icon-action close-detail" aria-label="Close file details" onClick={onClose}><Icon name="close" /></button></div>
      <div className="detail-file-icon"><Icon name="file" size={22} /></div>
      <h2 className="detail-filename">{file.filename}</h2>
      <p className="detail-path" title={file.path}>{file.path}</p>
      <div className="detail-metadata">
        {file.mime && <div><span>Type</span><strong>{file.mime}</strong></div>}
        {file.size != null && <div><span>Size</span><strong>{formatBytes(file.size)}</strong></div>}
        {file.score != null && <div><span>Relevance</span><strong>Match {formatScore(file.score)}</strong></div>}
      </div>
      {file.snippet && <section className="detail-section"><h3>Indexed excerpt</h3><p className="detail-excerpt">{file.snippet}</p></section>}
      {file.reasons && <section className="detail-section"><h3>Match details</h3><p>{file.reasons}</p></section>}
      <section className="explain-section"><div className="explain-heading"><span className="explain-icon"><Icon name="sparkle" size={16} /></span><h3>Why this match</h3></div>
        {explanation ? <p className={`explanation-copy${explanation.isError ? ' explanation-error' : ''}`}>{explanation.text}</p> : <p className="explain-hint">Generated locally by Ollama from file metadata and a short excerpt.</p>}
        <button type="button" className="button secondary explain-button" onClick={onExplain} disabled={explaining}><Icon name="sparkle" size={15} />{explaining ? 'Preparing explanation…' : explanation?.isError ? 'Try again' : explanation ? 'Explain again' : 'Explain match'}</button>
      </section>
      {notice && <p className="action-notice" role="status">{notice}</p>}
      {error && <p className="action-error" role="alert">{error}</p>}
      <div className="detail-actions"><button type="button" className="button primary open-file-button" onClick={onOpen}><Icon name="open" size={16} />Open file</button><button type="button" className="button danger" onClick={onTrash}><Icon name="trash" size={16} />Move to Trash…</button></div>
    </aside>
  );
}

function App() {
  const [directory, setDirectory] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [selectedPath, setSelectedPath] = useState(null);
  const [indexErrors, setIndexErrors] = useState(0);
  const [explanations, setExplanations] = useState({});
  const [explainingPaths, setExplainingPaths] = useState(() => new Set());
  const [isIndexing, setIsIndexing] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState(null);
  const [actionError, setActionError] = useState(null);
  const [actionNotice, setActionNotice] = useState(null);
  const [statusMsg, setStatusMsg] = useState(null);
  const [searchFailed, setSearchFailed] = useState(false);
  const [indexJob, setIndexJob] = useState(null);
  const [catalogNeedsReset, setCatalogNeedsReset] = useState(false);
  const [resultsAreStale, setResultsAreStale] = useState(false);
  const [apiStatus, setApiStatus] = useState('checking');
  const [indexedCount, setIndexedCount] = useState(null);
  const [isCompactLayout, setIsCompactLayout] = useState(() => window.matchMedia('(max-width: 1359px)').matches);
  const indexVersion = useRef(0);
  const lastSearchIndexVersion = useRef(null);
  const previousFocus = useRef(null);
  const closeButtonRef = useRef(null);
  const detailOpen = Boolean(selectedPath);
  const selectedFile = useMemo(() => results.find((file) => file.path === selectedPath) || null, [results, selectedPath]);

  useEffect(() => {
    let active = true;
    axios.get(`${API_URL}/health`).then(({ data }) => {
      if (active) { setApiStatus('connected'); setIndexedCount(data.indexed_files ?? null); }
    }).catch(() => { if (active) setApiStatus('unavailable'); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const media = window.matchMedia('(max-width: 1359px)');
    const updateLayout = (event) => setIsCompactLayout(event.matches);
    media.addEventListener('change', updateLayout);
    return () => media.removeEventListener('change', updateLayout);
  }, []);

  useEffect(() => {
    if (!detailOpen) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setSelectedPath(null);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => {
      window.removeEventListener('keydown', closeOnEscape);
      previousFocus.current?.focus?.();
    };
  }, [detailOpen]);

  useLayoutEffect(() => {
    if (isCompactLayout && detailOpen) closeButtonRef.current?.focus();
  }, [isCompactLayout, detailOpen, selectedPath]);

  const pause = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms));

  const handleBrowse = async () => {
    setError(null);
    try {
      const { data } = await post('/browse');
      if (data.path) setDirectory(data.path);
    } catch (err) {
      setError(`Could not open the folder picker: ${apiDetail(err, 'browse failed')}`);
    }
  };

  const handleIndex = async () => {
    if (!directory || isIndexing) return;
    const staleBeforeIndex = resultsAreStale;
    setIsIndexing(true);
    setError(null); setStatusMsg(null); setSearchFailed(false); setIndexErrors(0);
    setResultsAreStale(results.length > 0);
    try {
      const { data: started } = await post('/index', { directory });
      setIndexJob(started);
      let job = started;
      while (job.status === 'queued' || job.status === 'running' || job.status === 'cancelling') {
        await pause(400);
        const { data } = await axios.get(`${API_URL}/jobs/${started.job_id}`);
        job = data; setIndexJob(data);
      }
      if (job.status === 'completed') {
        const data = job.result;
        indexVersion.current += 1;
        setResultsAreStale(lastSearchIndexVersion.current != null && lastSearchIndexVersion.current !== indexVersion.current);
        setIndexErrors(data.error_count || 0);
        setIndexedCount(data.total_in_store ?? null);
        setStatusMsg(`Indexed ${data.indexed} new · updated ${data.updated} · skipped ${data.skipped} · removed ${data.removed || 0} stale. Catalog total: ${data.total_in_store}.`);
        setIndexJob(null);
      } else if (job.status === 'cancelled') {
        setResultsAreStale(staleBeforeIndex);
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
    } finally { setIsIndexing(false); }
  };

  const handleResetCatalog = async () => {
    if (isIndexing) return;
    const confirmed = window.confirm(`Clear the local catalog and embeddings? Files on disk will stay unchanged.${directory ? ' The selected folder will be re-indexed now.' : ''}`);
    if (!confirmed) return;
    try {
      await post('/index/reset', {});
      previousFocus.current = document.getElementById('folder-path');
      setResults([]); setSelectedPath(null); setResultsAreStale(false); setExplanations({}); setIndexedCount(0); setCatalogNeedsReset(false); setError(null);
      setStatusMsg(directory ? 'Catalog cleared. Re-indexing the selected folder. Files on disk were not changed.' : 'Catalog cleared. Files on disk were not changed.');
      if (directory) await handleIndex();
    } catch (err) { setError(apiDetail(err, 'Could not clear the catalog')); }
  };

  const handleCancelIndex = async () => {
    if (!indexJob?.job_id) return;
    try { setIndexJob(await post(`/jobs/${indexJob.job_id}/cancel`, {}).then(({ data }) => data)); }
    catch (err) { setError(apiDetail(err, 'Could not cancel indexing')); }
  };

  const handleSearch = async (event) => {
    event?.preventDefault();
    if (!query.trim()) return;
    setIsSearching(true); setError(null); setSearchFailed(false); setActionError(null); setActionNotice(null); setStatusMsg(null);
    const versionAtStart = indexVersion.current;
    try {
      const { data } = await post('/search', { query: query.trim(), limit: 20 });
      const hits = data.results || [];
      setResults(hits); setSelectedPath(null);
      lastSearchIndexVersion.current = versionAtStart;
      setResultsAreStale(versionAtStart !== indexVersion.current);
      setStatusMsg(hits.length ? `Found ${data.count} result${data.count === 1 ? '' : 's'}.` : 'No matches in this catalog. Index a folder or try different words.');
    } catch (err) {
      const message = apiDetail(err, 'Search failed'); setError(message); setSearchFailed(true);
      setCatalogNeedsReset(err.response?.status === 409 && /embedding|index profile|legacy embeddings/i.test(message));
    } finally { setIsSearching(false); }
  };

  const handleExplain = async (path) => {
    if (explainingPaths.size > 0) return;
    setExplainingPaths(new Set([path])); setActionError(null); setActionNotice(null);
    try {
      const { data } = await post('/explain', { path });
      setExplanations((current) => ({ ...current, [path]: { text: data.explanation, isError: false } }));
    } catch (err) {
      setExplanations((current) => ({ ...current, [path]: { text: `Explain unavailable: ${apiDetail(err, err.message)}`, isError: true } }));
    } finally { setExplainingPaths(new Set()); }
  };

  const handleOpen = async (path) => {
    const file = results.find((entry) => entry.path === path);
    setActionError(null); setActionNotice(null);
    try { await post('/open', { file_path: path }); }
    catch (err) { setSelectedPath(path); setActionError(`Could not open ${file?.filename || 'file'}: ${apiDetail(err, 'open failed')}`); }
  };

  const removeResult = (path, message) => {
    const index = results.findIndex((file) => file.path === path);
    const next = results.filter((file) => file.path !== path);
    setResults(next);
    if (selectedPath === path) {
      const nextSelection = next[index]?.path || next[index - 1]?.path || null;
      setSelectedPath(nextSelection);
      if (nextSelection) {
        window.requestAnimationFrame(() => {
          const nextButton = Array.from(document.querySelectorAll('.result-select')).find((button) => button.dataset.filePath === nextSelection) || null;
          previousFocus.current = nextButton;
          if (!isCompactLayout) nextButton?.focus();
        });
      } else previousFocus.current = document.getElementById('semantic-query');
    }
    setExplanations((current) => { const next = { ...current }; delete next[path]; return next; });
    setActionError(null); setActionNotice(message);
  };

  const handleTrash = async (path) => {
    const file = results.find((entry) => entry.path === path);
    if (!window.confirm(`Move “${file?.filename || path}” to system Trash? You can restore it from Trash.`)) return;
    setActionError(null); setActionNotice(null);
    try {
      await post('/delete', { file_path: path });
      removeResult(path, `${file?.filename || 'File'} moved to Trash.`);
      setIndexedCount((count) => count == null ? count : Math.max(0, count - 1));
    } catch (err) {
      const message = apiDetail(err, 'Trash action failed');
      if (err.response?.status === 500 && /File moved to Trash, but index cleanup failed/i.test(message)) {
        removeResult(path, `${file?.filename || 'File'} was moved to Trash, but the catalog cleanup failed. Search results may be stale.`);
        setResultsAreStale(true);
      } else setActionError(message);
    }
  };

  const handleDetailClose = () => setSelectedPath(null);

  return (
    <div className="app-shell" id="library">
      <div inert={isCompactLayout && detailOpen} aria-hidden={isCompactLayout && detailOpen || undefined}><Sidebar apiStatus={apiStatus} indexedCount={indexedCount} /></div>
      <main className="main-workspace">
        <header className="topbar" inert={isCompactLayout && detailOpen} aria-hidden={isCompactLayout && detailOpen || undefined}><div className="breadcrumb"><span>Library</span><Icon name="chevron" size={14} /><span className="breadcrumb-current">Semantic search</span></div><div className="topbar-status" title={directory || 'No folder selected'}><Icon name="pin" size={14} /><span>{directory ? shortPath(directory, 38) : 'No folder selected'}</span></div></header>
        <div className="workspace-grid">
          <section className="results-workspace" aria-label="File library" inert={isCompactLayout && detailOpen} aria-hidden={isCompactLayout && detailOpen || undefined}>
            <div className="page-heading"><div><p className="eyebrow">Semantic search</p><h1>Find files by meaning</h1><p className="page-subtitle">A calm, private library for folders you choose.</p></div></div>
            <SourcePanel directory={directory} setDirectory={setDirectory} onBrowse={handleBrowse} onIndex={handleIndex} isIndexing={isIndexing} indexJob={indexJob} onCancel={handleCancelIndex} apiStatus={apiStatus} />
            <SearchBar query={query} setQuery={setQuery} onSearch={handleSearch} isSearching={isSearching} />
            {error && <div className="notice error-notice" role="alert"><Icon name="alert" /><span>{error}</span></div>}
            {catalogNeedsReset && <div className="notice warning-notice" role="status" aria-live="polite"><Icon name="alert" /><div><strong>Catalog needs to be rebuilt</strong><p>Stored vectors cannot be compared safely with the active embedding model. Clearing the catalog leaves files on disk unchanged.</p><button type="button" className="button warning-button" onClick={handleResetCatalog} disabled={isIndexing}>{isIndexing ? 'Wait for indexing to finish' : 'Clear catalog and re-index this folder'}</button></div></div>}
            {statusMsg && <div className="notice success-notice" role="status" aria-live="polite" aria-atomic="true"><Icon name="check" /><span>{statusMsg}</span></div>}
            {actionNotice && <div className="notice success-notice action-notice action-result-notice" role="status"><Icon name="check" /><span>{actionNotice}</span></div>}
            {indexErrors > 0 && <div className="notice warning-notice compact-notice" role="status"><Icon name="alert" /><span>{indexErrors} file{indexErrors === 1 ? '' : 's'} had indexing errors. The remaining files are available.</span></div>}
            <div className="results-heading"><div><h2>Results</h2>{results.length > 0 && <span className="result-count">{results.length} found</span>}</div>{query && results.length > 0 && <span className="query-context">for “{query.trim()}”</span>}</div>
            {resultsAreStale && results.length > 0 && <div className="stale-notice" role="status"><Icon name="alert" size={16} /><span>The catalog changed after this search. Search again to refresh.</span></div>}
            {results.length === 0 ? (
              <div className="empty-state">
                <div className="empty-symbol"><Icon name={query ? 'search' : indexedCount > 0 ? 'library' : 'folder'} size={22} /></div>
                <h3>{searchFailed ? 'Search could not be completed' : query && statusMsg?.startsWith('No matches') ? 'No matches in this catalog' : indexedCount > 0 ? 'Your library is ready' : 'Start with a folder'}</h3>
                <p>{searchFailed ? 'Check the local service connection and try searching again.' : query && statusMsg?.startsWith('No matches') ? 'Try different words or index another folder to expand your local library.' : indexedCount > 0 ? 'Describe the file you are looking for in the search box above.' : 'Choose a folder to build a searchable local catalog. Your files stay where they are.'}</p>
              </div>
            ) : (
              <div className="results-list" role="list" aria-label="Search results">
                {results.map((file) => <div role="listitem" key={file.path}><ResultRow file={file} selected={selectedPath === file.path} explaining={explainingPaths.has(file.path)} explainDisabled={explainingPaths.size > 0} onSelect={(event) => { previousFocus.current = event.currentTarget; setSelectedPath(file.path); setActionError(null); setActionNotice(null); }} onExplain={(event) => { previousFocus.current = event.currentTarget; setSelectedPath(file.path); handleExplain(file.path); }} onOpen={(event) => { previousFocus.current = event.currentTarget; setSelectedPath(file.path); handleOpen(file.path); }} /></div>)}
              </div>
            )}
            <footer className="workspace-footer"><Icon name="pin" size={14} /><span>Files stay in their folders</span><span className="footer-separator">·</span><span>Catalog, indexing, and search stay on this Mac</span></footer>
          </section>
          <div className={`detail-backdrop${detailOpen ? ' visible' : ''}`} onClick={handleDetailClose} aria-hidden="true" />
          <div className={`detail-shell${detailOpen ? ' open' : ''}`} aria-hidden={isCompactLayout && !detailOpen}>
            <FileDetailPanel file={selectedFile} explanation={selectedFile ? explanations[selectedFile.path] : null} explaining={Boolean(selectedFile && explainingPaths.has(selectedFile.path))} onExplain={() => selectedFile && handleExplain(selectedFile.path)} onOpen={() => selectedFile && handleOpen(selectedFile.path)} onTrash={() => selectedFile && handleTrash(selectedFile.path)} onClose={handleDetailClose} error={actionError} notice={null} isDialog={isCompactLayout && detailOpen} closeButtonRef={closeButtonRef} />
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
