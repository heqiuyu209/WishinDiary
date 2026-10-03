<script setup lang="ts">
import { DatePicker } from 'v-calendar';
import 'v-calendar/style.css';
import { useCycleCalendar } from '../composables/useCycleCalendar';
import { formatDate } from '../../../shared/utils/date';
import PredictionBanner from '../components/PredictionBanner.vue';
import CycleRangePanel from '../components/CycleRangePanel.vue';
import DailyHealthForm from '../components/DailyHealthForm.vue';

const {
  selectedDate,
  prediction,
  predictionMessage,
  predictionWarnings,
  message,
  errorMsg,
  dailyForm,
  dailyLogLoading,
  dailyLogLoadError,
  canSaveDailyLog,
  reloadDailyLog,
  isSelectedFuture,
  calendarMaxDate,
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
} = useCycleCalendar();
</script>

<template>
  <div class="space-y-6">
    <PredictionBanner :prediction="prediction" />
    <div
      v-if="predictionMessage"
      role="status"
      class="rounded-2xl bg-amber-50 p-4 text-sm text-amber-800"
    >
      <p>{{ predictionMessage }}</p>
      <p v-for="warning in predictionWarnings" :key="warning" class="mt-2 text-xs">{{ warning }}</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-12 gap-6">
      <div
        class="md:col-span-6 bg-white rounded-3xl shadow-[0_20px_60px_-15px_rgba(244,63,94,0.10)] border border-gray-100 p-6 flex flex-col items-center"
      >
        <ul
          aria-label="日历标记说明"
          class="mb-4 flex w-full flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs text-gray-500"
        >
          <li class="flex items-center gap-1.5">
            <span aria-hidden="true" class="h-2.5 w-2.5 rounded-full bg-red-500"></span>
            经期记录与预览
          </li>
          <li class="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              class="h-2.5 w-2.5 rounded-full border-2 border-purple-500"
            ></span>
            预计开始日
          </li>
          <li class="flex items-center gap-1.5">
            <span aria-hidden="true" class="h-2.5 w-2.5 rounded-full bg-green-200"></span>
            估算易孕期
          </li>
        </ul>
        <DatePicker
          v-model="selectedDate"
          :attributes="calendarAttributes"
          :max-date="calendarMaxDate"
          expanded
          color="pink"
          class="border-0 shadow-none !font-sans"
        />

        <CycleRangePanel
          :selected-date-text="formatDate(selectedDate)"
          :is-selected-future="isSelectedFuture"
          :can-confirm-end="canConfirmEnd"
          :has-selected-closed-cycle="!!selectedClosedCycle"
          :has-open-cycle="!!endTargetCycle"
          :preview-mode="selectedPreviewMode"
          :range-text="selectedRangeText"
          :estimated-bleeding-days="estimatedBleedingDays"
          :show-clear="!!selectedCycle"
          :has-open-cycle-hint="!!endTargetCycle"
          @mark-start="markStart"
          @mark-end="markEnd"
          @clear="clearSelectedCycle"
        />
      </div>

      <div class="md:col-span-6">
        <p v-if="dailyLogLoading" role="status" class="mb-2 text-xs text-gray-500">
          正在加载当天档案…
        </p>
        <button
          v-if="dailyLogLoadError"
          class="mb-2 text-xs text-purple-600 underline"
          @click="reloadDailyLog"
        >
          重新加载档案
        </button>
        <DailyHealthForm v-model:form="dailyForm" :disabled="!canSaveDailyLog" @save="saveLog" />
      </div>
    </div>

    <div
      v-if="message"
      class="p-3 bg-emerald-50 text-emerald-600 rounded-xl text-xs font-medium text-center"
    >
      {{ message }}
    </div>
    <div
      v-if="errorMsg"
      class="p-3 bg-red-50 text-red-600 rounded-xl text-xs font-medium text-center"
    >
      {{ errorMsg }}
    </div>
  </div>
</template>
