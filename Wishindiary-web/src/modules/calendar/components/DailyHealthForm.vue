<script setup lang="ts">
import { watch } from 'vue';
import type { DailyFormData } from '../composables/useCycleCalendar';

const form = defineModel<DailyFormData>('form', { required: true });
defineProps<{ disabled: boolean }>();
const emit = defineEmits<{ save: [] }>();
const symptomOptions: Array<{ key: keyof DailyFormData['symptom_levels']; label: string }> = [
  { key: 'headache', label: '头痛' },
  { key: 'bloat', label: '腹胀' },
  { key: 'breast_tenderness', label: '乳房胀痛' },
  { key: 'fatigue', label: '疲劳' },
];
const flagOptions = [
  { value: null, label: '未填写' },
  { value: false, label: '没有' },
  { value: true, label: '有' },
];
const flags: Array<{
  key: 'is_late_night' | 'is_night_shift' | 'is_medication' | 'is_intercourse';
  label: string;
}> = [
  { key: 'is_late_night', label: '昨晚熬夜（自评）' },
  { key: 'is_night_shift', label: '昨晚夜班' },
  { key: 'is_medication', label: '今日用药' },
  { key: 'is_intercourse', label: '同房（自愿记录）' },
];
const sleepTime = () => {
  const value = form.value.sleep_start_minutes;
  return value == null
    ? ''
    : `${String(Math.floor(value / 60)).padStart(2, '0')}:${String(value % 60).padStart(2, '0')}`;
};
const setSleepTime = (event: Event) => {
  const value = (event.target as HTMLInputElement).value;
  const [hour, minute] = value.split(':').map(Number);
  form.value.sleep_start_minutes =
    value && hour != null && minute != null ? hour * 60 + minute : null;
};
watch(
  () => form.value.is_exercise,
  (value) => {
    if (value === false) {
      form.value.exercise_minutes = 0;
      form.value.exercise_intensity = 0;
    }
  },
);
</script>

<template>
  <fieldset
    :disabled="disabled"
    class="bg-white rounded-3xl shadow-sm border border-rose-100 p-6 space-y-4"
  >
    <h3 class="text-sm font-bold text-gray-800">✍️ 每日健康档案</h3>
    <p class="text-xs text-gray-500 leading-relaxed">
      所有项目均可跳过。“未填写”与“没有”分别保存，按实际情况选择。睡眠填写昨晚到今天的情况；旧记录中的默认零值需重新核对。生活因素先用于记录与离线研究，真实数据训练需独立授权。
    </p>
    <div class="grid grid-cols-2 gap-3 text-xs">
      <label class="space-y-1">
        心情
        <select v-model="form.mood_level" class="w-full border rounded-xl p-2">
          <option :value="null">未填写</option>
          <option :value="0">平静</option>
          <option :value="1">开心</option>
          <option :value="2">烦躁</option>
          <option :value="3">低落</option>
        </select>
      </label>
      <label class="space-y-1">
        腹痛
        <select v-model="form.cramps_severity" class="w-full border rounded-xl p-2">
          <option :value="null">未填写</option>
          <option :value="0">无</option>
          <option :value="1">轻</option>
          <option :value="2">中</option>
          <option :value="3">重</option>
        </select>
      </label>
    </div>
    <label class="block text-xs space-y-1">
      压力（今日自评，与心情分开记录）
      <select v-model="form.stress_level" class="w-full border rounded-xl p-2">
        <option :value="null">未填写</option>
        <option :value="0">无压力</option>
        <option :value="1">轻</option>
        <option :value="2">中</option>
        <option :value="3">重</option>
      </select>
    </label>
    <div class="rounded-xl bg-blue-50 p-3 space-y-3 text-xs">
      <h4 class="font-bold text-blue-800">睡眠与作息</h4>
      <div class="grid grid-cols-2 gap-3">
        <label class="space-y-1">
          睡眠时长（分钟）
          <input
            v-model.number="form.sleep_duration_minutes"
            type="number"
            min="0"
            max="1440"
            placeholder="未填写"
            class="w-full bg-white border rounded-xl p-2"
          />
        </label>
        <label class="space-y-1">
          入睡时间（当地时间）
          <input
            :value="sleepTime()"
            @input="setSleepTime"
            type="time"
            class="w-full bg-white border rounded-xl p-2"
          />
        </label>
      </div>
      <label class="block space-y-1">
        睡眠质量
        <select v-model="form.sleep_quality" class="w-full bg-white border rounded-xl p-2">
          <option :value="null">未填写</option>
          <option :value="0">很差</option>
          <option :value="1">较差</option>
          <option :value="2">一般</option>
          <option :value="3">很好</option>
        </select>
      </label>
    </div>
    <div class="rounded-xl bg-indigo-50 p-3 space-y-3 text-xs">
      <h4 class="font-bold text-indigo-800">运动</h4>
      <label class="block space-y-1">
        今日是否运动
        <select v-model="form.is_exercise" class="w-full bg-white border rounded-xl p-2">
          <option v-for="option in flagOptions" :key="String(option.value)" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
      <div class="grid grid-cols-2 gap-3">
        <label class="space-y-1">
          运动时长（分钟）
          <input
            v-model.number="form.exercise_minutes"
            :disabled="form.is_exercise === false"
            type="number"
            min="0"
            max="1440"
            placeholder="未填写"
            class="w-full bg-white border rounded-xl p-2"
          />
        </label>
        <label class="space-y-1">
          运动强度（自评）
          <select
            v-model="form.exercise_intensity"
            :disabled="form.is_exercise === false"
            class="w-full bg-white border rounded-xl p-2"
          >
            <option :value="null">未填写</option>
            <option :value="0">无</option>
            <option :value="1">轻</option>
            <option :value="2">中</option>
            <option :value="3">高</option>
          </select>
        </label>
      </div>
      <label class="block space-y-1">
        运动类型
        <input
          v-model="form.exercise_type"
          type="text"
          maxlength="50"
          placeholder="选填，例如散步"
          class="w-full bg-white border rounded-xl p-2"
        />
      </label>
      <p class="text-gray-500">
        时长与强度不能代替能量摄入或消耗测量，当前不据此换算经期变化天数。
      </p>
    </div>
    <div class="grid grid-cols-2 gap-3 text-xs">
      <label v-for="flag in flags" :key="flag.key" class="space-y-1">
        {{ flag.label }}
        <select v-model="form[flag.key]" class="w-full border rounded-xl p-2">
          <option v-for="option in flagOptions" :key="String(option.value)" :value="option.value">
            {{ option.label }}
          </option>
        </select>
      </label>
    </div>
    <label v-if="form.is_medication" class="block text-xs space-y-1">
      用药说明
      <input
        v-model="form.medication_note"
        type="text"
        maxlength="100"
        class="w-full border rounded-xl p-2"
      />
    </label>
    <div class="rounded-xl bg-rose-50 p-3 space-y-2 text-xs">
      <h4 class="font-bold text-rose-800">症状明细</h4>
      <label v-for="item in symptomOptions" :key="item.key" class="flex items-center gap-3">
        <span class="w-20">{{ item.label }}</span>
        <select
          v-model="form.symptom_levels[item.key]"
          class="flex-1 bg-white border rounded-xl p-2"
        >
          <option :value="null">未填写</option>
          <option :value="0">无</option>
          <option :value="1">轻</option>
          <option :value="2">中</option>
          <option :value="3">重</option>
        </select>
      </label>
    </div>
    <label class="block text-xs space-y-1">
      饮食记录
      <input
        v-model="form.diet_tag"
        type="text"
        maxlength="100"
        placeholder="选填"
        class="w-full border rounded-xl p-2"
      />
    </label>
    <label class="block text-xs space-y-1">
      自由日记
      <textarea
        v-model="form.journal_text"
        rows="2"
        maxlength="4000"
        class="w-full border rounded-xl p-2 resize-none"
      ></textarea>
    </label>
    <button
      :disabled="disabled"
      @click="emit('save')"
      class="w-full bg-purple-500 hover:bg-purple-600 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-bold p-3 rounded-2xl text-xs"
    >
      保存档案
    </button>
  </fieldset>
</template>
