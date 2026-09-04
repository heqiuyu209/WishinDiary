<script setup lang="ts">
defineProps<{ daysUntil: number }>();
</script>

<template>
  <span
    class="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-rose-50/55 border border-rose-100/70 text-rose-600 text-[11px] font-bold backdrop-blur-sm transition-all duration-300"
  >
    <span class="relative flex h-2 w-2">
      <span
        class="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"
      ></span>
      <span class="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
    </span>
    {{ daysUntil <= 0 ? '经期即将到来' : `距预测经期 ${daysUntil} 天` }}
  </span>
</template>
