<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue';

defineProps<{ username: string; email: string; initial: string }>();

const profileOpen = ref(false);
const profileButtonRef = ref<HTMLElement | null>(null);
const profileMenuRef = ref<HTMLElement | null>(null);

const toggle = () => {
  profileOpen.value = !profileOpen.value;
};

const close = () => {
  profileOpen.value = false;
};

const handleDocumentPointerDown = (event: PointerEvent) => {
  const target = event.target as Node | null;
  if (profileButtonRef.value?.contains(target) || profileMenuRef.value?.contains(target)) {
    return;
  }
  close();
};

onMounted(() => {
  document.addEventListener('pointerdown', handleDocumentPointerDown);
});
onUnmounted(() => {
  document.removeEventListener('pointerdown', handleDocumentPointerDown);
});
</script>

<template>
  <div class="relative">
    <button
      type="button"
      @click.stop="toggle"
      class="flex items-center gap-2 rounded-full border border-white/55 bg-white/45 px-2.5 py-1.5 text-left shadow-sm transition-all duration-300 hover:bg-white/70 hover:shadow-md"
      title="个人资料"
    >
      <span
        class="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-rose-500 to-pink-500 text-[11px] font-black text-white shadow-sm transition-all duration-300"
      >
        {{ initial }}
      </span>
      <span class="hidden sm:block pr-1 transition-all duration-300">
        <span class="block max-w-24 truncate text-xs font-bold text-gray-800">
          {{ username || '个人资料' }}
        </span>
        <span class="block max-w-24 truncate text-[10px] text-gray-400">{{ email }}</span>
      </span>
      <svg
        xmlns="http://www.w3.org/2000/svg"
        class="hidden sm:block h-3.5 w-3.5 text-gray-400 transition-transform duration-300"
        :class="profileOpen ? 'rotate-180' : ''"
        fill="none"
        viewBox="0 0 24 24"
        stroke="currentColor"
        stroke-width="2"
      >
        <path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
      </svg>
    </button>

    <transition
      enter-active-class="transition duration-200 ease-out"
      enter-from-class="opacity-0 translate-y-2 scale-95"
      enter-to-class="opacity-100 translate-y-0 scale-100"
      leave-active-class="transition duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0 scale-100"
      leave-to-class="opacity-0 translate-y-2 scale-95"
    >
      <div
        v-if="profileOpen"
        ref="profileMenuRef"
        class="absolute right-0 top-full mt-3 w-[min(18rem,calc(100vw-1rem))] rounded-[28px] border border-white/70 bg-white/82 p-4 shadow-[0_20px_60px_-15px_rgba(244,63,94,0.18)] backdrop-blur-2xl backdrop-saturate-150"
      >
        <div class="flex items-center gap-3 border-b border-white/70 pb-4">
          <span
            class="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-500 to-pink-500 text-sm font-black text-white shadow-md"
          >
            {{ initial }}
          </span>
          <div class="min-w-0">
            <p class="text-sm font-extrabold text-gray-800 truncate">
              {{ username || '未命名账户' }}
            </p>
            <p class="text-[11px] text-gray-400 truncate">{{ email }}</p>
          </div>
        </div>

        <div class="mt-4 space-y-2">
          <div class="flex items-center justify-between rounded-2xl bg-rose-50/70 px-3 py-2.5">
            <span class="text-[11px] font-bold text-gray-500">用户名</span>
            <span class="text-[11px] font-semibold text-gray-800">{{ username || '未设置' }}</span>
          </div>
          <div
            class="flex items-center justify-between rounded-2xl bg-white/80 px-3 py-2.5 border border-gray-100"
          >
            <span class="text-[11px] font-bold text-gray-500">邮箱账号</span>
            <span class="text-[11px] font-semibold text-gray-400">即将开放</span>
          </div>
          <div
            class="flex items-center justify-between rounded-2xl bg-white/80 px-3 py-2.5 border border-gray-100"
          >
            <span class="text-[11px] font-bold text-gray-500">修改密码</span>
            <span class="text-[11px] font-semibold text-gray-400">即将开放</span>
          </div>
        </div>

        <div
          class="mt-4 rounded-2xl border border-rose-100 bg-rose-50/80 px-3 py-2 text-[11px] leading-relaxed text-rose-700"
        >
          后续会支持邮箱注册、找回密码和修改密码，个人资料入口先预留在这里。
        </div>
      </div>
    </transition>
  </div>
</template>
