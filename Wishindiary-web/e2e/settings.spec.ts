import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername } from './helpers';

test('普通用户可以设置提醒偏好，未验证邮箱不能开启提醒或进入管理端', async ({ page }) => {
  await registerAndLogin(page, uniqueUsername());
  await page.goto('/settings');
  await expect(page.getByRole('heading', { name: '邮箱与提醒设置' })).toBeVisible();
  await expect(page.getByRole('checkbox', { name: '接收邮箱提醒' })).toBeDisabled();
  await page.getByLabel('提前多久').selectOption('3');
  await page.getByLabel('按哪个时区计算日期').selectOption('UTC');
  await page.getByRole('button', { name: '保存提醒设置' }).click();
  await expect(page.getByRole('status')).toHaveText('提醒设置已保存');
  await page.reload();
  await expect(page.getByLabel('提前多久')).toHaveValue('3');
  await expect(page.getByLabel('按哪个时区计算日期')).toHaveValue('UTC');
  await page.goto('/admin/research');
  await expect(page).toHaveURL(/\/calendar/);
  await expect(page.getByRole('button', { name: '研究管理', exact: true })).toHaveCount(0);
});

test('access cookie 缺失时使用 refresh cookie 续期，再次退出后无法续期', async ({
  page,
  context,
}) => {
  await registerAndLogin(page, uniqueUsername());
  const before = (await context.cookies()).find((cookie) => cookie.name === 'refresh_token');
  expect(before).toBeDefined();
  await context.clearCookies({ name: 'access_token' });
  const renewed = page.waitForResponse((response) =>
    response.url().endsWith('/api/v1/auth/refresh'),
  );
  await page.goto('/settings');
  expect((await renewed).status()).toBe(200);
  await expect(page.getByRole('heading', { name: '邮箱与提醒设置' })).toBeVisible();
  const after = (await context.cookies()).find((cookie) => cookie.name === 'refresh_token');
  expect(after?.value).not.toEqual(before?.value);
  await page.getByRole('button', { name: '退出登录', exact: true }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto('/settings');
  await expect(page).toHaveURL(/\/login/);
});
