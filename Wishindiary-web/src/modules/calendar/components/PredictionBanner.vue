<script setup lang="ts">
import type { PredictionResponseData } from '../../../types/api';

defineProps<{ prediction: PredictionResponseData | null }>();
</script>

<template>
  <div>
    <div
      v-if="prediction"
      class="relative overflow-hidden bg-gradient-to-br from-rose-50 via-white to-pink-50 p-5 rounded-3xl shadow-[0_20px_60px_-15px_rgba(244,63,94,0.15)] border border-rose-100/60 flex flex-col md:flex-row items-center justify-between gap-4"
    >
      <div
        class="absolute -top-10 -right-10 w-32 h-32 rounded-full bg-gradient-to-br from-rose-200/30 to-pink-200/30 blur-2xl pointer-events-none"
      ></div>
      <div class="relative flex items-center gap-4">
        <div
          class="w-12 h-12 rounded-2xl bg-white/70 backdrop-blur flex items-center justify-center text-rose-500 shadow-inner shrink-0"
        >
          <span class="text-xl">🤖</span>
        </div>
        <div>
          <p class="text-xs font-bold text-gray-400 uppercase">AI 周期预估</p>
          <p class="text-sm text-gray-800 font-medium">
            下次经期:
            <span class="text-rose-600 font-bold bg-white/70 px-2 py-0.5 rounded-md">
              {{ prediction.next_period_start }}
            </span>
          </p>
          <p class="text-xs text-gray-500 mt-1">
            预测周期:
            <span class="font-bold text-gray-700">{{ prediction.predicted_cycle_length }} 天</span>
          </p>
        </div>
      </div>
      <div
        class="relative text-right w-full md:w-auto border-t md:border-t-0 md:border-l border-rose-100/60 pt-3 md:pt-0 md:pl-6"
      >
        <p class="text-xs font-bold text-gray-400 uppercase">排卵与易孕期</p>
        <p class="text-sm text-gray-800 font-medium">
          核心排卵日:
          <span class="text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded-md">
            {{ prediction.ovulation_date }}
          </span>
        </p>
      </div>
    </div>
    <div
      v-if="prediction && prediction.medical_guardrail_note"
      class="mt-4 text-[11px] leading-relaxed text-amber-700 bg-amber-50/80 border border-amber-100 rounded-2xl px-4 py-3"
    >
      {{ prediction.medical_guardrail_note }}
    </div>
    <div
      v-if="prediction && prediction.data_quality_warnings?.length"
      class="mt-2 space-y-1.5"
    >
      <div
        v-for="(warning, idx) in prediction.data_quality_warnings"
        :key="idx"
        class="text-[11px] leading-relaxed text-orange-700 bg-orange-50/80 border border-orange-100 rounded-2xl px-4 py-3"
      >
        {{ warning }}
      </div>
    </div>
  </div>
</template>
