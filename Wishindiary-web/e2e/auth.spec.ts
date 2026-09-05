import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername } from './helpers';

test('注册新用户并登录跳转打卡页', async ({ page }) => {
  const username = uniqueUsername();
  await registerAndLogin(page, username);

  // 登录后停留在打卡页，导航与用户身份可见。
  await expect(page.getByRole('button', { name: /WishinDiary/ })).toBeVisible();
  await expect(page.getByRole('button', { name: new RegExp(username) })).toBeVisible();
  await page.reload();
  await expect(page).toHaveURL(/\/calendar/);
  await expect(page.getByRole('button', { name: new RegExp(username) })).toBeVisible();
});

test('未登录访问受保护页面被重定向到登录页', async ({ page }) => {
  await page.goto('/report');
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByPlaceholder('Username')).toBeVisible();
});
