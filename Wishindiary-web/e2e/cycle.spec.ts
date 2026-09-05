import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername, vCalendarDayLabel } from './helpers';

test('记录经期开始并结束一个周期', async ({ page }) => {
  await registerAndLogin(page, uniqueUsername());

  const startDate = new Date();
  startDate.setDate(startDate.getDate() - 1);

  // 从昨天开始，随后用今天结束，避免重复点击已选日期将值切换为空。
  await page.getByRole('button', { name: vCalendarDayLabel(startDate) }).click();
  await page.getByRole('button', { name: '标记开始' }).click();

  // 开始成功后出现系统预估/历史平均区间预览。
  await expect(page.getByText(/系统预估区间|历史平均/).first()).toBeVisible({
    timeout: 15_000,
  });

  // 选择今天作为结束日期，提交标记结束。
  await page.locator('.vc-day.is-today [role="button"]').click();
  await page.getByRole('button', { name: '标记结束' }).click();

  // 结束成功后进入已关闭区间的可清空预览。
  await expect(page.getByText('当前选中区间').first()).toBeVisible({
    timeout: 15_000,
  });
});
