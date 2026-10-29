import { computed, onMounted, reactive, ref, watch, type Ref } from 'vue';
import type { AxiosResponse } from 'axios';
import {
  confirmTrackingApi,
  deleteCycleApi,
  getDailyLogApi,
  logEndApi,
  logStartApi,
  saveDailyLogApi,
} from '../api';
import { getPredictionApi, getStatsApi } from '../../dashboard/api';
import { extractApiErrorMessage } from '../../../shared/api/httpClient';
import {
  addDays,
  formatDate,
  isAfter,
  isOnOrAfter,
  toLocalDate,
  today,
} from '../../../shared/utils/date';
import type {
  CycleOperationResponse,
  CycleRead,
  TrackingKind,
  DailyLogData,
  DailyLogRequest,
  DailyLogResponse,
  PredictionResponseData,
} from '../../../types/api';

export interface DailyFormData {
  mood_level: number | null;
  cramps_severity: number | null;
  is_exercise: boolean | null;
  is_intercourse: boolean | null;
  exercise_type: string;
  exercise_minutes: number | null;
  exercise_intensity: number | null;
  stress_level: number | null;
  diet_tag: string;
  journal_text: string;
  sleep_duration_minutes: number | null;
  sleep_quality: number | null;
  sleep_start_minutes: number | null;
  is_late_night: boolean | null;
  is_night_shift: boolean | null;
  is_medication: boolean | null;
  medication_note: string;
  symptom_levels: {
    headache: number | null;
    bloat: number | null;
    breast_tenderness: number | null;
    fatigue: number | null;
  };
}

export function createDefaultDailyForm(): DailyFormData {
  return {
    mood_level: null,
    cramps_severity: null,
    is_exercise: null,
    is_intercourse: null,
    exercise_type: '',
    exercise_minutes: null,
    exercise_intensity: null,
    stress_level: null,
    diet_tag: '',
    journal_text: '',
    sleep_duration_minutes: null,
    sleep_quality: null,
    sleep_start_minutes: null,
    is_late_night: null,
    is_night_shift: null,
    is_medication: null,
    medication_note: '',
    symptom_levels: { headache: null, bloat: null, breast_tenderness: null, fatigue: null },
  };
}

export function buildDailyLogPayload(form: DailyFormData, logDate: string): DailyLogRequest {
  const result = { ...form, symptom_levels: { ...form.symptom_levels }, log_date: logDate };
  const numericKeys = [
    'mood_level',
    'cramps_severity',
    'exercise_minutes',
    'exercise_intensity',
    'stress_level',
    'sleep_duration_minutes',
    'sleep_quality',
    'sleep_start_minutes',
  ] as const;
  for (const key of numericKeys) {
    if (typeof result[key] !== 'number' || !Number.isFinite(result[key])) result[key] = null;
  }
  if (result.is_exercise === false) {
    result.exercise_minutes = 0;
    result.exercise_intensity = 0;
  }
  return result;
}

interface CalendarAttr {
  key: string;
  highlight?: { color: string; fillMode: string };
  dot?: { color: string };
  dates: Date | { start: Date; end: Date };
  order: number;
  customData?: Record<string, unknown>;
}

export function useCycleCalendar() {
  const selectedDate: Ref<Date> = ref(new Date());
  const prediction = ref<PredictionResponseData | null>(null);
  const predictionMessage = ref('');
  const predictionWarnings = ref<string[]>([]);
  const message = ref('');
  const errorMsg = ref('');
  const aiHealthAdvices = ref<string[]>([]);
  const manualEndDate = ref<Date | null>(null);
  const cycles = ref<CycleRead[]>([]);

  const dailyForm = reactive<DailyFormData>(createDefaultDailyForm());
  const dailyLogLoading = ref(false);
  const dailyLogSaving = ref(false);
  const dailyLogLoadError = ref(false);
  const dailyLogLoadedDate = ref<string | null>(null);

  const isSelectedFuture = computed(() => isAfter(toLocalDate(selectedDate.value), today()));
  const canSaveDailyLog = computed(
    () =>
      !isSelectedFuture.value &&
      !dailyLogLoading.value &&
      !dailyLogSaving.value &&
      dailyLogLoadedDate.value === formatDate(selectedDate.value),
  );
  const calendarMaxDate = computed(() => {
    const forecastStart = toLocalDate(prediction.value?.next_period_start);
    const fertileEnd = toLocalDate(prediction.value?.fertile_window_end);
    const latestForecast = [forecastStart, fertileEnd]
      .filter((value): value is Date => !!value)
      .reduce((latest, value) => (isAfter(value, latest) ? value : latest), today());
    return addDays(latestForecast, 35);
  });

  const findLatestOpenCycle = (list: CycleRead[]): CycleRead | null => {
    const latest = [...list]
      .filter((cycle) => cycle.start_date)
      .sort((a, b) => a.start_date.localeCompare(b.start_date))
      .at(-1);
    return latest && !latest.end_date ? latest : null;
  };

  const findSelectedClosedCycle = (date: Date, list: CycleRead[]): CycleRead | null => {
    const target = toLocalDate(date);
    if (!target) return null;

    const targetTime = target.getTime();
    return (
      [...list].reverse().find((cycle) => {
        const start = toLocalDate(cycle.start_date);
        if (!start) return false;

        const end = toLocalDate(cycle.end_date);
        return !!end && targetTime >= start.getTime() && targetTime <= end.getTime();
      }) || null
    );
  };

  const openCycle = computed(() => findLatestOpenCycle(cycles.value));
  const selectedClosedCycle = computed(() =>
    findSelectedClosedCycle(selectedDate.value, cycles.value),
  );
  const selectedUnknownCycle = computed(() => {
    const target = formatDate(selectedDate.value);
    const preceding = [...cycles.value]
      .filter((cycle) => cycle.start_date <= target)
      .sort((a, b) => a.start_date.localeCompare(b.start_date))
      .at(-1);
    return preceding && !preceding.end_date ? preceding : null;
  });
  const endTargetCycle = computed(() => selectedUnknownCycle.value || openCycle.value);
  const selectedCycle = computed(() => selectedClosedCycle.value || endTargetCycle.value);
  const estimatedBleedingDays = computed(() => {
    const durations = cycles.value
      .map((cycle) => Number(cycle.bleeding_days))
      .filter((days) => Number.isFinite(days) && days > 0);

    if (!durations.length) return 5;

    const average = durations.reduce((sum, days) => sum + days, 0) / durations.length;
    return Math.max(1, Math.round(average));
  });
  const selectedPreviewRange = computed(() => {
    const currentOpen = endTargetCycle.value;
    if (!currentOpen) return null;

    const start = toLocalDate(currentOpen.start_date);
    if (!start) return null;

    const selected = toLocalDate(manualEndDate.value);
    const end =
      selected && isOnOrAfter(selected, start)
        ? selected
        : addDays(start, estimatedBleedingDays.value - 1);

    return { start, end };
  });

  const selectedPreviewMode = computed<'none' | 'default' | 'custom'>(() => {
    if (!endTargetCycle.value) return 'none';
    if (manualEndDate.value) return 'custom';
    return 'default';
  });

  const selectedRangeText = computed(() => {
    if (selectedClosedCycle.value) {
      return `${selectedClosedCycle.value.start_date || ''} ~ ${selectedClosedCycle.value.end_date || ''}`;
    }

    if (selectedPreviewRange.value) {
      return `${formatDate(selectedPreviewRange.value.start)} ~ ${formatDate(selectedPreviewRange.value.end)}`;
    }

    return '';
  });

  const canConfirmEnd = computed(() => {
    const currentOpen = endTargetCycle.value;
    if (!currentOpen) return false;

    const start = toLocalDate(currentOpen.start_date);
    const end = toLocalDate(manualEndDate.value);
    return !selectedClosedCycle.value && !!start && !!end && isOnOrAfter(end, start);
  });

  const calendarAttributes = computed<CalendarAttr[]>(() => {
    const attrs: CalendarAttr[] = [];

    cycles.value.forEach((cycle) => {
      const start = toLocalDate(cycle.start_date);
      if (!start) return;

      const end = toLocalDate(cycle.end_date);
      if (end) {
        attrs.push({
          key: `cycle-${cycle.cycle_id}`,
          highlight: { color: 'red', fillMode: 'solid' },
          dates: { start, end },
          order: 10,
          customData: { cycle_id: cycle.cycle_id, state: 'closed' },
        });
        return;
      }

      attrs.push({
        key: `cycle-open-${cycle.cycle_id}`,
        dot: { color: 'red' },
        dates: start,
        order: 20,
        customData: { cycle_id: cycle.cycle_id, state: 'open' },
      });
    });

    if (selectedPreviewRange.value && endTargetCycle.value) {
      attrs.push({
        key: `cycle-preview-${endTargetCycle.value.cycle_id}-${formatDate(selectedPreviewRange.value.start)}-${formatDate(selectedPreviewRange.value.end)}`,
        highlight: { color: 'red', fillMode: 'light' },
        dates: { start: selectedPreviewRange.value.start, end: selectedPreviewRange.value.end },
        order: 30,
        customData: { cycle_id: endTargetCycle.value.cycle_id, state: 'preview' },
      });
    }

    if (prediction.value) {
      const nextStart = toLocalDate(prediction.value.next_period_start);
      const fertileStart = toLocalDate(prediction.value.fertile_window_start);
      const fertileEnd = toLocalDate(prediction.value.fertile_window_end);

      if (nextStart) {
        attrs.push({
          key: 'pred-start',
          highlight: { color: 'purple', fillMode: 'outline' },
          dates: nextStart,
          order: 1,
          customData: { state: 'predicted-start' },
        });
      }

      if (fertileStart && fertileEnd) {
        attrs.push({
          key: 'pred-fertile',
          highlight: { color: 'green', fillMode: 'light' },
          dates: { start: fertileStart, end: fertileEnd },
          order: 2,
        });
      }
    }

    return attrs;
  });

  const handleRequestError = (err: unknown, fallback: string) => {
    errorMsg.value = extractApiErrorMessage(err, fallback);
  };

  const applySuccess = (
    res: AxiosResponse<CycleOperationResponse | DailyLogResponse>,
    successMsg: string,
  ) => {
    message.value = res.data.message || successMsg;
    errorMsg.value = '';
    if ('ai_health_advice' in res.data) {
      aiHealthAdvices.value = res.data.ai_health_advice;
    }
    void fetchData();
  };

  const markStart = async () => {
    try {
      const res = await logStartApi({ start_date: formatDate(selectedDate.value) });
      applySuccess(res, '标记经期开始');
    } catch (err) {
      handleRequestError(err, '标记开始失败');
    }
  };

  const markEnd = async () => {
    try {
      const res = await logEndApi({
        end_date: formatDate(manualEndDate.value || selectedDate.value),
        cycle_id: endTargetCycle.value?.cycle_id ?? null,
      });
      applySuccess(res, '标记经期结束');
    } catch (err) {
      handleRequestError(err, '标记结束失败');
    }
  };

  const saveLog = async () => {
    if (!canSaveDailyLog.value) {
      errorMsg.value = '请等待当天档案加载完成后再保存；加载失败时请重新加载。';
      return;
    }
    const logDate = formatDate(selectedDate.value);
    dailyLogSaving.value = true;
    try {
      const res = await saveDailyLogApi(buildDailyLogPayload(dailyForm, logDate));
      if (logDate === formatDate(selectedDate.value)) applySuccess(res, '打卡成功');
    } catch (err) {
      if (logDate === formatDate(selectedDate.value)) handleRequestError(err, '保存失败');
    } finally {
      dailyLogSaving.value = false;
    }
  };

  const fillDailyForm = (log: DailyLogData) => {
    const legacy = log.recording_version === 0;
    Object.assign(dailyForm, createDefaultDailyForm());
    const fields = Object.keys(dailyForm).filter((key) => key !== 'symptom_levels') as Array<
      keyof Omit<DailyFormData, 'symptom_levels'>
    >;
    for (const key of fields) {
      const value = log[key];
      // Old defaults cannot tell "not filled" from an explicit zero/false.
      const clean = legacy && (value === 0 || value === false) ? null : value;
      Object.assign(dailyForm, {
        [key]: clean ?? (typeof dailyForm[key] === 'string' ? '' : null),
      });
    }
    for (const key of Object.keys(dailyForm.symptom_levels) as Array<
      keyof DailyFormData['symptom_levels']
    >) {
      const value = log.symptom_levels?.[key] ?? null;
      dailyForm.symptom_levels[key] = legacy && value === 0 ? null : value;
    }
  };

  let dailyLogFetchSeq = 0;

  const loadDailyLogForDate = async (target: Date) => {
    const seq = ++dailyLogFetchSeq;
    const dateStr = formatDate(target);
    dailyLogLoading.value = true;
    dailyLogLoadedDate.value = null;
    dailyLogLoadError.value = false;
    message.value = '';
    errorMsg.value = '';
    aiHealthAdvices.value = [];
    Object.assign(dailyForm, createDefaultDailyForm());
    try {
      const res = await getDailyLogApi(dateStr);
      if (seq !== dailyLogFetchSeq) return; // 丢弃过期响应，防止快速切日期串台
      if (res.data?.status === 'success' && res.data.log) {
        fillDailyForm(res.data.log);
        dailyLogLoadedDate.value = dateStr;
      } else {
        throw new Error('当天档案响应无效');
      }
    } catch (err) {
      if (seq !== dailyLogFetchSeq) return;
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        // 该日无记录：重置为默认表单
        Object.assign(dailyForm, createDefaultDailyForm());
        dailyLogLoadedDate.value = dateStr;
      } else {
        dailyLogLoadError.value = true;
        handleRequestError(err, '当天档案加载失败，请重新加载后再保存');
      }
    } finally {
      if (seq === dailyLogFetchSeq) dailyLogLoading.value = false;
    }
  };
  const reloadDailyLog = () => loadDailyLogForDate(selectedDate.value);

  const clearCycle = async (
    cycleId: number,
    confirmText = '确定清空该区间吗？清空后可重新标记。',
  ) => {
    if (!cycleId) return;
    if (!window.confirm(confirmText)) return;

    try {
      const res = await deleteCycleApi(cycleId);
      message.value = res.data.message || '已清空';
      errorMsg.value = '';
      await fetchData();
    } catch (err) {
      handleRequestError(err, '清空失败');
    }
  };

  const trackingSaving = ref(false);
  const confirmTracking = async (kind: TrackingKind) => {
    if (!selectedCycle.value || trackingSaving.value) return;
    trackingSaving.value = true;
    try {
      const response = await confirmTrackingApi(
        selectedCycle.value.cycle_id,
        kind,
        formatDate(selectedDate.value),
      );
      applySuccess(response, '核对信息已保存');
    } catch (err) {
      handleRequestError(err, '核对信息保存失败');
    } finally {
      trackingSaving.value = false;
    }
  };

  const clearSelectedCycle = async () => {
    if (selectedCycle.value) {
      await clearCycle(selectedCycle.value.cycle_id);
    }
  };

  const fetchData = async () => {
    const [predictionResult, statsResult] = await Promise.allSettled([
      getPredictionApi(),
      getStatsApi(),
    ]);

    if (predictionResult.status === 'fulfilled') {
      const payload = predictionResult.value.data;
      prediction.value = payload.status === 'success' ? payload.prediction : null;
      predictionMessage.value =
        payload.status === 'success' ? '' : payload.message || '暂时无法预测';
      predictionWarnings.value = payload.data_quality_warnings || [];
    } else {
      // 预测数据不足时仍然保留并显示历史周期，不能阻断日历加载。
      prediction.value = null;
      predictionMessage.value = '预测加载失败，请稍后重试。';
      predictionWarnings.value = [];
      console.warn('Prediction unavailable:', predictionResult.reason);
    }

    if (statsResult.status === 'fulfilled') {
      cycles.value = Array.isArray(statsResult.value.data.cycles)
        ? statsResult.value.data.cycles
        : [];
      manualEndDate.value = null;
    } else {
      console.error('Stats unavailable:', statsResult.reason);
      handleRequestError(statsResult.reason, '历史周期加载失败');
    }
  };

  watch(selectedDate, (newDate) => {
    void loadDailyLogForDate(newDate);
    const currentOpen = endTargetCycle.value;
    if (!currentOpen) {
      manualEndDate.value = null;
      return;
    }

    const start = toLocalDate(currentOpen.start_date);
    const end = toLocalDate(newDate);
    if (start && end && isOnOrAfter(end, start)) {
      manualEndDate.value = newDate;
    } else {
      manualEndDate.value = null;
    }
  });

  onMounted(() => {
    void fetchData();
    void loadDailyLogForDate(selectedDate.value);
  });

  return {
    selectedDate,
    prediction,
    predictionMessage,
    predictionWarnings,
    message,
    errorMsg,
    aiHealthAdvices,
    dailyForm,
    dailyLogLoading,
    dailyLogLoadError,
    canSaveDailyLog,
    reloadDailyLog,
    isSelectedFuture,
    calendarMaxDate,
    openCycle,
    endTargetCycle,
    selectedClosedCycle,
    selectedCycle,
    estimatedBleedingDays,
    selectedPreviewMode,
    selectedRangeText,
    canConfirmEnd,
    calendarAttributes,
    markStart,
    markEnd,
    saveLog,
    clearSelectedCycle,
    confirmTracking,
    trackingSaving,
    fetchData,
  };
}
