<script setup lang="ts">
import type { DailyFormData } from '../composables/useCycleCalendar';

const form = defineModel<DailyFormData>('form', { required: true });
defineProps<{
  disabled: boolean;
}>();
const emit = defineEmits<{ save: [] }>();

const symptomOptions: Array<{ key: keyof DailyFormData['symptom_levels']; label: string }> = [
  { key: 'headache', label: '头痛' },
  { key: 'bloat', label: '腹胀' },
  { key: 'breast_tenderness', label: '乳房胀痛' },
  { key: 'fatigue', label: '疲劳' },
];
</script>

<template>
  <div
    class="relative overflow-hidden bg-gradient-to-br from-white via-rose-50/30 to-pink-50/40 rounded-3xl shadow-[0_20px_60px_-15px_rgba(244,63,94,0.10)] border border-rose-100/50 p-6 flex flex-col h-full"
  >
    <div class="mb-5 flex items-center justify-between">
      <h3 class="text-sm font-bold text-gray-800">✍️ 每日健康档案</h3>
      <span
        class="text-[10px] bg-purple-50 text-purple-600 px-2.5 py-1 rounded-full font-bold uppercase tracking-wider"
      >
        AI 分析
      </span>
    </div>

    <div class="space-y-4 flex-1">
      <div class="grid grid-cols-2 gap-4 text-xs">
        <select
          v-model.number="form.mood_level"
          class="p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl outline-none"
        >
          <option :value="0">😊 平静</option>
          <option :value="1">✨ 开心</option>
          <option :value="2">⚡ 烦躁</option>
          <option :value="3">🌧️ 低落</option>
        </select>
        <select
          v-model.number="form.cramps_severity"
          class="p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl outline-none"
        >
          <option :value="0">🟢 无腹痛</option>
          <option :value="1">🟡 轻隐痛</option>
          <option :value="2">🟠 中度痛</option>
          <option :value="3">🔴 重剧痛</option>
        </select>
      </div>
      <div class="grid grid-cols-2 gap-4 text-xs">
        <input
          v-model="form.exercise_type"
          type="text"
          placeholder="运动: 瑜伽"
          class="p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl outline-none"
        />
        <input
          v-model.number="form.exercise_minutes"
          type="number"
          min="0"
          placeholder="时长(分)"
          class="p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl outline-none"
        />
      </div>
      <input
        v-model="form.diet_tag"
        type="text"
        placeholder="饮食: 清淡"
        class="w-full p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl text-xs outline-none"
      />
      <textarea
        v-model="form.journal_text"
        rows="2"
        maxlength="4000"
        placeholder="自由日记..."
        class="w-full p-2.5 bg-gray-50/50 border border-gray-200 rounded-xl text-xs outline-none resize-none"
      ></textarea>

      <div class="flex items-center gap-6 pt-1 text-[11px] font-semibold text-gray-600">
        <label class="flex items-center gap-2 cursor-pointer">
          <input
            v-model="form.is_exercise"
            type="checkbox"
            class="w-4 h-4 text-purple-500 rounded"
          />
          今日运动
        </label>
        <label class="flex items-center gap-2 cursor-pointer">
          <input
            v-model="form.is_intercourse"
            type="checkbox"
            class="w-4 h-4 text-pink-500 rounded"
          />
          同房记录
        </label>
      </div>

      <!-- 睡眠 / 熬夜 -->
      <div class="rounded-xl bg-blue-50/40 border border-blue-100/60 p-3 space-y-3">
        <div class="flex items-center justify-between text-[11px] font-bold text-blue-700">
          <span>😴 睡眠与熬夜</span>
          <label class="flex items-center gap-2 font-semibold text-gray-600 cursor-pointer">
            <input
              v-model="form.is_late_night"
              type="checkbox"
              class="w-4 h-4 text-blue-500 rounded"
            />
            昨晚熬夜
          </label>
        </div>
        <div class="grid grid-cols-2 gap-3">
          <label class="flex flex-col gap-1">
            <span class="text-[10px] text-gray-500">睡眠时长(分钟)</span>
            <input
              v-model.number="form.sleep_duration_minutes"
              type="number"
              min="0"
              max="1440"
              class="p-2 bg-white/70 border border-gray-200 rounded-xl outline-none text-xs"
            />
          </label>
          <label class="flex flex-col gap-1">
            <span class="text-[10px] text-gray-500">睡眠质量</span>
            <select
              v-model.number="form.sleep_quality"
              class="p-2 bg-white/70 border border-gray-200 rounded-xl outline-none text-xs"
            >
              <option :value="0">未填</option>
              <option :value="1">很差</option>
              <option :value="2">一般</option>
              <option :value="3">很好</option>
            </select>
          </label>
        </div>
      </div>

      <!-- 用药记录 -->
      <div class="rounded-xl bg-amber-50/40 border border-amber-100/60 p-3 space-y-3">
        <label class="flex items-center gap-2 text-[11px] font-bold text-amber-700 cursor-pointer">
          <input
            v-model="form.is_medication"
            type="checkbox"
            class="w-4 h-4 text-amber-500 rounded"
          />
          今日服用了药物
        </label>
        <input
          v-if="form.is_medication"
          v-model="form.medication_note"
          type="text"
          maxlength="100"
          placeholder="用药说明（≤100字）"
          class="w-full p-2 bg-white/70 border border-gray-200 rounded-xl text-xs outline-none"
        />
      </div>

      <!-- 症状明细 -->
      <div class="rounded-xl bg-rose-50/40 border border-rose-100/60 p-3 space-y-2">
        <span class="text-[11px] font-bold text-rose-700 block">🩺 症状明细</span>
        <div v-for="item in symptomOptions" :key="item.key" class="flex items-center gap-2">
          <span class="w-20 text-[11px] text-gray-600">{{ item.label }}</span>
          <select
            v-model.number="form.symptom_levels[item.key]"
            class="flex-1 p-2 bg-white/70 border border-gray-200 rounded-xl outline-none text-xs"
          >
            <option :value="0">无</option>
            <option :value="1">轻</option>
            <option :value="2">中</option>
            <option :value="3">重</option>
          </select>
        </div>
      </div>
    </div>

    <button
      :disabled="disabled"
      @click="emit('save')"
      class="w-full mt-6 bg-purple-500 hover:bg-purple-600 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-bold py-3.5 rounded-2xl text-xs shadow-md transition-all active:scale-[0.98]"
    >
      保存档案并生成分析
    </button>
  </div>
</template>
