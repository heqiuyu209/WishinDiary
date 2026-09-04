import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername, vCalendarDayLabel } from './helpers';

test('记录经期开始并结束一个周期', async ({ page }) => {
  await registerAndLogin(page, uniqueUsername());

  const today = new Date();
  const todayLabel = vCalendarDayLabel(today);

  // 选中今天并标记开始。
  await page.getByRole('button', { name: todayLabel }).click();
  await page.getByRole('button', { name: '标记开始' }).click();

  // 开始成功后出现系统预估/历史平均区间预览。
  await expect(page.getByText(/系统预估区间|历史平均/).first()).toBeVisible({
    timeout: 15_000,
  });

  // 再次选中今天作为结束日期，提交标记结束。
  await page.getByRole('button', { name: todayLabel }).click();
  await page.getByRole('button', { name: '标记结束' }).click();

  // 结束成功后进入已关闭区间的可清空预览。
  await expect(page.getByText('当前选中区间').first()).toBeVisible({
    timeout: 15_000,
  });
});
