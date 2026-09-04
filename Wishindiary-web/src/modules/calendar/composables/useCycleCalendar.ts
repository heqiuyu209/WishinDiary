import { computed, onMounted, reactive, ref, watch, type Ref } from 'vue';
import type { AxiosResponse } from 'axios';
import { deleteCycleApi, getDailyLogApi, logEndApi, logStartApi, saveDailyLogApi } from '../api';
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
  DailyLogData,
  DailyLogResponse,
  PredictionResponseData,
} from '../../../types/api';

export interface DailyFormData {
  mood_level: number;
  cramps_severity: number;
  is_exercise: boolean;
  is_intercourse: boolean;
  exercise_type: string;
  exercise_minutes: number;
  diet_tag: string;
  journal_text: string;
  // --- 新增自记录维度 ---
  sleep_duration_minutes: number;
  sleep_quality: number;
  is_late_night: boolean;
  is_medication: boolean;
  medication_note: string;
  symptom_levels: { headache: number; bloat: number; breast_tenderness: number; fatigue: number };
}

export function createDefaultDailyForm(): DailyFormData {
  return {
    mood_level: 0,
    cramps_severity: 0,
    is_exercise: false,
    is_intercourse: false,
    exercise_type: '',
    exercise_minutes: 30,
    diet_tag: '清淡',
    journal_text: '',
    sleep_duration_minutes: 0,
    sleep_quality: 0,
    is_late_night: false,
    is_medication: false,
    medication_note: '',
    symptom_levels: { headache: 0, bloat: 0, breast_tenderness: 0, fatigue: 0 },
  };
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
  const message = ref('');
  const errorMsg = ref('');
  const aiHealthAdvices = ref<string[]>([]);
  const manualEndDate = ref<Date | null>(null);
  const cycles = ref<CycleRead[]>([]);

  const dailyForm = reactive<DailyFormData>(createDefaultDailyForm());

  const isSelectedFuture = computed(() => isAfter(toLocalDate(selectedDate.value), today()));
  const calendarMaxDate = computed(() => {
    const forecastEnd = toLocalDate(prediction.value?.next_period_end);
    const fertileEnd = toLocalDate(prediction.value?.fertile_window_end);
    const latestForecast = [forecastEnd, fertileEnd]
      .filter((value): value is Date => !!value)
      .reduce((latest, value) => (isAfter(value, latest) ? value : latest), today());
    return addDays(latestForecast, 35);
  });

  const findLatestOpenCycle = (list: CycleRead[]): CycleRead | null =>
    [...list].reverse().find((cycle) => cycle.start_date && !cycle.end_date) || null;

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
  const selectedCycle = computed(() => selectedClosedCycle.value || openCycle.value);
  const estimatedBleedingDays = computed(() => {
    const durations = cycles.value
      .map((cycle) => Number(cycle.bleeding_days))
      .filter((days) => Number.isFinite(days) && days > 0);

    if (!durations.length) return 5;

    const average = durations.reduce((sum, days) => sum + days, 0) / durations.length;
    return Math.max(1, Math.round(average));
  });
  const selectedPreviewRange = computed(() => {
    const currentOpen = openCycle.value;
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
    if (!openCycle.value) return 'none';
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
    const currentOpen = openCycle.value;
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

    if (selectedPreviewRange.value && openCycle.value) {
      attrs.push({
        key: `cycle-preview-${openCycle.value.cycle_id}-${formatDate(selectedPreviewRange.value.start)}-${formatDate(selectedPreviewRange.value.end)}`,
        highlight: { color: 'red', fillMode: 'light' },
        dates: { start: selectedPreviewRange.value.start, end: selectedPreviewRange.value.end },
        order: 30,
        customData: { cycle_id: openCycle.value.cycle_id, state: 'preview' },
      });
    }

    if (prediction.value) {
      const nextStart = toLocalDate(prediction.value.next_period_start);
      const nextEnd = toLocalDate(prediction.value.next_period_end);
      const fertileStart = toLocalDate(prediction.value.fertile_window_start);
      const fertileEnd = toLocalDate(prediction.value.fertile_window_end);

      if (nextStart && nextEnd) {
        attrs.push({
          key: 'pred-period',
          highlight: { color: 'purple', fillMode: 'light' },
          dates: { start: nextStart, end: nextEnd },
          order: 1,
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
        cycle_id: openCycle.value?.cycle_id ?? null,
      });
      applySuccess(res, '标记经期结束');
    } catch (err) {
      handleRequestError(err, '标记结束失败');
    }
  };

  const saveLog = async () => {
    try {
      const res = await saveDailyLogApi({
        log_date: formatDate(selectedDate.value),
        ...dailyForm,
      });
      applySuccess(res, '打卡成功');
    } catch (err) {
      handleRequestError(err, '保存失败');
    }
  };

  const fillDailyForm = (log: DailyLogData) => {
    dailyForm.mood_level = log.mood_level;
    dailyForm.cramps_severity = log.cramps_severity;
    dailyForm.is_exercise = log.is_exercise;
    dailyForm.is_intercourse = log.is_intercourse;
    dailyForm.exercise_type = log.exercise_type ?? '';
    dailyForm.exercise_minutes = log.exercise_minutes;
    dailyForm.diet_tag = log.diet_tag ?? '';
    dailyForm.journal_text = log.journal_text ?? '';
    dailyForm.sleep_duration_minutes = log.sleep_duration_minutes ?? 0;
    dailyForm.sleep_quality = log.sleep_quality ?? 0;
    dailyForm.is_late_night = log.is_late_night ?? false;
    dailyForm.is_medication = log.is_medication ?? false;
    dailyForm.medication_note = log.medication_note ?? '';
    dailyForm.symptom_levels = log.symptom_levels
      ? {
          headache: log.symptom_levels.headache ?? 0,
          bloat: log.symptom_levels.bloat ?? 0,
          breast_tenderness: log.symptom_levels.breast_tenderness ?? 0,
          fatigue: log.symptom_levels.fatigue ?? 0,
        }
      : { headache: 0, bloat: 0, breast_tenderness: 0, fatigue: 0 };
  };

  let dailyLogFetchSeq = 0;

  const loadDailyLogForDate = async (target: Date) => {
    const seq = ++dailyLogFetchSeq;
    const dateStr = formatDate(target);
    try {
      const res = await getDailyLogApi(dateStr);
      if (seq !== dailyLogFetchSeq) return; // 丢弃过期响应，防止快速切日期串台
      if (res.data?.status === 'success' && res.data.log) {
        fillDailyForm(res.data.log);
      }
    } catch (err) {
      if (seq !== dailyLogFetchSeq) return;
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404) {
        // 该日无记录：重置为默认表单
        Object.assign(dailyForm, createDefaultDailyForm());
      }
      // 其它错误静默处理，不打断用户
    }
  };

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
    } else {
      // 预测数据不足时仍然保留并显示历史周期，不能阻断日历加载。
      prediction.value = null;
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
    const currentOpen = openCycle.value;
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
    message,
    errorMsg,
    aiHealthAdvices,
    dailyForm,
    isSelectedFuture,
    calendarMaxDate,
    openCycle,
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
    fetchData,
  };
}
