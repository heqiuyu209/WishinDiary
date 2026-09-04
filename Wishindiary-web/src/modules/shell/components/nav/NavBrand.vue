<script setup lang="ts">
defineProps<{ compact?: boolean }>();
const emit = defineEmits<{ select: [] }>();
</script>

<template>
  <button type="button" class="flex items-center gap-2 shrink-0" @click="emit('select')">
    <span
      class="flex h-9 w-9 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-100 to-pink-100 text-lg shadow-inner transition-all duration-300"
      :class="compact ? 'h-8 w-8 text-base' : ''"
    >
      🌸
    </span>
    <span
      class="hidden sm:block text-left leading-tight overflow-hidden transition-all duration-300"
      :class="compact ? 'max-w-0 opacity-0 -translate-y-1' : 'max-w-40 opacity-100 translate-y-0'"
    >
      <span
        class="block text-sm font-extrabold tracking-tight bg-gradient-to-r from-rose-500 to-pink-500 bg-clip-text text-transparent"
      >
        WishinDiary
      </span>
      <span class="block text-[10px] font-medium text-gray-400">个性化健康记录</span>
    </span>
  </button>
</template>
