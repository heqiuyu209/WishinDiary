import { expect, test } from '@playwright/test';
import { registerAndLogin, uniqueUsername } from './helpers';

test('生活档案区分未知与明确没有，并显示结构化症状提示', async ({ page }) => {
  await registerAndLogin(page, uniqueUsername());
  await expect(page.getByRole('button', { name: '保存档案', exact: true })).toBeEnabled();
  await page.getByLabel('压力（今日自评，与心情分开记录）').selectOption({ label: '重' });
  await page.getByLabel('头痛').selectOption({ label: '重' });
  await page.getByLabel('今日是否运动').selectOption({ label: '没有' });
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().endsWith('/api/v1/daily_log') && res.request().method() === 'POST',
    ),
    page.getByRole('button', { name: '保存档案', exact: true }).click(),
  ]);
  expect(response.status()).toBe(200);
  const payload = response.request().postDataJSON();
  expect(payload).toMatchObject({
    stress_level: 3,
    is_exercise: false,
    exercise_minutes: 0,
    is_intercourse: null,
    sleep_duration_minutes: null,
    symptom_levels: { headache: 3, fatigue: null },
  });
  expect((await response.json()).advice_source).toBe('rule_based');
  await expect(page.getByRole('list', { name: '记录提示' })).toContainText('头痛');
  await expect(page.getByRole('list', { name: '记录提示' })).not.toContainText('状态平稳');
  const origin = new URL(response.url()).origin;
  const stored = await page.request.get(`${origin}/api/v1/daily_log?date=${payload.log_date}`);
  expect((await stored.json()).log).toMatchObject({
    stress_level: 3,
    is_exercise: false,
    sleep_duration_minutes: null,
    recording_version: 1,
  });
});
