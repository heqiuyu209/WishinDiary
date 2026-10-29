import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername, vCalendarDayLabel } from './helpers';

test('跨月记录经期开始并结束一个周期', async ({ page }) => {
  const now = new Date();
  const endDate = new Date(now.getFullYear(), now.getMonth(), 1, 12);
  // 每次都覆盖月初边界；仅固定 Date，保留真实计时器和网络请求。
  await page.clock.setFixedTime(endDate);
  await registerAndLogin(page, uniqueUsername());

  const startDate = new Date(endDate);
  startDate.setDate(startDate.getDate() - 1);

  // 相邻月份的占位日不能点击，先正常翻页，再选择本月内的日期。
  await page.locator('button.vc-prev').click();
  await page
    .locator('.vc-day:not(.is-not-in-month)')
    .getByRole('button', { name: vCalendarDayLabel(startDate), exact: true })
    .click();
  await page.getByRole('button', { name: '标记开始' }).click();

  // 开始成功后显示经期持续时间预览，不与下次预计开始日混淆。
  await expect(page.getByText('预计经期持续时间', { exact: true })).toBeVisible({
    timeout: 15_000,
  });

  // 返回下个月，选择月初作为结束日期。
  await page.locator('button.vc-next').click();
  await page
    .locator('.vc-day:not(.is-not-in-month)')
    .getByRole('button', { name: vCalendarDayLabel(endDate), exact: true })
    .click();
  await page.getByRole('button', { name: '标记结束' }).click();

  // 结束成功后进入已关闭区间的可清空预览。
  await expect(page.getByText('当前选中区间').first()).toBeVisible({
    timeout: 15_000,
  });
});
