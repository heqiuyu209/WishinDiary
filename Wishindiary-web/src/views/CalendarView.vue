<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue';
import { DatePicker } from 'v-calendar';
import 'v-calendar/style.css';
import { getPredictionApi, getStatsApi, logStartApi, logEndApi, saveDailyLogApi, deleteCycleApi } from '../api/cycleApi';

const selectedDate = ref(new Date());
const prediction = ref(null);
const message = ref('');
const errorMsg = ref('');
const aiHealthAdvices = ref([]);
const manualEndDate = ref(null);

// 周期数据状态
const cycles = ref([]);

const dailyForm = reactive({
  mood_level: 0, cramps_severity: 0, is_exercise: false, is_intercourse: false,
  exercise_type: '', exercise_minutes: 30, diet_tag: '清淡', journal_text: ''
});

const addDays = (date, days) => {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
};

const toLocalDate = (value) => {
  if (!value) return null;

  if (value instanceof Date) {
    return new Date(value.getFullYear(), value.getMonth(), value.getDate());
  }

  if (typeof value === 'string') {
    const [year, month, day] = value.slice(0, 10).split('-').map(Number);
    if (!year || !month || !day) return null;
    return new Date(year, month - 1, day);
  }

  return null;
};

const formatDate = (date) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
};

const isOnOrAfter = (left, right) => !!left && !!right && left.getTime() >= right.getTime();
const isAfter = (left, right) => !!left && !!right && left.getTime() > right.getTime();
const today = () => {
  const now = new Date();
  return new Date(now.getFullYear(), now.getMonth(), now.getDate());
};
const isSelectedFuture = computed(() => isAfter(toLocalDate(selectedDate.value), today()));
const calendarMaxDate = computed(() => {
  const forecastEnd = toLocalDate(prediction.value?.next_period_end);
  const fertileEnd = toLocalDate(prediction.value?.fertile_window_end);
  const latestForecast = [forecastEnd, fertileEnd]
    .filter(Boolean)
    .reduce((latest, value) => (isAfter(value, latest) ? value : latest), today());
  return addDays(latestForecast, 35);
});

const findLatestOpenCycle = (list) => [...list].reverse().find((cycle) => cycle.start_date && !cycle.end_date) || null;

const findSelectedClosedCycle = (date, list) => {
  const target = toLocalDate(date);
  if (!target) return null;

  const targetTime = target.getTime();
  return [...list].reverse().find((cycle) => {
    const start = toLocalDate(cycle.start_date);
    if (!start) return false;

    const end = toLocalDate(cycle.end_date);
    return !!end && targetTime >= start.getTime() && targetTime <= end.getTime();
  }) || null;
};

const openCycle = computed(() => findLatestOpenCycle(cycles.value));
const selectedClosedCycle = computed(() => findSelectedClosedCycle(selectedDate.value, cycles.value));
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
  const end = selected && isOnOrAfter(selected, start)
    ? selected
    : addDays(start, estimatedBleedingDays.value - 1);

  return { start, end };
});

const selectedPreviewMode = computed(() => {
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

const clearCycle = async (cycleId, confirmText = '确定清空该区间吗？清空后可重新标记。') => {
  if (!cycleId) return;
  if (!window.confirm(confirmText)) return;

  try {
    const res = await deleteCycleApi(cycleId);
    message.value = res.data.message;
    errorMsg.value = '';
    await fetchData();
  } catch (err) {
    errorMsg.value = err.response?.data?.detail || '清空失败';
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
    errorMsg.value = statsResult.reason?.response?.data?.detail || '历史周期加载失败';
  }
};

const calendarAttributes = computed(() => {
  const attrs = [];

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
        customData: { cycle_id: cycle.cycle_id, state: 'closed' }
      });
      return;
    }

    attrs.push({
      key: `cycle-open-${cycle.cycle_id}`,
      dot: { color: 'red' },
      dates: start,
      order: 20,
      customData: { cycle_id: cycle.cycle_id, state: 'open' }
    });
  });

  if (selectedPreviewRange.value && openCycle.value) {
    attrs.push({
      key: `cycle-preview-${openCycle.value.cycle_id}-${formatDate(selectedPreviewRange.value.start)}-${formatDate(selectedPreviewRange.value.end)}`,
      highlight: { color: 'red', fillMode: 'light' },
      dates: { start: selectedPreviewRange.value.start, end: selectedPreviewRange.value.end },
      order: 30,
      customData: { cycle_id: openCycle.value.cycle_id, state: 'preview' }
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

const handleAction = async (apiCall, successMsg) => {
  try {
    let payload;
    if (apiCall === saveDailyLogApi) {
      payload = { log_date: formatDate(selectedDate.value), ...dailyForm };
    } else if (apiCall === logStartApi) {
      payload = { start_date: formatDate(selectedDate.value) };
    } else {
      payload = {
        end_date: formatDate(manualEndDate.value || selectedDate.value),
        cycle_id: openCycle.value?.cycle_id ?? null
      };
    }

    const res = await apiCall(payload);
    message.value = res.data.message || successMsg;
    errorMsg.value = '';
    aiHealthAdvices.value = res.data.ai_health_advice || [];
    await fetchData();
  } catch (err) {
    errorMsg.value = err.response?.data?.detail || '操作失败';
  }
};

const clearSelectedCycle = async () => {
  await clearCycle(selectedCycle.value?.cycle_id);
};

watch(selectedDate, (newDate) => {
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

onMounted(() => { fetchData(); });
</script>

<template>
  <div class="space-y-6">
    <div v-if="prediction" class="relative overflow-hidden bg-gradient-to-br from-rose-50 via-white to-pink-50 p-5 rounded-3xl shadow-[0_20px_60px_-15px_rgba(244,63,94,0.15)] border border-rose-100/60 flex flex-col md:flex-row items-center justify-between gap-4">
      <div class="absolute -top-10 -right-10 w-32 h-32 rounded-full bg-gradient-to-br from-rose-200/30 to-pink-200/30 blur-2xl pointer-events-none"></div>
      <div class="relative flex items-center gap-4">
        <div class="w-12 h-12 rounded-2xl bg-white/70 backdrop-blur flex items-center justify-center text-rose-500 shadow-inner shrink-0"><span class="text-xl">🤖</span></div>
        <div>
          <p class="text-xs font-bold text-gray-400 uppercase">AI 周期预估</p>
          <p class="text-sm text-gray-800 font-medium">下次经期: <span class="text-rose-600 font-bold bg-white/70 px-2 py-0.5 rounded-md">{{ prediction.next_period_start }}</span></p>
          <p class="text-xs text-gray-500 mt-1">预测周期: <span class="font-bold text-gray-700">{{ prediction.predicted_cycle_length }} 天</span></p>
        </div>
      </div>
      <div class="relative text-right w-full md:w-auto border-t md:border-t-0 md:border-l border-rose-100/60 pt-3 md:pt-0 md:pl-6">
          <p class="text-xs font-bold text-gray-400 uppercase">排卵与易孕期</p>
          <p class="text-sm text-gray-800 font-medium">核心排卵日: <span class="text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded-md">{{ prediction.ovulation_date }}</span></p>
      </div>
    </div>
    <div v-if="prediction && prediction.medical_guardrail_note" class="mt-4 text-[11px] leading-relaxed text-amber-700 bg-amber-50/80 border border-amber-100 rounded-2xl px-4 py-3">
      {{ prediction.medical_guardrail_note }}
    </div>

    <div class="grid grid-cols-1 md:grid-cols-12 gap-6">
      <div class="md:col-span-6 bg-white rounded-3xl shadow-[0_20px_60px_-15px_rgba(244,63,94,0.10)] border border-gray-100 p-6 flex flex-col items-center">
        <DatePicker v-model="selectedDate" :attributes="calendarAttributes" :max-date="calendarMaxDate" expanded color="pink" class="border-0 shadow-none !font-sans" />

        <div class="w-full mt-6 space-y-3">
          <div class="bg-gray-50 p-3 rounded-2xl flex justify-between items-center border border-gray-100/50">
            <span class="text-xs font-medium text-gray-500">当前选中日期</span>
            <span class="text-sm font-bold text-gray-800">{{ formatDate(selectedDate) }}</span>
          </div>
          <div v-if="selectedClosedCycle" class="bg-rose-50 p-3 rounded-2xl border border-rose-100 text-rose-700">
            <div class="flex items-center justify-between gap-3">
              <span class="text-xs font-medium">当前选中区间</span>
              <span class="text-[11px] font-semibold bg-white px-2 py-0.5 rounded-full border border-rose-100">可清空</span>
            </div>
            <p class="mt-1 text-sm font-bold">{{ selectedRangeText }}</p>
          </div>
          <div v-else-if="openCycle" class="bg-amber-50 p-3 rounded-2xl border border-amber-100 text-amber-700">
            <div class="flex items-center justify-between gap-3">
              <span class="text-xs font-medium">{{ selectedPreviewMode === 'custom' ? '正在预览区间' : '系统预估区间' }}</span>
              <span class="text-[11px] font-semibold bg-white px-2 py-0.5 rounded-full border border-amber-100">
                {{ selectedPreviewMode === 'custom' ? '待确认结束' : `历史平均 ${estimatedBleedingDays} 天` }}
              </span>
            </div>
            <p class="mt-1 text-sm font-bold">{{ selectedRangeText }}</p>
          </div>
          <div v-else class="bg-gray-50 p-3 rounded-2xl border border-gray-100 text-gray-600 text-xs">
            先在日历上选择开始日期，再点“标记开始”；之后只需点结束日期并确认，不需要手工输入。
          </div>
          <div class="flex flex-col sm:flex-row gap-3">
            <button :disabled="isSelectedFuture" @click="handleAction(logStartApi, '标记经期开始')" class="flex-1 bg-gray-800 hover:bg-gray-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-2xl text-xs transition-all active:scale-[0.98]">标记开始</button>
            <button
              @click="handleAction(logEndApi, '标记经期结束')"
              :disabled="!canConfirmEnd || isSelectedFuture"
              class="flex-1 bg-white border border-gray-200 hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400 disabled:border-gray-100 text-gray-700 font-semibold py-3 rounded-2xl text-xs transition-all active:scale-[0.98]"
            >
              标记结束
            </button>
            <button
              v-if="selectedCycle"
              @click="clearSelectedCycle"
              class="flex-1 bg-rose-50 border border-rose-100 hover:bg-rose-100 text-rose-600 font-semibold py-3 rounded-2xl text-xs transition-all active:scale-[0.98]"
            >
              清空选中区间
            </button>
          </div>
          <p v-if="openCycle" class="text-[11px] text-gray-400">
            已选开始日期后，点击日历上后续日期即可连续预览区间，再用“标记结束”保存。
          </p>
        </div>

      </div>

      <div class="md:col-span-6 relative overflow-hidden bg-gradient-to-br from-white via-rose-50/30 to-pink-50/40 rounded-3xl shadow-[0_20px_60px_-15px_rgba(244,63,94,0.10)] border border-rose-100/50 p-6 flex flex-col h-full">
        <div class="mb-5 flex items-center justify-between">
          <h3 class="text-sm font-bold text-gray-800">✍️ 每日健康档案</h3>
          <span class="text-[10px] bg-purple-50 text-purple-600 px-2.5 py-1 rounded-full font-bold uppercase tracking-wider">AI 分析</span>
        </div>

        <div class="space-y-4 flex-1">
          <div class="grid grid-cols-2 gap-4 text-xs">
            <select v-model.number="dailyForm.mood_level" class="p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl outline-none"><option :value="0">😊 平静</option><option :value="1">✨ 开心</option><option :value="2">⚡ 烦躁</option><option :value="3">🌧️ 低落</option></select>
            <select v-model.number="dailyForm.cramps_severity" class="p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl outline-none"><option :value="0">🟢 无腹痛</option><option :value="1">🟡 轻隐痛</option><option :value="2">🟠 中度痛</option><option :value="3">🔴 重剧痛</option></select>
          </div>
          <div class="grid grid-cols-2 gap-4 text-xs">
            <input v-model="dailyForm.exercise_type" type="text" placeholder="运动: 瑜伽" class="p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl outline-none" />
            <input v-model.number="dailyForm.exercise_minutes" type="number" min="0" placeholder="时长(分)" class="p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl outline-none" />
          </div>
          <input v-model="dailyForm.diet_tag" type="text" placeholder="饮食: 清淡" class="w-full p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl text-xs outline-none" />
          <textarea v-model="dailyForm.journal_text" rows="2" maxlength="4000" placeholder="自由日记..." class="w-full p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl text-xs outline-none resize-none"></textarea>

          <div class="flex items-center gap-6 pt-1 text-[11px] font-semibold text-gray-600">
            <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" v-model="dailyForm.is_exercise" class="w-4 h-4 text-purple-500 rounded" /> 今日运动</label>
            <label class="flex items-center gap-2 cursor-pointer"><input type="checkbox" v-model="dailyForm.is_intercourse" class="w-4 h-4 text-pink-500 rounded" /> 同房记录</label>
          </div>
        </div>

        <button :disabled="isSelectedFuture" @click="handleAction(saveDailyLogApi, '打卡成功')" class="w-full mt-6 bg-purple-500 hover:bg-purple-600 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-bold py-3.5 rounded-2xl text-xs shadow-md transition-all active:scale-[0.98]">
          保存档案并生成分析
        </button>
      </div>
    </div>

    <div v-if="message" class="p-3 bg-emerald-50 text-emerald-600 rounded-xl text-xs font-medium text-center">{{ message }}</div>
    <div v-if="errorMsg" class="p-3 bg-red-50 text-red-600 rounded-xl text-xs font-medium text-center">{{ errorMsg }}</div>
  </div>
</template>
