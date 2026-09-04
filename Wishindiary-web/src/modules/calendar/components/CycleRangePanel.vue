<script setup lang="ts">
defineProps<{
  selectedDateText: string;
  isSelectedFuture: boolean;
  canConfirmEnd: boolean;
  hasSelectedClosedCycle: boolean;
  hasOpenCycle: boolean;
  previewMode: 'none' | 'default' | 'custom';
  rangeText: string;
  estimatedBleedingDays: number;
  showClear: boolean;
  hasOpenCycleHint: boolean;
}>();
const emit = defineEmits<{
  markStart: [];
  markEnd: [];
  clear: [];
}>();
</script>

<template>
  <div class="w-full mt-6 space-y-3">
    <div
      class="bg-gray-50 p-3 rounded-2xl flex justify-between items-center border border-gray-100/50"
    >
      <span class="text-xs font-medium text-gray-500">当前选中日期</span>
      <span class="text-sm font-bold text-gray-800">{{ selectedDateText }}</span>
    </div>
    <div
      v-if="hasSelectedClosedCycle"
      class="bg-rose-50 p-3 rounded-2xl border border-rose-100 text-rose-700"
    >
      <div class="flex items-center justify-between gap-3">
        <span class="text-xs font-medium">当前选中区间</span>
        <span
          class="text-[11px] font-semibold bg-white px-2 py-0.5 rounded-full border border-rose-100"
        >
          可清空
        </span>
      </div>
      <p class="mt-1 text-sm font-bold">{{ rangeText }}</p>
    </div>
    <div
      v-else-if="hasOpenCycle"
      class="bg-amber-50 p-3 rounded-2xl border border-amber-100 text-amber-700"
    >
      <div class="flex items-center justify-between gap-3">
        <span class="text-xs font-medium">
          {{ previewMode === 'custom' ? '正在预览区间' : '系统预估区间' }}
        </span>
        <span
          class="text-[11px] font-semibold bg-white px-2 py-0.5 rounded-full border border-amber-100"
        >
          {{ previewMode === 'custom' ? '待确认结束' : `历史平均 ${estimatedBleedingDays} 天` }}
        </span>
      </div>
      <p class="mt-1 text-sm font-bold">{{ rangeText }}</p>
    </div>
    <div v-else class="bg-gray-50 p-3 rounded-2xl border border-gray-100 text-gray-600 text-xs">
      先在日历上选择开始日期，再点“标记开始”；之后只需点结束日期并确认，不需要手工输入。
    </div>
    <div class="flex flex-col sm:flex-row gap-3">
      <button
        :disabled="isSelectedFuture"
        @click="emit('markStart')"
        class="flex-1 bg-gray-800 hover:bg-gray-900 disabled:bg-gray-300 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-2xl text-xs transition-all active:scale-[0.98]"
      >
        标记开始
      </button>
      <button
        @click="emit('markEnd')"
        :disabled="!canConfirmEnd || isSelectedFuture"
        class="flex-1 bg-white border border-gray-200 hover:bg-gray-50 disabled:bg-gray-100 disabled:text-gray-400 disabled:border-gray-100 text-gray-700 font-semibold py-3 rounded-2xl text-xs transition-all active:scale-[0.98]"
      >
        标记结束
      </button>
      <button
        v-if="showClear"
        @click="emit('clear')"
        class="flex-1 bg-rose-50 border border-rose-100 hover:bg-rose-100 text-rose-600 font-semibold py-3 rounded-2xl text-xs transition-all active:scale-[0.98]"
      >
        清空选中区间
      </button>
    </div>
    <p v-if="hasOpenCycleHint" class="text-[11px] text-gray-400">
      已选开始日期后，点击日历上后续日期即可连续预览区间，再用“标记结束”保存。
    </p>
  </div>
</template>
