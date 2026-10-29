import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername, vCalendarDayLabel } from './helpers';
import { formatDate } from '../src/shared/utils/date';

test('切换日期加载期间禁止保存，加载完成后只保存目标日内容', async ({ page }, testInfo) => {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 1, 15, 12);
  const second = new Date(first.getFullYear(), first.getMonth(), 14, 12);
  await page.clock.setFixedTime(first);
  await registerAndLogin(page, uniqueUsername());
  const save = page.getByRole('button', { name: '保存档案并生成分析', exact: true });
  await expect(save).toBeEnabled();
  await page.locator('textarea').fill('synthetic first-day note');
  const [firstSave] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/v1/daily_log') && response.request().method() === 'POST',
    ),
    save.click(),
  ]);
  const apiOrigin = new URL(firstSave.url()).origin;
  await expect(save).toBeEnabled();

  let release!: () => void;
  let requested!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const requestStarted = new Promise<void>((resolve) => {
    requested = resolve;
  });
  const secondPath = `/api/v1/daily_log?date=${formatDate(second)}`;
  await page.route(/\/api\/v1\/daily_log\?/, async (route) => {
    if (new URL(route.request().url()).searchParams.get('date') !== formatDate(second)) {
      await route.continue();
      return;
    }
    requested();
    await gate;
    await route.continue();
  });
  const writes: Array<Record<string, unknown>> = [];
  page.on('request', (request) => {
    if (request.method() === 'POST' && request.url().endsWith('/api/v1/daily_log')) {
      writes.push(request.postDataJSON());
    }
  });
  await page
    .locator('.vc-day:not(.is-not-in-month)')
    .getByRole('button', { name: vCalendarDayLabel(second), exact: true })
    .click();
  await requestStarted;
  try {
    await expect(page.getByText('正在加载当天档案…')).toBeVisible();
    await expect(save).toBeDisabled();
    await expect(page.locator('textarea')).toBeDisabled();
    await page.screenshot({ path: testInfo.outputPath('daily-log-loading.png'), fullPage: true });
    await save.evaluate((button) => (button as HTMLButtonElement).click());
    expect(writes).toHaveLength(0);
  } finally {
    release();
  }
  await expect(save).toBeEnabled();
  await expect(page.locator('textarea')).toHaveValue('');
  await page.locator('textarea').fill('synthetic second-day note');
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().endsWith('/api/v1/daily_log') && response.request().method() === 'POST',
    ),
    save.click(),
  ]);
  expect(writes).toEqual([
    expect.objectContaining({
      log_date: formatDate(second),
      journal_text: 'synthetic second-day note',
    }),
  ]);
  const firstResponse = await page.request.get(
    `${apiOrigin}/api/v1/daily_log?date=${formatDate(first)}`,
  );
  const secondResponse = await page.request.get(`${apiOrigin}${secondPath}`);
  expect((await firstResponse.json()).log.journal_text).toBe('synthetic first-day note');
  expect((await secondResponse.json()).log.journal_text).toBe('synthetic second-day note');
});
