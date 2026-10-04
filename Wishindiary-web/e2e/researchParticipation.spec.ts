import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername } from './helpers';

test('研究授权独立于邮箱、背景区分未知与否定、撤回保留记录', async ({ page }) => {
  await registerAndLogin(page, uniqueUsername());
  await page.goto('/settings');
  const research = page.getByRole('region', { name: '自愿研究与医学背景' });
  await expect(research).toContainText('未参加研究');
  const join = research.getByRole('button', { name: '自愿参加研究', exact: true });
  await expect(join).toBeDisabled();
  await research.getByLabel('我确认已满 18 岁').check();
  await research.getByLabel('我已阅读以上说明，自愿授权参加').check();
  await join.click();
  await expect(research).toContainText('已自愿参加');
  await research.getByLabel('目前是否妊娠').selectOption({ label: '否' });
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) =>
        res.url().endsWith('/api/v1/research/background') && res.request().method() === 'PUT',
    ),
    research.getByRole('button', { name: '保存可选背景', exact: true }).click(),
  ]);
  expect(response.status()).toBe(200);
  expect(response.request().postDataJSON()).toMatchObject({
    pregnancy: false,
    diagnosed_pcos: null,
  });
  await page.reload();
  await expect(research.getByLabel('目前是否妊娠')).toHaveValue('false');
  await expect(research.getByLabel('是否已被医生诊断为 PCOS').locator('option:checked')).toHaveText(
    '未填写 / 不确定',
  );
  await research.getByRole('button', { name: '撤回研究授权' }).click();
  await expect(research).toContainText('未参加研究');
  const origin = new URL(response.url()).origin;
  expect((await page.request.get(`${origin}/api/v1/admin/research`)).status()).toBe(403);
  const exported = await page.request.get(`${origin}/api/v1/user/export`);
  expect(exported.status()).toBe(200);
  expect(
    (await exported.json()).research_consent_events.map((row: { action: string }) => row.action),
  ).toEqual(['grant', 'withdraw']);
});
