import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername, vCalendarDayLabel } from './helpers';

const instant = new Date('2026-10-06T16:30:00Z');

test.describe('经期结束后的核对', () => {
  test.use({ timezoneId: 'Asia/Shanghai' });

  test('已记录结束日的周期仍可在第 7/14/21 天提交尚未开始确认', async ({ page }) => {
    await page.clock.setFixedTime(instant);
    const settingsResponse = page.waitForResponse((response) =>
      response.url().endsWith('/api/v1/notifications/settings'),
    );
    await registerAndLogin(page, uniqueUsername());
    const origin = new URL((await settingsResponse).url()).origin;
    expect(
      (
        await page.request.post(`${origin}/api/v1/log_start`, {
          data: { start_date: '2026-09-01' },
        })
      ).status(),
    ).toBe(200);
    expect(
      (
        await page.request.post(`${origin}/api/v1/log_end`, {
          data: { end_date: '2026-09-05' },
        })
      ).status(),
    ).toBe(200);
    await page.reload();
    await expect(page.getByText('日期按账户时区 Asia/Shanghai 计算')).toBeVisible();
    await page.locator('button.vc-prev').click();
    for (const elapsed of [7, 14, 21]) {
      const date = new Date(2026, 8, 1 + elapsed);
      const dateText = `2026-09-${String(1 + elapsed).padStart(2, '0')}`;
      await page
        .locator('.vc-day:not(.is-not-in-month)')
        .getByRole('button', {
          name: vCalendarDayLabel(date),
          exact: true,
        })
        .click();
      const confirm = page.getByRole('button', { name: '截至所选日期，尚未开始下次经期' });
      await expect(confirm).toBeEnabled();
      await expect(page.getByRole('button', { name: '标记结束' })).toBeDisabled();
      await expect(page.getByRole('button', { name: '清空选中区间' })).toHaveCount(0);
      const [response] = await Promise.all([
        page.waitForResponse(
          (res) => res.url().endsWith('/tracking') && res.request().method() === 'POST',
        ),
        confirm.click(),
      ]);
      expect(response.status()).toBe(200);
      expect(response.request().postDataJSON()).toEqual({ kind: 'no_onset', as_of_date: dateText });
      await expect(
        page.getByText(`最近核对：截至确认日尚未开始下次经期（${dateText}）`),
      ).toBeVisible();
    }
  });
});

for (const scenario of [
  { device: 'Asia/Shanghai', account: 'America/Los_Angeles', today: '2026-10-06', future: 7 },
  { device: 'America/Los_Angeles', account: 'Asia/Shanghai', today: '2026-10-07', future: 8 },
]) {
  test.describe(`设备 ${scenario.device}，账户 ${scenario.account}`, () => {
    test.use({ timezoneId: scenario.device });

    test('默认日期、保存与未来日期禁用都遵循账户时区', async ({ page }) => {
      await page.clock.setFixedTime(instant);
      const settingsResponse = page.waitForResponse((response) =>
        response.url().endsWith('/api/v1/notifications/settings'),
      );
      await registerAndLogin(page, uniqueUsername());
      const origin = new URL((await settingsResponse).url()).origin;
      expect(
        (
          await page.request.put(`${origin}/api/v1/notifications/settings`, {
            data: { enabled: false, lead_days: 2, timezone: scenario.account },
          })
        ).status(),
      ).toBe(200);
      await page.reload();
      await expect(page.getByText(`日期按账户时区 ${scenario.account} 计算`)).toBeVisible();
      await expect(page.getByText('当前选中日期').locator('..')).toContainText(scenario.today);
      const save = page.getByRole('button', { name: '保存档案' });
      await expect(save).toBeEnabled();
      const [response] = await Promise.all([
        page.waitForResponse(
          (res) => res.url().endsWith('/daily_log') && res.request().method() === 'POST',
        ),
        save.click(),
      ]);
      expect(response.status()).toBe(200);
      expect(response.request().postDataJSON()).toMatchObject({ log_date: scenario.today });
      await page
        .locator('.vc-day:not(.is-not-in-month)')
        .getByRole('button', {
          name: vCalendarDayLabel(new Date(2026, 9, scenario.future)),
          exact: true,
        })
        .click();
      await expect(save).toBeDisabled();
      await expect(page.getByRole('button', { name: '标记开始' })).toBeDisabled();
    });
  });
}
