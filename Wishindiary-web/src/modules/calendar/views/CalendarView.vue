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
  calendarTimezone,
  calendarTimeReady,
  calendarTimeLoading,
  calendarTimeError,
  reloadCalendarTime,
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
  endTargetCycle,
  selectedClosedCycle,
  selectedCycle,
  selectedTrackingCycle,
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

        <p v-if="calendarTimeReady" class="mt-3 text-xs text-gray-500">
          日期按账户时区 {{ calendarTimezone }} 计算
        </p>
        <p v-else role="status" class="mt-3 text-xs text-gray-500">
          {{ calendarTimeLoading ? '正在加载账户日期…' : calendarTimeError }}
          <button v-if="!calendarTimeLoading" class="ml-2 underline" @click="reloadCalendarTime">
            重新加载
          </button>
        </p>
        <CycleRangePanel
          v-if="calendarTimeReady"
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
        <div
          v-if="calendarTimeReady && selectedTrackingCycle"
          class="mt-4 w-full rounded-2xl bg-slate-50 p-4 text-xs space-y-2"
        >
          <p class="font-semibold">核对开始日 {{ selectedTrackingCycle.start_date }} 的记录</p>
          <p class="text-gray-500">
            确认用于记录质量与离线研究，不会自动补造日期或修改线上预测。选“漏记”后请按实际日期补录。
          </p>
          <p v-if="selectedTrackingCycle.tracking_kind" class="text-gray-500">
            最近核对：{{
              {
                unknown: '不确定',
                missed_tracking: '有漏记',
                true_long_interval: '真实间隔',
                no_onset: '截至确认日尚未开始下次经期',
              }[selectedTrackingCycle.tracking_kind]
            }}（{{ selectedTrackingCycle.tracking_as_of_date }}）
          </p>
          <div class="flex flex-wrap gap-2">
            <template v-if="selectedTrackingCycle.cycle_length != null">
              <button
                :disabled="trackingSaving || isSelectedFuture"
                class="border rounded-lg p-2"
                @click="confirmTracking('missed_tracking')"
              >
                我漏记了开始日
              </button>
              <button
                :disabled="trackingSaving || isSelectedFuture"
                class="border rounded-lg p-2"
                @click="confirmTracking('true_long_interval')"
              >
                确认是真实间隔
              </button>
              <button
                :disabled="trackingSaving || isSelectedFuture"
                class="border rounded-lg p-2"
                @click="confirmTracking('unknown')"
              >
                暂不确定
              </button>
            </template>
            <button
              v-else
              :disabled="trackingSaving || isSelectedFuture"
              class="border rounded-lg p-2"
              @click="confirmTracking('no_onset')"
            >
              截至所选日期，尚未开始下次经期
            </button>
          </div>
        </div>
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
    <ul
      v-if="aiHealthAdvices.length"
      aria-label="记录提示"
      class="rounded-xl bg-blue-50 p-4 text-xs text-blue-800 space-y-2"
    >
      <li v-for="advice in aiHealthAdvices" :key="advice">{{ advice }}</li>
    </ul>
    <div
      v-if="errorMsg"
      class="p-3 bg-red-50 text-red-600 rounded-xl text-xs font-medium text-center"
    >
      {{ errorMsg }}
    </div>
  </div>
</template>
