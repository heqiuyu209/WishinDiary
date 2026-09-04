<script setup lang="ts">
const emit = defineEmits<{ logout: [] }>();
</script>

<template>
  <button
    type="button"
    @click="emit('logout')"
    class="flex items-center justify-center h-9 w-9 rounded-full text-gray-400 hover:text-rose-500 hover:bg-rose-50 transition-all duration-300"
    title="退出登录"
  >
    <svg
      xmlns="http://www.w3.org/2000/svg"
      class="h-4.5 w-4.5"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      stroke-width="2"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-7.5A2.25 2.25 0 003 5.25v13.5A2.25 2.25 0 005.25 21h7.5A2.25 2.25 0 0015.75 18.75V15M9 12h12m0 0l-3-3m3 3l-3 3"
      />
    </svg>
  </button>
</template>
