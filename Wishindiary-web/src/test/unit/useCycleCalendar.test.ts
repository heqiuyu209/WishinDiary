import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, nextTick, type App } from 'vue';
import type { AxiosResponse } from 'axios';
import { useCycleCalendar } from '../../modules/calendar/composables/useCycleCalendar';
import type { StatusResponse, StatsResponse, CycleRead } from '../../types/api';

vi.mock('../../modules/dashboard/api', () => ({
  getPredictionApi: vi.fn(),
  getStatsApi: vi.fn(),
}));
vi.mock('../../modules/calendar/api', () => ({
  logStartApi: vi.fn(),
  logEndApi: vi.fn(),
  saveDailyLogApi: vi.fn(),
  getDailyLogApi: vi.fn(),
  updateDailyLogApi: vi.fn(),
  deleteDailyLogApi: vi.fn(),
  deleteCycleApi: vi.fn(),
}));

import { getPredictionApi, getStatsApi } from '../../modules/dashboard/api';
import { getDailyLogApi, logEndApi, saveDailyLogApi } from '../../modules/calendar/api';

const getStatsApiMock = vi.mocked(getStatsApi);
const getPredictionApiMock = vi.mocked(getPredictionApi);
const logEndApiMock = vi.mocked(logEndApi);
const saveDailyLogApiMock = vi.mocked(saveDailyLogApi);
const getDailyLogApiMock = vi.mocked(getDailyLogApi);

function ok<T extends StatusResponse>(data: T): Promise<AxiosResponse<T>> {
  return Promise.resolve({ data } as AxiosResponse<T>);
}

const openCycle: CycleRead = {
  cycle_id: 2,
  start_date: '2026-10-01',
  end_date: null,
  cycle_length: null,
  bleeding_days: null,
};
const closedCycle: CycleRead = {
  cycle_id: 1,
  start_date: '2020-01-01',
  end_date: '2020-01-05',
  cycle_length: 30,
  bleeding_days: 5,
};

const stats: StatsResponse = {
  status: 'success',
  cycles: [closedCycle, openCycle],
  recent_logs: [],
};

function withSetup<T>(composable: () => T): { app: App; result: T | undefined } {
  let result: T | undefined;
  const app = createApp({
    setup() {
      result = composable();
      return () => null;
    },
  });
  app.mount(document.createElement('div'));
  return { app, result };
}

async function makeCalendar() {
  getPredictionApiMock.mockResolvedValue(ok({ status: 'success', prediction: null }) as never);
  getStatsApiMock.mockResolvedValue(ok(stats) as never);
  const { app, result } = withSetup(() => useCycleCalendar());
  await new Promise((r) => setTimeout(r, 0));
  await nextTick();
  return { app, calendar: result! };
}

describe('useCycleCalendar', () => {
  beforeEach(() => {
    getStatsApiMock.mockReset();
    getPredictionApiMock.mockReset();
    logEndApiMock.mockReset();
    saveDailyLogApiMock.mockReset();
    getDailyLogApiMock.mockReset();
  });

  it('从 stats 识别最新开放周期并计算历史平均经期天数', async () => {
    const { app, calendar } = await makeCalendar();

    expect(calendar.openCycle.value?.cycle_id).toBe(2);
    expect(calendar.selectedClosedCycle.value).toBeNull();
    expect(calendar.estimatedBleedingDays.value).toBe(5);
    expect(calendar.selectedPreviewMode.value).toBe('default');
    expect(calendar.canConfirmEnd.value).toBe(false);
    expect(calendar.selectedRangeText.value).toBeTruthy();

    app.unmount();
  });

  it('选中日期落在已关闭周期内时定位该周期', async () => {
    const { app, calendar } = await makeCalendar();

    calendar.selectedDate.value = new Date(2020, 0, 3); // 2020-01-03
    await nextTick();

    expect(calendar.selectedClosedCycle.value?.cycle_id).toBe(1);
    expect(calendar.selectedPreviewMode.value).toBe('default');

    app.unmount();
  });

  it('开放周期内 markEnd 直接提交 end_date 与 cycle_id', async () => {
    logEndApiMock.mockResolvedValue(ok({ status: 'success', message: 'ok' }) as never);
    const { app, calendar } = await makeCalendar();

    calendar.selectedDate.value = new Date(2026, 9, 5); // 2026-10-05
    await nextTick();
    expect(calendar.canConfirmEnd.value).toBe(true);

    await calendar.markEnd();
    expect(logEndApiMock).toHaveBeenCalledTimes(1);
    expect(logEndApiMock.mock.calls[0]?.[0]).toMatchObject({
      end_date: '2026-10-05',
      cycle_id: 2,
    });

    app.unmount();
  });

  it('saveLog 请求体携带新增自记录字段', async () => {
    saveDailyLogApiMock.mockResolvedValue(
      ok({ status: 'success', message: 'ok', ai_health_advice: ['ok'] }) as never,
    );
    const { app, calendar } = await makeCalendar();

    calendar.dailyForm.sleep_duration_minutes = 480;
    calendar.dailyForm.sleep_quality = 3;
    calendar.dailyForm.is_late_night = true;
    calendar.dailyForm.is_medication = true;
    calendar.dailyForm.medication_note = '布洛芬';
    calendar.dailyForm.symptom_levels.headache = 2;

    await calendar.saveLog();
    expect(saveDailyLogApiMock).toHaveBeenCalledTimes(1);
    expect(saveDailyLogApiMock.mock.calls[0]?.[0]).toMatchObject({
      sleep_duration_minutes: 480,
      sleep_quality: 3,
      is_late_night: true,
      is_medication: true,
      medication_note: '布洛芬',
      symptom_levels: { headache: 2, bloat: 0, breast_tenderness: 0, fatigue: 0 },
    });

    app.unmount();
  });

  it('切换日期回显已有记录的新字段', async () => {
    getDailyLogApiMock.mockResolvedValue(
      ok({
        status: 'success',
        log: {
          log_date: '2026-08-20',
          mood_level: 1,
          cramps_severity: 2,
          is_exercise: true,
          is_intercourse: false,
          exercise_type: '',
          exercise_minutes: 30,
          diet_tag: '',
          journal_text: '压力很大',
          sleep_duration_minutes: 420,
          sleep_quality: 2,
          is_late_night: true,
          is_medication: false,
          medication_note: '',
          symptom_levels: { headache: 1, bloat: 0, breast_tenderness: 0, fatigue: 3 },
        },
      }) as never,
    );
    const { app, calendar } = await makeCalendar();

    calendar.selectedDate.value = new Date(2026, 7, 20); // 2026-08-20
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(getDailyLogApiMock).toHaveBeenCalled();
    expect(calendar.dailyForm.sleep_duration_minutes).toBe(420);
    expect(calendar.dailyForm.sleep_quality).toBe(2);
    expect(calendar.dailyForm.is_late_night).toBe(true);
    expect(calendar.dailyForm.symptom_levels).toEqual({
      headache: 1,
      bloat: 0,
      breast_tenderness: 0,
      fatigue: 3,
    });

    app.unmount();
  });

  it('该日无记录(404)时表单重置为默认值', async () => {
    getDailyLogApiMock.mockRejectedValue({ response: { status: 404 } });
    const { app, calendar } = await makeCalendar();

    calendar.dailyForm.medication_note = '残留值';
    calendar.dailyForm.symptom_levels.headache = 3;

    calendar.selectedDate.value = new Date(2026, 7, 21); // 2026-08-21
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));
    await nextTick();

    expect(calendar.dailyForm.medication_note).toBe('');
    expect(calendar.dailyForm.is_medication).toBe(false);
    expect(calendar.dailyForm.symptom_levels).toEqual({
      headache: 0,
      bloat: 0,
      breast_tenderness: 0,
      fatigue: 0,
    });

    app.unmount();
  });
});
