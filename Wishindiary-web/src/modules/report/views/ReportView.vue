<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { getHealthReportApi } from '../api';
import type { ReportData } from '../../../types/api';

const healthReportData = ref<ReportData | null>(null);
const isLoading = ref(true);

onMounted(async () => {
  try {
    const res = await getHealthReportApi();
    healthReportData.value = res.data.report;
  } catch (err) {
    console.error('报告加载失败', err);
  } finally {
    isLoading.value = false;
  }
});
</script>

<template>
  <div
    class="bg-white rounded-3xl shadow-[0_8px_30px_rgb(0,0,0,0.04)] border border-gray-100 p-8 max-w-lg mx-auto w-full"
  >
    <div class="text-center space-y-2 mb-8 border-b border-gray-100 pb-6">
      <div class="w-12 h-12 bg-gray-800 rounded-full flex items-center justify-center mx-auto mb-3">
        <span class="text-white text-xl">🩺</span>
      </div>
      <h2 class="text-lg font-extrabold text-gray-800">健康记录摘要</h2>
      <p class="text-[11px] font-bold text-gray-400 uppercase tracking-widest">
        Non-diagnostic Summary
      </p>
    </div>

    <div v-if="healthReportData" class="space-y-6">
      <div class="grid grid-cols-2 gap-4">
        <div
          class="bg-gray-50/50 p-4 rounded-2xl border border-gray-100 flex flex-col justify-center"
        >
          <span class="text-[10px] font-bold text-gray-400 uppercase mb-1">平均周期</span>
          <span class="text-xl font-extrabold text-gray-800">
            {{ healthReportData.average_cycle_length }}
            <span class="text-sm font-medium text-gray-500">Days</span>
          </span>
        </div>
        <div
          class="bg-gray-50/50 p-4 rounded-2xl border border-gray-100 flex flex-col justify-center"
        >
          <span class="text-[10px] font-bold text-gray-400 uppercase mb-1">预测误差</span>
          <span class="text-xl font-extrabold text-indigo-600">
            ±{{ healthReportData.ai_prediction_accuracy_days }}
            <span class="text-sm font-medium text-gray-500">Days</span>
          </span>
        </div>
      </div>

      <div class="space-y-3">
        <div
          class="flex items-center justify-between p-3.5 bg-white border border-gray-100 rounded-xl shadow-sm"
        >
          <span class="text-xs font-semibold text-gray-600">记录总数</span>
          <span class="text-xs font-bold text-gray-900">
            {{ healthReportData.total_recorded_cycles }} 个周期
          </span>
        </div>
        <div
          class="flex items-center justify-between p-3.5 bg-white border border-gray-100 rounded-xl shadow-sm"
        >
          <span class="text-xs font-semibold text-gray-600">周期规律性</span>
          <span class="text-xs font-bold text-emerald-600">
            {{ healthReportData.cycle_regularity }}
          </span>
        </div>
        <div
          v-if="healthReportData.latest_prediction_error_days !== null"
          class="flex items-center justify-between p-3.5 bg-white border border-gray-100 rounded-xl shadow-sm"
        >
          <span class="text-xs font-semibold text-gray-600">最近预测偏差</span>
          <span class="text-xs font-bold text-indigo-600">
            ±{{ healthReportData.latest_prediction_error_days }} 天
          </span>
        </div>
        <div
          class="flex items-center justify-between p-3.5 bg-white border border-gray-100 rounded-xl shadow-sm"
        >
          <span class="text-xs font-semibold text-gray-600">痛经综合评级</span>
          <span class="text-xs font-bold text-purple-600">
            {{ healthReportData.cramps_evaluation }}
          </span>
        </div>
      </div>

      <div class="relative mt-6">
        <div
          class="absolute -inset-0.5 bg-gradient-to-r from-rose-100 to-indigo-100 rounded-2xl blur opacity-50"
        ></div>
        <div class="relative bg-white p-5 rounded-2xl border border-rose-50">
          <p class="text-xs font-bold text-gray-800 mb-2">我的状态解读</p>
          <div class="space-y-2 mb-3">
            <p v-if="healthReportData.cycle_length_hint" class="text-[11.5px] text-gray-600 leading-relaxed font-medium">
              {{ healthReportData.cycle_length_hint }}
            </p>
            <p v-if="healthReportData.data_readiness" class="text-[11.5px] text-gray-600 leading-relaxed font-medium">
              {{ healthReportData.data_readiness }}
            </p>
          </div>
          <p class="text-[10.5px] font-bold text-gray-800 uppercase tracking-widest mb-1.5">
            临床建议总览
          </p>
          <p class="text-[11.5px] text-gray-600 leading-relaxed font-medium">
            {{ healthReportData.doctor_advice_summary }}
          </p>
        </div>
      </div>
    </div>

    <div v-else-if="isLoading" class="text-center py-12 flex flex-col items-center">
      <span class="text-xs text-gray-400 font-medium">深度报告聚合中...</span>
    </div>
  </div>
</template>
