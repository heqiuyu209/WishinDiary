import { expect, test, type Page } from '@playwright/test';

const PASSWORD = 'E2ePassword123!';

/** 生成符合后端用户名校验规则（3-50 位，字母/数字/._-）的唯一用户名。 */
export function uniqueUsername(): string {
  return `e2e_${Date.now()}`;
}

/** 返回 V-Calendar 在当前 E2E 英文区域设置下使用的日期无障碍标签。 */
export function vCalendarDayLabel(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
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
  const login = async () => {
    const [response] = await Promise.all([
      page.waitForResponse(
        (res) => res.url().endsWith('/api/v1/auth/login') && res.request().method() === 'POST',
      ),
      page.getByRole('button', { name: '进入系统' }).click(),
    ]);
    return response;
  };
  let response = await login();
  if (response.status() === 429) {
    // The suite shares one localhost IP. Respect the backend's 60-second
    // window after a burst of real logins, while retaining the normal limit.
    test.setTimeout(Math.max(test.info().timeout, 120_000));
    await new Promise((resolve) => setTimeout(resolve, 61_000));
    response = await login();
  }
  expect(response.status()).toBe(200);

  await expect(page).toHaveURL(/\/calendar/, { timeout: 15_000 });
}
