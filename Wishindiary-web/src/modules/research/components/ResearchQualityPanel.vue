<script setup lang="ts">
import type { ResearchQuality } from '../../../types/api';
defineProps<{ quality: ResearchQuality }>();
const groupLabels: Record<string, string> = {
  unknown: '背景未知或尚未完整填写',
  explicit_none: '各项背景明确否定',
  reported_context: '报告至少一种背景',
};
</script>
<template>
  <section
    class="space-y-4 rounded-2xl border border-rose-100 bg-white p-5"
    aria-labelledby="research-quality-title"
  >
    <h2 id="research-quality-title" class="font-semibold">授权研究队列与记录质量</h2>
    <p class="text-sm leading-relaxed text-gray-500">
      仅统计当前自愿参加的账号。下方全站运营计数不等于可用于研究的样本数。
    </p>
    <p v-if="!quality.available" class="text-sm text-amber-700">{{ quality.message }}</p>
    <template v-else>
      <div class="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div
          v-for="card in [
            { label: '当前参加', value: quality.participants },
            { label: '及时录入', value: quality.timely_records },
            { label: '事后补录', value: quality.backfilled_records },
            { label: '首次时刻未知', value: quality.unknown_recording_time },
          ]"
          :key="card.label"
          class="rounded-xl bg-gray-50 p-3"
        >
          <p class="text-xs text-gray-500">{{ card.label }}</p>
          <p class="mt-2 text-xl font-semibold">{{ card.value ?? 0 }}</p>
        </div>
      </div>
      <p class="text-sm">
        加入后最近 28 个已结束日历日：{{ quality.observed_days ?? 0 }} /
        {{ quality.calendar_days ?? 0 }} 天有结构化记录，覆盖率
        {{ quality.coverage_pct == null ? '暂无分母' : `${quality.coverage_pct.toFixed(2)}%` }}。
      </p>
      <p class="text-sm text-gray-500">
        睡眠 {{ quality.sleep_days ?? 0 }} 天 · 压力 {{ quality.stress_days ?? 0 }} 天 · 运动
        {{ quality.exercise_days ?? 0 }} 天
      </p>
      <p class="text-sm leading-relaxed text-gray-500">
        记录当天或次日录入称为及时，之后为补录；及时性计数包含已授权历史。覆盖率从本次加入日开始，不含今天，未记录天也计入分母；明确没有运动计为有效观测。
      </p>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="(count, group) in quality.background_groups"
          :key="group"
          class="rounded-full bg-rose-50 px-3 py-2 text-xs text-rose-700"
        >
          {{ groupLabels[group] ?? group }}：{{ count }}
        </span>
      </div>
      <p class="text-xs leading-relaxed text-gray-500">
        医学背景统计只用于分组检查，不能说明原因或诊断。过去预测样本使用当时已知的背景版本。
      </p>
    </template>
  </section>
</template>
