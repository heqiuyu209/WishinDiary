import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, nextTick, type App } from 'vue';
import type { AxiosResponse } from 'axios';
import {
  useCycleCalendar,
  buildDailyLogPayload,
  createDefaultDailyForm,
} from '../../modules/calendar/composables/useCycleCalendar';
import type {
  StatusResponse,
  StatsResponse,
  CycleRead,
  PredictionResponseData,
} from '../../types/api';
import { formatDate } from '../../shared/utils/date';

vi.mock('../../modules/dashboard/api', () => ({
  getPredictionApi: vi.fn(),
  getStatsApi: vi.fn(),
}));
vi.mock('../../modules/calendar/api', () => ({
  logStartApi: vi.fn(),
  confirmTrackingApi: vi.fn(),
  logEndApi: vi.fn(),
  saveDailyLogApi: vi.fn(),
  getDailyLogApi: vi.fn(),
  updateDailyLogApi: vi.fn(),
  deleteDailyLogApi: vi.fn(),
  deleteCycleApi: vi.fn(),
}));

import { getPredictionApi, getStatsApi } from '../../modules/dashboard/api';
import {
  confirmTrackingApi,
  getDailyLogApi,
  logEndApi,
  saveDailyLogApi,
} from '../../modules/calendar/api';

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

async function makeCalendar(prediction: PredictionResponseData | null = null) {
  getPredictionApiMock.mockResolvedValue(ok({ status: 'success', prediction }) as never);
  getStatsApiMock.mockResolvedValue(ok(stats) as never);
  const { app, result } = withSetup(() => useCycleCalendar());
  await new Promise((r) => setTimeout(r, 0));
  await nextTick();
  return { app, calendar: result! };
}

const predictionFixture = (nextEnd = '2026-11-04'): PredictionResponseData => ({
  last_period_start: '2026-10-01',
  predicted_cycle_length: 30,
  next_period_start: '2026-10-31',
  next_period_end: nextEnd,
  ovulation_date: '2026-10-17',
  fertile_window_start: '2026-10-12',
  fertile_window_end: '2026-10-18',
  features_info: 'test',
  model_version: 'test',
  disclaimer: 'test',
});

describe('useCycleCalendar', () => {
  beforeEach(() => {
    getStatsApiMock.mockReset();
    getPredictionApiMock.mockReset();
    logEndApiMock.mockReset();
    saveDailyLogApiMock.mockReset();
    getDailyLogApiMock.mockReset();
    getDailyLogApiMock.mockRejectedValue({ response: { status: 404 } });
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

  it('超出模型范围时保留解释与提示，并清除预测日', async () => {
    const { app, calendar } = await makeCalendar(predictionFixture());
    getPredictionApiMock.mockResolvedValue(
      ok({
        status: 'outside_model_scope',
        prediction: null,
        message: '暂不提供日期',
        data_quality_warnings: ['核对 60 天记录'],
      }) as never,
    );
    await calendar.fetchData();
    expect(calendar.prediction.value).toBeNull();
    expect(calendar.predictionMessage.value).toBe('暂不提供日期');
    expect(calendar.predictionWarnings.value).toEqual(['核对 60 天记录']);
    expect(calendar.calendarAttributes.value.some((row) => row.key === 'pred-start')).toBe(false);
    app.unmount();
  });

  it('最新经期已结束时，不把历史漏记结束日当成开放周期', async () => {
    const { app, calendar } = await makeCalendar();
    getStatsApiMock.mockResolvedValue(
      ok({
        ...stats,
        cycles: [
          { ...closedCycle, end_date: null, bleeding_days: null },
          { ...openCycle, end_date: '2026-10-05', bleeding_days: 5 },
        ],
      }) as never,
    );
    await calendar.fetchData();
    expect(calendar.openCycle.value).toBeNull();
    expect(calendar.selectedPreviewMode.value).toBe('none');
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

  it('历史结束日未知时，补录结束准确提交历史周期 ID', async () => {
    logEndApiMock.mockResolvedValue(ok({ status: 'success', message: 'ok' }) as never);
    const { app, calendar } = await makeCalendar();
    getStatsApiMock.mockResolvedValue(
      ok({
        ...stats,
        cycles: [{ ...closedCycle, end_date: null }, openCycle],
      }) as never,
    );
    await calendar.fetchData();
    calendar.selectedDate.value = new Date(2020, 0, 5);
    await nextTick();
    expect(calendar.endTargetCycle.value?.cycle_id).toBe(1);
    expect(calendar.canConfirmEnd.value).toBe(true);
    await calendar.markEnd();
    expect(logEndApiMock.mock.calls[0]?.[0]).toEqual({ end_date: '2020-01-05', cycle_id: 1 });
    app.unmount();
  });

  it('核对操作提交所选周期、类型与日期', async () => {
    vi.mocked(confirmTrackingApi).mockResolvedValue(ok({ status: 'success' }) as never);
    const { app, calendar } = await makeCalendar();
    calendar.selectedDate.value = new Date(2020, 0, 3);
    await nextTick();
    await calendar.confirmTracking('missed_tracking');
    expect(confirmTrackingApi).toHaveBeenCalledWith(1, 'missed_tracking', '2020-01-03');
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
      symptom_levels: { headache: 2, bloat: null, breast_tenderness: null, fatigue: null },
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
    expect(calendar.dailyForm.is_medication).toBeNull();
    expect(calendar.dailyForm.symptom_levels).toEqual({
      headache: null,
      bloat: null,
      breast_tenderness: null,
      fatigue: null,
    });

    app.unmount();
  });

  it('新日期加载期间以及 watch 尚未执行时，都不能保存旧日期内容', async () => {
    const { app, calendar } = await makeCalendar();
    calendar.dailyForm.journal_text = 'synthetic previous-day note';
    calendar.message.value = 'previous-day saved';
    calendar.aiHealthAdvices.value = ['previous-day advice'];
    let complete!: (value: Awaited<ReturnType<typeof getDailyLogApi>>) => void;
    getDailyLogApiMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    calendar.selectedDate.value = new Date(2024, 0, 2);
    await calendar.saveLog();
    expect(saveDailyLogApiMock).not.toHaveBeenCalled();
    await nextTick();
    expect(calendar.dailyLogLoading.value).toBe(true);
    expect(calendar.dailyForm.journal_text).toBe('');
    expect(calendar.message.value).toBe('');
    expect(calendar.aiHealthAdvices.value).toEqual([]);
    await calendar.saveLog();
    expect(saveDailyLogApiMock).not.toHaveBeenCalled();
    complete({
      data: {
        status: 'success',
        log: {
          ...calendar.dailyForm,
          log_date: '2024-01-02',
          journal_text: 'synthetic target-day note',
        },
      },
    } as Awaited<ReturnType<typeof getDailyLogApi>>);
    await new Promise((r) => setTimeout(r, 0));
    expect(calendar.canSaveDailyLog.value).toBe(true);
    saveDailyLogApiMock.mockResolvedValue(ok({ status: 'success', message: 'ok' }) as never);
    await calendar.saveLog();
    expect(saveDailyLogApiMock).toHaveBeenCalledWith(
      expect.objectContaining({
        log_date: '2024-01-02',
        journal_text: 'synthetic target-day note',
      }),
    );
    app.unmount();
  });

  it('加载失败时阻止覆盖已有记录，重新加载后才能保存', async () => {
    const { app, calendar } = await makeCalendar();
    getDailyLogApiMock.mockRejectedValueOnce({ response: { status: 503 } });
    calendar.selectedDate.value = new Date(2024, 0, 2);
    await nextTick();
    await new Promise((r) => setTimeout(r, 0));
    expect(calendar.dailyLogLoadError.value).toBe(true);
    await calendar.saveLog();
    expect(saveDailyLogApiMock).not.toHaveBeenCalled();
    await calendar.reloadDailyLog(); // 404 表示已确认该日尚无记录。
    expect(calendar.canSaveDailyLog.value).toBe(true);
    expect(calendar.dailyLogLoadError.value).toBe(false);
    app.unmount();
  });

  it('快速切换日期时旧响应不能覆盖新日期，也不能提前解锁保存', async () => {
    const { app, calendar } = await makeCalendar();
    let finishOld!: (value: Awaited<ReturnType<typeof getDailyLogApi>>) => void;
    let finishNew!: (value: Awaited<ReturnType<typeof getDailyLogApi>>) => void;
    getDailyLogApiMock
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishOld = resolve;
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishNew = resolve;
          }),
      );
    calendar.selectedDate.value = new Date(2024, 0, 2);
    await nextTick();
    calendar.selectedDate.value = new Date(2024, 0, 3);
    await nextTick();
    finishOld({
      data: {
        status: 'success',
        log: {
          ...calendar.dailyForm,
          journal_text: 'stale synthetic note',
        },
      },
    } as Awaited<ReturnType<typeof getDailyLogApi>>);
    await new Promise((r) => setTimeout(r, 0));
    expect(calendar.dailyLogLoading.value).toBe(true);
    expect(calendar.canSaveDailyLog.value).toBe(false);
    finishNew({
      data: {
        status: 'success',
        log: {
          ...calendar.dailyForm,
          journal_text: 'current synthetic note',
        },
      },
    } as Awaited<ReturnType<typeof getDailyLogApi>>);
    await new Promise((r) => setTimeout(r, 0));
    expect(calendar.dailyForm.journal_text).toBe('current synthetic note');
    expect(calendar.canSaveDailyLog.value).toBe(true);
    app.unmount();
  });

  it.each(['2026-11-04', '2026-12-31', ''])(
    '只标记预计开始日，结束字段为 %s 时也不会涂成跨月区间',
    async (nextEnd) => {
      const { app, calendar } = await makeCalendar(predictionFixture(nextEnd));
      const predicted = calendar.calendarAttributes.value.filter(
        (attr) => attr.customData?.state === 'predicted-start',
      );
      expect(predicted).toHaveLength(1);
      const day = predicted[0]!.dates;
      expect(day).toBeInstanceOf(Date);
      expect(formatDate(day as Date)).toBe('2026-10-31');

      // 已记录的五天经期继续使用实际起止日期，不能被改成单日。
      const recorded = calendar.calendarAttributes.value.find(
        (attr) => attr.customData?.cycle_id === closedCycle.cycle_id,
      );
      expect(recorded?.dates).toEqual({ start: new Date(2020, 0, 1), end: new Date(2020, 0, 5) });
      app.unmount();
    },
  );

  it('缺少结束日期与易孕期时，远期预计开始日仍在可浏览日期内', async () => {
    const prediction = {
      ...predictionFixture(''),
      next_period_start: '2099-01-31',
      fertile_window_start: '',
      fertile_window_end: '',
    };
    const { app, calendar } = await makeCalendar(prediction);
    expect(calendar.calendarMaxDate.value.getTime()).toBeGreaterThanOrEqual(
      new Date(2099, 0, 31).getTime(),
    );
    app.unmount();
  });
});

describe('daily missing-value payload', () => {
  it('默认未知、清空输入仍发送 null；明确未运动才保存零', () => {
    const form = createDefaultDailyForm();
    expect(buildDailyLogPayload(form, '2024-01-01').is_intercourse).toBeNull();
    form.sleep_duration_minutes = '' as unknown as number;
    expect(buildDailyLogPayload(form, '2024-01-01').sleep_duration_minutes).toBeNull();
    form.is_exercise = false;
    expect(buildDailyLogPayload(form, '2024-01-01').exercise_minutes).toBe(0);
    expect(form.exercise_minutes).toBeNull();
  });
});
