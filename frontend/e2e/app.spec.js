import { expect, test } from '@playwright/test';

const results = [
  {
    path: '/tmp/project-plan.txt', filename: 'project-plan.txt', score: 0.91,
    mime: 'text/plain', size: 1200, snippet: 'Project plan with milestones and owners.',
    reasons: 'Matched indexed excerpt',
  },
  {
    path: '/tmp/notes/launch-notes.md', filename: 'launch-notes.md', score: 0.84,
    mime: 'text/markdown', size: 4096, snippet: 'Launch checklist, rollout, and go-live notes.',
    reasons: 'Related to rollout terminology',
  },
];

const json = (data, status = 200) => ({ status, contentType: 'application/json', body: JSON.stringify(data) });

test('first run is search-first, folder aware, and submits a trimmed local query', async ({ page }) => {
  let searchPayload;
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 0 }));
    if (pathname === '/search') {
      searchPayload = route.request().postDataJSON();
      return route.fulfill(json({ query: searchPayload.query, count: 0, results: [] }));
    }
    return route.fulfill(json({}));
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Find files by meaning' })).toBeVisible();
  await expect(page.getByLabel('Folder to index')).toBeEditable();
  const query = page.getByLabel('Search query');
  const submit = page.getByRole('button', { name: 'Search' });
  await expect(query).toBeEditable();
  await expect(submit).toBeDisabled();
  await query.fill('  signed lease  ');
  await expect(submit).toBeEnabled();
  await query.press('Enter');
  await expect(page.getByRole('heading', { name: 'No matches in this catalog' })).toBeVisible();
  expect(searchPayload).toEqual({ query: 'signed lease', limit: 20 });
});

test('search errors explain the service problem instead of showing catalog setup guidance', async ({ page }) => {
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 4 }));
    if (pathname === '/search') return route.fulfill(json({ detail: 'Local service unavailable' }, 503));
    return route.fulfill(json({}));
  });
  await page.goto('/');
  await page.getByLabel('Search query').fill('budget draft');
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByRole('heading', { name: 'Search could not be completed' })).toBeVisible();
  await expect(page.getByText('Check the local service connection and try searching again.')).toBeVisible();
  await expect(page.getByText('Start with a folder')).toHaveCount(0);
});

test('dismissing the native folder picker is a neutral no-op', async ({ page }) => {
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 0 }));
    if (pathname === '/browse') return route.fulfill(json({ path: '' }));
    return route.fulfill(json({}));
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Choose folder' }).click();
  await expect(page.getByLabel('Folder to index')).toHaveValue('');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('indexes with staged progress while search stays available and stale results can refresh', async ({ page }) => {
  let nextJob = 0;
  let completeJob = false;
  const pollCounts = new Map();
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 5 }));
    if (pathname === '/index' && route.request().method() === 'POST') {
      nextJob += 1;
      const jobId = `job-${nextJob}`;
      pollCounts.set(jobId, 0);
      return route.fulfill(json({ job_id: jobId, status: 'running', stage: 'scanning', completed: 0, total: null }, 202));
    }
    if (pathname.startsWith('/jobs/job-') && route.request().method() === 'GET') {
      const jobId = pathname.split('/').at(-1);
      const polls = (pollCounts.get(jobId) || 0) + 1;
      pollCounts.set(jobId, polls);
      if (!completeJob) return route.fulfill(json({ job_id: jobId, status: 'running', stage: 'embedding', completed: Math.min(3, polls), total: 3 }));
      return route.fulfill(json({ job_id: jobId, status: 'completed', stage: 'completed', result: { indexed: 1, updated: 0, removed: 0, skipped: 0, total_in_store: 6, error_count: 0 } }));
    }
    if (pathname === '/search' && route.request().method() === 'POST') return route.fulfill(json({ count: 2, results }));
    return route.fulfill(json({}));
  });

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await page.getByLabel('Folder to index').fill('/Users/demo/Documents');
  await expect(page.locator('.topbar-status')).toContainText('/Users/demo/Documents');
  await page.getByRole('button', { name: 'Index folder' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Embedding 1 of 3 files' })).toBeVisible();
  await expect(page.getByLabel('Folder to index')).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Choose folder' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
  await page.getByLabel('Search query').fill('project plan');
  await expect(page.getByRole('button', { name: 'Search' })).toBeEnabled();
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByRole('button', { name: 'Select project-plan.txt' })).toBeVisible();
  completeJob = true;
  await expect(page.getByText('Indexed 1 new · updated 0 · skipped 0 · removed 0 stale. Catalog total: 6.')).toBeVisible();
  await expect(page.getByText('The catalog changed after this search. Search again to refresh.')).toBeVisible();

  const grid = await page.locator('.workspace-grid').boundingBox();
  const detail = page.getByRole('complementary', { name: 'File details' });
  await expect(detail).toBeVisible();
  const main = await page.locator('.results-workspace').boundingBox();
  const panel = await page.locator('.detail-shell').boundingBox();
  expect(main.x + main.width).toBeLessThanOrEqual(panel.x + 1);
  expect(grid).toBeTruthy();
});

test('result selection shows grounded details, Explain handles success and failure, and Open reports inline errors', async ({ page }) => {
  let explainFails = false;
  let openFails = false;
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 2 }));
    if (pathname === '/search') return route.fulfill(json({ count: 2, results }));
    if (pathname === '/explain') return route.fulfill(explainFails ? json({ detail: 'Ollama is not running' }, 503) : json({ explanation: 'This file contains the milestones and owners named in your query.' }));
    if (pathname === '/open') return route.fulfill(openFails ? json({ detail: 'Failed to open file' }, 500) : json({ status: 'opened' }));
    return route.fulfill(json({}));
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await page.getByLabel('Search query').fill('project plan');
  await page.getByRole('button', { name: 'Search' }).click();
  await page.getByRole('button', { name: 'Select launch-notes.md' }).click();
  const detail = page.getByRole('complementary', { name: 'File details for launch-notes.md' });
  await expect(detail.getByText('/tmp/notes/launch-notes.md')).toBeVisible();
  await expect(detail.getByText('Launch checklist, rollout, and go-live notes.')).toBeVisible();
  await expect(detail.getByText('Match 0.84')).toBeVisible();
  await expect(detail.getByText('Related to rollout terminology')).toBeVisible();
  await expect(detail.getByText('Generated locally by Ollama from file metadata and a short excerpt.')).toBeVisible();
  await detail.getByRole('button', { name: 'Explain match' }).click();
  await expect(detail.getByText('This file contains the milestones and owners named in your query.')).toBeVisible();

  explainFails = true;
  await detail.getByRole('button', { name: 'Explain again' }).click();
  await expect(detail.getByText('Explain unavailable: Ollama is not running')).toBeVisible();
  await expect(detail.getByRole('button', { name: 'Try again' })).toBeVisible();

  openFails = true;
  await detail.getByRole('button', { name: 'Open file' }).click();
  await expect(detail.getByRole('alert')).toContainText('Could not open launch-notes.md');
});

test('Trash confirms the named file, removes success, and reports partial cleanup accurately', async ({ page }) => {
  let deleteMode = 'success';
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 2 }));
    if (pathname === '/search') return route.fulfill(json({ count: 2, results }));
    if (pathname === '/delete') {
      if (deleteMode === 'partial') return route.fulfill(json({ detail: 'File moved to Trash, but index cleanup failed; search results may be stale' }, 500));
      if (deleteMode === 'failure') return route.fulfill(json({ detail: 'Trash permission denied' }, 400));
      return route.fulfill(json({ status: 'deleted' }));
    }
    return route.fulfill(json({}));
  });
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/');
  await page.getByLabel('Search query').fill('launch');
  await page.getByRole('button', { name: 'Search' }).click();
  await page.getByRole('button', { name: 'Select project-plan.txt' }).click();
  page.once('dialog', async (dialog) => {
    expect(dialog.type()).toBe('confirm');
    expect(dialog.message()).toContain('project-plan.txt');
    await dialog.accept();
  });
  await page.getByRole('button', { name: 'Move to Trash…' }).click();
  await expect(page.getByRole('button', { name: 'Select project-plan.txt' })).toHaveCount(0);
  await expect(page.getByRole('complementary', { name: 'File details for launch-notes.md' })).toBeVisible();
  await expect(page.locator('.action-result-notice')).toContainText('project-plan.txt moved to Trash');
  await expect(page.locator('.detail-panel .action-notice')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Select launch-notes.md' })).toBeFocused();

  deleteMode = 'failure';
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Move to Trash…' }).click();
  await expect(page.locator('.action-error')).toContainText('Trash permission denied');
  await expect(page.getByRole('button', { name: 'Select launch-notes.md' })).toBeVisible();

  deleteMode = 'partial';
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Move to Trash…' }).click();
  await expect(page.locator('.action-notice')).toContainText('was moved to Trash, but the catalog cleanup failed');
  await expect(page.getByRole('button', { name: 'Select launch-notes.md' })).toHaveCount(0);
});

test('cancelled indexing confirms no save and preserves stale state that existed before indexing', async ({ page }) => {
  let cancelled = false;
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 2 }));
    if (pathname === '/search') return route.fulfill(json({ count: 2, results }));
    if (pathname === '/delete') return route.fulfill(json({ detail: 'File moved to Trash, but index cleanup failed; search results may be stale' }, 500));
    if (pathname === '/index') return route.fulfill(json({ job_id: 'cancel-job', status: 'running', stage: 'scanning', completed: 0, total: null }, 202));
    if (pathname === '/jobs/cancel-job') return route.fulfill(cancelled
      ? json({ job_id: 'cancel-job', status: 'cancelled', stage: 'cancelled' })
      : json({ job_id: 'cancel-job', status: 'running', stage: 'embedding', completed: 2, total: 8 }));
    if (pathname === '/jobs/cancel-job/cancel') { cancelled = true; return route.fulfill(json({ job_id: 'cancel-job', status: 'cancelling' })); }
    return route.fulfill(json({}));
  });
  await page.goto('/');
  await page.getByLabel('Search query').fill('plan');
  await page.getByRole('button', { name: 'Search' }).click();
  await page.getByRole('button', { name: 'Select project-plan.txt' }).click();
  page.once('dialog', (dialog) => dialog.accept());
  await page.getByRole('button', { name: 'Move to Trash…' }).click();
  await expect(page.getByText('The catalog changed after this search. Search again to refresh.')).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByLabel('Folder to index').fill('/tmp/demo');
  await page.getByRole('button', { name: 'Index folder' }).click();
  await expect(page.getByText('The catalog changed after this search. Search again to refresh.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel' })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel' }).click();
  await expect(page.getByText('Indexing cancelled. No catalog changes were saved.')).toBeVisible();
  await expect(page.getByText('The catalog changed after this search. Search again to refresh.')).toBeVisible();
});

test('saving phase prevents cancellation and defers catalog reset until indexing finishes', async ({ page }) => {
  let finishJob = false;
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 2 }));
    if (pathname === '/index') return route.fulfill(json({ job_id: 'saving-job', status: 'running', stage: 'scanning', completed: 0, total: null }, 202));
    if (pathname === '/jobs/saving-job') return route.fulfill(finishJob
      ? json({ job_id: 'saving-job', status: 'completed', stage: 'completed', result: { indexed: 0, updated: 1, removed: 0, skipped: 0, total_in_store: 2, error_count: 0 } })
      : json({ job_id: 'saving-job', status: 'running', stage: 'saving', completed: 2, total: 2 }));
    if (pathname === '/search') return route.fulfill(json({ detail: 'The index contains legacy embeddings without a verified model profile.' }, 409));
    if (pathname === '/index/reset') return route.fulfill(json({ status: 'cleared', removed: 2, files_deleted_from_disk: false }));
    return route.fulfill(json({}));
  });
  await page.goto('/');
  await page.getByLabel('Folder to index').fill('/tmp/demo');
  await page.getByRole('button', { name: 'Index folder' }).click();
  await expect(page.getByText('Saving catalog changes…')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Cancel' })).toHaveCount(0);
  await page.getByLabel('Search query').fill('old files');
  await page.getByRole('button', { name: 'Search' }).click();
  const reset = page.getByRole('button', { name: 'Wait for indexing to finish' });
  await expect(reset).toBeDisabled();
  finishJob = true;
  await expect(page.getByText(/Catalog total: 2\./)).toBeVisible();
  await expect(page.getByRole('button', { name: 'Clear catalog and re-index this folder' })).toBeEnabled();
});

test('detail panel adapts at tablet and mobile widths without horizontal overflow', async ({ page }) => {
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 2 }));
    if (pathname === '/search') return route.fulfill(json({ count: 2, results }));
    return route.fulfill(json({}));
  });
  await page.goto('/');
  await page.getByLabel('Search query').fill('project');
  await page.getByRole('button', { name: 'Search' }).click();
  await page.getByRole('button', { name: 'Select project-plan.txt' }).click();
  await page.setViewportSize({ width: 1100, height: 800 });
  await expect(page.locator('.detail-shell')).toHaveCSS('position', 'fixed');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('dialog', { name: 'File details for project-plan.txt' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Close file details' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Close file details' })).toBeFocused();
  await expect(page.locator('.results-workspace')).toHaveAttribute('inert', '');
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Explain match' })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(page.getByRole('button', { name: 'Close file details' })).toBeFocused();
  const pageWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(pageWidth).toBeLessThanOrEqual(390);
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog', { name: 'File details for project-plan.txt' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Select project-plan.txt' })).toBeFocused();
  await page.setViewportSize({ width: 320, height: 700 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
});

test('offers a safe catalog reset after an embedding compatibility conflict', async ({ page }) => {
  let resetJobStarted = false;
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/health') return route.fulfill(json({ status: 'ok', indexed_files: 2 }));
    if (pathname === '/search') return route.fulfill(json({ detail: 'The index contains legacy embeddings without a verified model profile. Clear the catalog and re-index folders to continue.' }, 409));
    if (pathname === '/index/reset') return route.fulfill(json({ status: 'cleared', removed: 2, files_deleted_from_disk: false }));
    if (pathname === '/index') {
      resetJobStarted = true;
      return route.fulfill(json({ job_id: 'reset-job', status: 'completed', stage: 'completed', result: { indexed: 1, updated: 0, removed: 0, skipped: 0, total_in_store: 1, error_count: 0 } }, 202));
    }
    return route.fulfill(json({ job_id: 'reset-job', status: 'completed', result: { indexed: 1, updated: 0, removed: 0, skipped: 0, total_in_store: 1, error_count: 0 } }));
  });
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto('/');
  await page.getByLabel('Folder to index').fill('/tmp/demo');
  await page.getByLabel('Search query').fill('old files');
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByRole('alert')).toContainText('legacy embeddings');
  await page.getByRole('button', { name: 'Clear catalog and re-index this folder' }).click();
  await expect(page.getByText('Indexed 1 new · updated 0 · skipped 0 · removed 0 stale. Catalog total: 1.')).toBeVisible();
  expect(resetJobStarted).toBe(true);
});
