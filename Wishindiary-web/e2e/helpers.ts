import { expect, type Page } from '@playwright/test';

const PASSWORD = 'E2ePassword123!';

/** 生成符合后端用户名校验规则（3-50 位，字母/数字/._-）的唯一用户名。 */
export function uniqueUsername(): string {
  return `e2e_${Date.now()}`;
}

/** 在浏览器地址栏可直接访问的登录页完成注册与登录，返回用户名。 */
export async function registerAndLogin(page: Page, username: string): Promise<void> {
  await page.goto('/login');

  await page.getByRole('button', { name: '没有账号？点击注册' }).click();
  await page.getByPlaceholder('Username').fill(username);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.getByRole('button', { name: '确认注册' }).click();

  // 注册成功后自动切回登录态，表单内容保留，直接登录。
  await expect(page.getByText('注册成功，请直接登录！')).toBeVisible({ timeout: 15_000 });
  await page.getByRole('button', { name: '进入系统' }).click();

  await expect(page).toHaveURL(/\/calendar/, { timeout: 15_000 });
}

/** 生成 v-calendar 日期格按钮的 aria-label（date-fns 格式 "Wed Sep 2 2026"）。 */
export function vCalendarDayLabel(d: Date): string {
  const wd = d.toLocaleDateString('en-US', { weekday: 'short' });
  const mon = d.toLocaleDateString('en-US', { month: 'short' });
  return `${wd} ${mon} ${d.getDate()} ${d.getFullYear()}`;
}
