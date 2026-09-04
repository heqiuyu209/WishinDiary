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
  message,
  errorMsg,
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
} = useCycleCalendar();
</script>

<template>
  <div class="space-y-6">
    <PredictionBanner :prediction="prediction" />

    <div class="grid grid-cols-1 md:grid-cols-12 gap-6">
      <div
        class="md:col-span-6 bg-white rounded-3xl shadow-[0_20px_60px_-15px_rgba(244,63,94,0.10)] border border-gray-100 p-6 flex flex-col items-center"
      >
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
          :has-open-cycle="!!openCycle"
          :preview-mode="selectedPreviewMode"
          :range-text="selectedRangeText"
          :estimated-bleeding-days="estimatedBleedingDays"
          :show-clear="!!selectedCycle"
          :has-open-cycle-hint="!!openCycle"
          @mark-start="markStart"
          @mark-end="markEnd"
          @clear="clearSelectedCycle"
        />
      </div>

      <div class="md:col-span-6">
        <DailyHealthForm v-model:form="dailyForm" :disabled="isSelectedFuture" @save="saveLog" />
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
