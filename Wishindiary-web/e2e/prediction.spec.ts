import { expect, test } from '@playwright/test';
import { addDays, formatDate, toLocalDate } from '../src/shared/utils/date';
import { uniqueUsername, vCalendarDayLabel } from './helpers';

test('真实预测只圈出预计开始日，跨月后也不延续为五天区间', async ({ page }, testInfo) => {
  const now = new Date();
  const anchor = new Date(now.getFullYear(), now.getMonth(), 1, 12);
  await page.clock.setFixedTime(anchor);
  const username = uniqueUsername();
  const password = 'E2ePassword123!';
  const apiBase = process.env.VITE_API_BASE_URL || 'http://localhost:8000';
  const registration = await page.request.post(`${apiBase}/api/v1/auth/register`, {
    data: {
      username,
      password,
      period_start_dates: [-56, -28, 0].map((offset) => formatDate(addDays(anchor, offset))),
    },
  });
  expect(registration.ok()).toBe(true);

  await page.goto('/login');
  await page.getByPlaceholder('Username').fill(username);
  await page.locator('input[type=password]').fill(password);
  await page.getByRole('button', { name: '进入系统', exact: true }).click();
  await expect(page).toHaveURL(/\/calendar/);
  await expect(page.getByText('下次经期预计开始日:', { exact: false })).toBeVisible();
  await expect(page.getByLabel('日历标记说明')).toContainText('预计开始日');

  const response = await page.request.get(`${apiBase}/api/v1/prediction`);
  expect(response.ok()).toBe(true);
  const { prediction } = await response.json();
  const predictedStart = toLocalDate(prediction.next_period_start)!;
  // API 的持续时间字段仍保留，日历应将开始日独立展示。
  expect(prediction.next_period_end).toBe(formatDate(addDays(predictedStart, 4)));
  let visibleMonth = anchor.getFullYear() * 12 + anchor.getMonth();
  for (let offset = 0; offset < 5; offset++) {
    const date = addDays(predictedStart, offset);
    const targetMonth = date.getFullYear() * 12 + date.getMonth();
    while (visibleMonth < targetMonth) {
      await page.locator('button.vc-next').click();
      visibleMonth++;
    }
    const day = page.locator(`.vc-day.id-${formatDate(date)}:not(.is-not-in-month)`);
    await expect(
      day.getByRole('button', { name: vCalendarDayLabel(date), exact: true }),
    ).toBeVisible();
    if (offset === 0) {
      await expect(day.locator('.vc-purple .vc-highlight-bg-outline')).toHaveCount(1);
      await testInfo.attach('predicted-start-desktop', {
        body: await page.screenshot({ fullPage: true }),
        contentType: 'image/png',
      });
      const desktopViewport = page.viewportSize()!;
      await page.setViewportSize({ width: 390, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        390,
      );
      await testInfo.attach('predicted-start-mobile', {
        body: await page.screenshot({ fullPage: true }),
        contentType: 'image/png',
      });
      await page.setViewportSize(desktopViewport);
    } else {
      await expect(day.locator('.vc-purple .vc-highlight')).toHaveCount(0);
    }
  }
});
