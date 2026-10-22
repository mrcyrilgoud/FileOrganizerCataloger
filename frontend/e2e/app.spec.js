import { expect, test } from '@playwright/test';

const result = {
  path: '/tmp/project-plan.txt',
  filename: 'project-plan.txt',
  score: 0.91,
  mime: 'text/plain',
  size: 12,
  snippet: 'project plan',
  reasons: 'Matched indexed excerpt',
};

test('indexes, searches, announces progress, and marks results stale after overlapping work', async ({ page }) => {
  let nextJob = 0;
  const pollCounts = new Map();
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/index' && route.request().method() === 'POST') {
      nextJob += 1;
      const jobId = `job-${nextJob}`;
      pollCounts.set(jobId, 0);
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: jobId, status: 'running', stage: 'scanning', completed: 0, total: null }),
      });
      return;
    }
    if (pathname.startsWith('/jobs/job-') && route.request().method() === 'GET') {
      const jobId = pathname.split('/').at(-1);
      const polls = (pollCounts.get(jobId) || 0) + 1;
      pollCounts.set(jobId, polls);
      if (polls < 4) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ job_id: jobId, status: 'running', stage: 'embedding', completed: 1, total: 3 }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          job_id: jobId,
          status: 'completed',
          stage: 'completed',
          result: { indexed: 1, updated: 0, removed: 0, skipped: 0, total_in_store: 1, error_count: 0 },
        }),
      });
      return;
    }
    if (pathname === '/search' && route.request().method() === 'POST') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ count: 1, results: [result] }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' });
  });

  await page.goto('/');
  const folder = page.getByLabel('Folder to index');
  const query = page.getByLabel('Search query');
  await expect(folder).toHaveCount(1);
  await expect(query).toHaveCount(1);
  await folder.fill('/tmp/demo');
  await page.getByRole('button', { name: 'Index' }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Embedding 1 of 3 files' })).toBeVisible();
  await expect(page.getByText('Indexed 1 new, updated 0, removed 0 stale, skipped 0. Store total: 1.')).toBeVisible();

  await query.fill('project plan');
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByText('project-plan.txt', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Index' }).click();
  await expect(page.getByRole('button', { name: 'Indexing…' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Search' })).toBeEnabled();
  await query.fill('latest plans');
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByText('Found 1 result(s).')).toBeVisible();
  await expect(page.getByText('These results are from before the latest indexing run. Search again to refresh them.')).toBeVisible();

  await page.keyboard.press('Tab');
  const hasVisibleFocus = await page.evaluate(() => (
    document.activeElement.matches(':focus-visible')
      && getComputedStyle(document.activeElement).outlineStyle === 'solid'
  ));
  expect(hasVisibleFocus).toBe(true);
});

test('offers a safe catalog reset after an embedding compatibility conflict', async ({ page }) => {
  let resetJobStarted = false;
  await page.route('http://localhost:8000/**', async (route) => {
    const { pathname } = new URL(route.request().url());
    if (pathname === '/search') {
      await route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'The index contains legacy embeddings without a verified model profile. Clear the catalog and re-index folders to continue.' }),
      });
      return;
    }
    if (pathname === '/index/reset') {
      await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ status: 'cleared', removed: 2, files_deleted_from_disk: false }) });
      return;
    }
    if (pathname === '/index') {
      resetJobStarted = true;
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify({ job_id: 'reset-job', status: 'completed', stage: 'completed', result: { indexed: 1, updated: 0, removed: 0, skipped: 0, total_in_store: 1, error_count: 0 } }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ job_id: 'reset-job', status: 'completed', result: { indexed: 1, updated: 0, removed: 0, skipped: 0, total_in_store: 1, error_count: 0 } }),
    });
  });
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto('/');
  await page.getByLabel('Folder to index').fill('/tmp/demo');
  await page.getByLabel('Search query').fill('old files');
  await page.getByRole('button', { name: 'Search' }).click();
  await expect(page.getByRole('alert')).toContainText('legacy embeddings');
  await page.getByRole('button', { name: 'Clear catalog and re-index selected folder' }).click();
  await expect(page.getByText('Indexed 1 new, updated 0, removed 0 stale, skipped 0. Store total: 1.')).toBeVisible();
  expect(resetJobStarted).toBe(true);
});
