import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername } from './helpers';

test('登录后通过导航进入报告页', async ({ page }) => {
  await registerAndLogin(page, uniqueUsername());

  await page.getByRole('button', { name: '深度报告' }).click();
  await expect(page).toHaveURL(/\/report/);
  await expect(page.getByText('健康记录摘要')).toBeVisible();
});
