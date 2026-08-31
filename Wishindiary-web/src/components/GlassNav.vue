<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '../stores/authStore';
import { getPredictionApi } from '../api/cycleApi';
import { logoutApi } from '../api/authApi';

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();

const currentViewName = computed(() => route.name);
const profileOpen = ref(false);
const profileButtonRef = ref(null);
const profileMenuRef = ref(null);
const navShellRef = ref(null);

const navItems = [
  { name: 'Calendar', label: '打卡与预测', icon: '📍' },
  { name: 'Dashboard', label: '数据看板', icon: '📊' },
  { name: 'Report', label: '深度报告', icon: '📑' },
];

// 玻璃态滚动状态：0=顶部，1=滚动后
const scrollY = ref(0);
let scrollRafId = 0;
let navResizeObserver = null;
const navHeightVarName = '--glass-nav-height';

const onScroll = () => {
  if (scrollRafId) return;
  scrollRafId = window.requestAnimationFrame(() => {
    scrollY.value = window.scrollY || 0;
    scrollRafId = 0;
  });
};

const scrollProgress = computed(() => {
  const progress = (scrollY.value - 8) / 120;
  return Math.min(1, Math.max(0, progress));
});

const isCompactNav = computed(() => scrollProgress.value > 0.18);

const navSurfaceMetrics = computed(() => {
  const progress = scrollProgress.value;
  // 顶部保持通透，滚动后增加磨砂不透明度；这样缩小导航时仍有玻璃层次。
  const alpha = 0.24 + progress * 0.46;
  const paddingY = 16 - progress * 5;
  const blur = 24 + progress * 12;
  const saturate = 155 + progress * 45;
  const radius = 40 - progress * 12;

  return {
    backgroundColor: `rgba(255, 255, 255, ${alpha})`,
    backgroundImage: `linear-gradient(180deg, rgba(255,255,255,${Math.min(0.94, alpha + 0.16)}) 0%, rgba(255,255,255,${Math.max(0.08, alpha - 0.12)}) 100%)`,
    borderColor: `rgba(255, 255, 255, ${0.72 - progress * 0.28})`,
    boxShadow: progress > 0.25
      ? '0 14px 32px -22px rgba(15, 23, 42, 0.18)'
      : '0 26px 70px -28px rgba(244, 63, 94, 0.18)',
    paddingTop: `${paddingY}px`,
    paddingBottom: `${paddingY}px`,
    borderRadius: `${radius}px`,
    backdropFilter: `blur(${blur}px) saturate(${saturate}%)`,
    WebkitBackdropFilter: `blur(${blur}px) saturate(${saturate}%)`,
  };
});

const syncNavHeight = () => {
  const element = navShellRef.value;
  if (!element) return;

  const nextHeight = Math.ceil(element.getBoundingClientRect().height);
  if (!nextHeight) return;

  const rootStyle = document.documentElement.style;
  const currentHeight = Number.parseFloat(rootStyle.getPropertyValue(navHeightVarName)) || 0;
  if (Math.abs(nextHeight - currentHeight) > 1) {
    rootStyle.setProperty(navHeightVarName, `${nextHeight}px`);
  }
};

const profileInitial = computed(() => {
  const name = authStore.currentUsername?.trim();
  if (!name) return 'W';
  return name.slice(0, 1).toUpperCase();
});

const profileEmail = computed(() => authStore.currentEmail || '邮箱注册待开放');

const toggleProfileMenu = () => {
  profileOpen.value = !profileOpen.value;
};

const closeProfileMenu = () => {
  profileOpen.value = false;
};

const handleDocumentPointerDown = (event) => {
  const target = event.target;
  if (profileButtonRef.value?.contains(target) || profileMenuRef.value?.contains(target)) {
    return;
  }
  closeProfileMenu();
};

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true });
  document.addEventListener('pointerdown', handleDocumentPointerDown);
  onScroll();
  syncNavHeight();

  if (typeof ResizeObserver !== 'undefined' && navShellRef.value) {
    navResizeObserver = new ResizeObserver(() => {
      syncNavHeight();
    });
    navResizeObserver.observe(navShellRef.value);
  } else {
    window.addEventListener('resize', syncNavHeight, { passive: true });
  }
});
onUnmounted(() => {
  window.removeEventListener('scroll', onScroll);
  document.removeEventListener('pointerdown', handleDocumentPointerDown);
  window.removeEventListener('resize', syncNavHeight);
  if (navResizeObserver) {
    navResizeObserver.disconnect();
    navResizeObserver = null;
  }
  if (scrollRafId) {
    window.cancelAnimationFrame(scrollRafId);
    scrollRafId = 0;
  }
});

// 周期状态胶囊：距预测经期还有几天
const prediction = ref(null);
const daysUntil = ref(null);
const fetchPrediction = async () => {
  try {
    const res = await getPredictionApi();
    if (res.data.status === 'success' && res.data.prediction) {
      prediction.value = res.data.prediction;
      const next = new Date(`${res.data.prediction.next_period_start}T00:00:00`);
      const now = new Date();
      now.setHours(0, 0, 0, 0);
      const diff = Math.round((next - now) / 86400000);
      daysUntil.value = diff;
    }
  } catch {
    prediction.value = null;
    daysUntil.value = null;
  }
};
onMounted(fetchPrediction);

const handleLogout = async () => {
  closeProfileMenu();
  try { await logoutApi(); } catch { /* local logout still proceeds */ }
  authStore.logout();
  router.push('/login');
};

const navigateTo = (name) => router.push({ name });
</script>

<template>
  <div class="fixed inset-x-0 top-0 z-50 pointer-events-none px-2 sm:px-3 lg:px-4 pt-2 sm:pt-3">
    <nav
      ref="navShellRef"
      class="pointer-events-auto mx-auto flex w-full max-w-7xl items-center justify-between gap-2 sm:gap-4 border transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)] will-change-[transform,background-color,box-shadow,padding,border-radius,backdrop-filter]"
      :style="navSurfaceMetrics"
    >
      <div class="flex flex-col gap-2 md:hidden px-3 py-3">
        <div class="flex items-center justify-between gap-2">
          <button class="flex items-center gap-2 shrink-0" @click="navigateTo('Calendar')">
            <span class="flex h-9 w-9 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-100 to-pink-100 text-lg shadow-inner transition-all duration-300" :class="isCompactNav ? 'h-8 w-8 text-base' : ''">🌸</span>
            <span
              class="hidden sm:block text-left leading-tight overflow-hidden transition-all duration-300"
              :class="isCompactNav ? 'max-w-0 opacity-0 -translate-y-1' : 'max-w-40 opacity-100 translate-y-0'"
            >
              <span class="block text-sm font-extrabold tracking-tight bg-gradient-to-r from-rose-500 to-pink-500 bg-clip-text text-transparent">WishinDiary</span>
              <span class="block text-[10px] font-medium text-gray-400">个性化健康记录</span>
            </span>
          </button>

          <div class="flex items-center gap-1.5 shrink-0">
            <span
              v-if="daysUntil !== null"
              class="hidden sm:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-rose-50/55 border border-rose-100/70 text-rose-600 text-[11px] font-bold backdrop-blur-sm transition-all duration-300"
            >
              <span class="relative flex h-2 w-2">
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                <span class="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
              </span>
              {{ daysUntil <= 0 ? '经期即将到来' : `距预测经期 ${daysUntil} 天` }}
            </span>

            <div class="relative" ref="profileButtonRef">
              <button
                @click.stop="toggleProfileMenu"
                class="flex items-center gap-2 rounded-full border border-white/55 bg-white/45 px-2.5 py-1.5 text-left shadow-sm transition-all duration-300 hover:bg-white/70 hover:shadow-md"
                title="个人资料"
              >
                <span class="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-rose-500 to-pink-500 text-[11px] font-black text-white shadow-sm transition-all duration-300" :class="isCompactNav ? 'h-[26px] w-[26px] text-[10px]' : ''">
                  {{ profileInitial }}
                </span>
                <span class="hidden sm:block pr-1 transition-all duration-300" :class="isCompactNav ? 'opacity-0 -translate-y-1 max-w-0 overflow-hidden' : 'opacity-100 translate-y-0 max-w-28'">
                  <span class="block max-w-24 truncate text-xs font-bold text-gray-800">{{ authStore.currentUsername || '个人资料' }}</span>
                  <span class="block max-w-24 truncate text-[10px] text-gray-400">{{ profileEmail }}</span>
                </span>
                <svg xmlns="http://www.w3.org/2000/svg" class="hidden sm:block h-3.5 w-3.5 text-gray-400 transition-transform duration-300" :class="profileOpen ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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
                    <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-500 to-pink-500 text-sm font-black text-white shadow-md">
                      {{ profileInitial }}
                    </span>
                    <div class="min-w-0">
                      <p class="text-sm font-extrabold text-gray-800 truncate">{{ authStore.currentUsername || '未命名账户' }}</p>
                      <p class="text-[11px] text-gray-400 truncate">{{ profileEmail }}</p>
                    </div>
                  </div>

                  <div class="mt-4 space-y-2">
                    <div class="flex items-center justify-between rounded-2xl bg-rose-50/70 px-3 py-2.5">
                      <span class="text-[11px] font-bold text-gray-500">用户名</span>
                      <span class="text-[11px] font-semibold text-gray-800">{{ authStore.currentUsername || '未设置' }}</span>
                    </div>
                    <div class="flex items-center justify-between rounded-2xl bg-white/80 px-3 py-2.5 border border-gray-100">
                      <span class="text-[11px] font-bold text-gray-500">邮箱账号</span>
                      <span class="text-[11px] font-semibold text-gray-400">即将开放</span>
                    </div>
                    <div class="flex items-center justify-between rounded-2xl bg-white/80 px-3 py-2.5 border border-gray-100">
                      <span class="text-[11px] font-bold text-gray-500">修改密码</span>
                      <span class="text-[11px] font-semibold text-gray-400">即将开放</span>
                    </div>
                  </div>

                  <div class="mt-4 rounded-2xl border border-rose-100 bg-rose-50/80 px-3 py-2 text-[11px] leading-relaxed text-rose-700">
                    后续会支持邮箱注册、找回密码和修改密码，个人资料入口先预留在这里。
                  </div>
                </div>
              </transition>
            </div>

            <button
              @click="handleLogout"
              class="flex items-center justify-center h-9 w-9 rounded-full text-gray-400 hover:text-rose-500 hover:bg-rose-50 transition-all duration-300"
              title="退出登录"
            >
              <svg xmlns="http://www.w3.org/2000/svg" class="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-7.5A2.25 2.25 0 003 5.25v13.5A2.25 2.25 0 005.25 21h7.5A2.25 2.25 0 0015.75 18.75V15M9 12h12m0 0l-3-3m3 3l-3 3" />
              </svg>
            </button>
          </div>
        </div>

        <div class="grid grid-cols-3 gap-1.5 rounded-[24px] border border-white/55 bg-white/24 p-1.5 shadow-[0_8px_25px_-18px_rgba(15,23,42,0.2)] backdrop-blur-sm">
          <button
            v-for="item in navItems"
            :key="item.name"
            @click="navigateTo(item.name)"
            :class="currentViewName === item.name
              ? 'bg-white text-gray-800 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'"
            class="flex min-h-12 flex-col items-center justify-center gap-1 rounded-[18px] px-2 py-2 text-[11px] font-bold transition-all duration-300"
          >
            <span class="text-sm">{{ item.icon }}</span>
            <span class="hidden sm:block leading-none">{{ item.label }}</span>
          </button>
        </div>
      </div>

      <div class="hidden md:flex w-full items-center justify-between gap-2 sm:gap-4 px-3 sm:px-4 lg:px-6 transition-all duration-300 ease-[cubic-bezier(0.16,1,0.3,1)]">
        <!-- Logo + 用户名 -->
        <button class="flex items-center gap-2 shrink-0" @click="navigateTo('Calendar')">
          <span class="flex h-9 w-9 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-100 to-pink-100 text-lg shadow-inner transition-all duration-300" :class="isCompactNav ? 'h-8 w-8 text-base' : ''">🌸</span>
          <span
            class="text-left leading-tight overflow-hidden transition-all duration-300"
            :class="isCompactNav ? 'max-w-0 opacity-0 -translate-y-1' : 'max-w-40 opacity-100 translate-y-0'"
          >
            <span class="block text-sm font-extrabold tracking-tight bg-gradient-to-r from-rose-500 to-pink-500 bg-clip-text text-transparent">WishinDiary</span>
            <span class="block text-[10px] font-medium text-gray-400">个性化健康记录</span>
          </span>
        </button>

        <!-- 导航项 -->
        <div class="flex bg-white/32 backdrop-blur-sm rounded-full p-1 border border-white/50 shadow-[0_8px_25px_-18px_rgba(15,23,42,0.2)] transition-all duration-300">
          <button
            v-for="item in navItems"
            :key="item.name"
            @click="navigateTo(item.name)"
            :class="currentViewName === item.name
              ? 'bg-white text-gray-800 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'"
            class="flex items-center gap-1.5 px-2.5 sm:px-4 py-2 rounded-full text-xs font-bold transition-all duration-300"
          >
            <span class="text-sm">{{ item.icon }}</span>
            <span class="hidden lg:inline">{{ item.label }}</span>
          </button>
        </div>

        <!-- 右侧：周期状态胶囊 + 退出 -->
        <div class="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <span
            v-if="daysUntil !== null && !isCompactNav"
            class="hidden xl:inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-rose-50/55 border border-rose-100/70 text-rose-600 text-[11px] font-bold backdrop-blur-sm transition-all duration-300"
          >
            <span class="relative flex h-2 w-2">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-2 w-2 bg-rose-500"></span>
            </span>
            {{ daysUntil <= 0 ? '经期即将到来' : `距预测经期 ${daysUntil} 天` }}
          </span>

          <div class="relative" ref="profileButtonRef">
            <button
              @click.stop="toggleProfileMenu"
              class="flex items-center gap-2 rounded-full border border-white/55 bg-white/45 px-2.5 py-1.5 text-left shadow-sm transition-all duration-300 hover:bg-white/70 hover:shadow-md"
              title="个人资料"
            >
              <span class="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-br from-rose-500 to-pink-500 text-[11px] font-black text-white shadow-sm transition-all duration-300" :class="isCompactNav ? 'h-[26px] w-[26px] text-[10px]' : ''">
                {{ profileInitial }}
              </span>
              <span class="pr-1 transition-all duration-300" :class="isCompactNav ? 'opacity-0 -translate-y-1 max-w-0 overflow-hidden' : 'opacity-100 translate-y-0 max-w-28'">
                <span class="block max-w-24 truncate text-xs font-bold text-gray-800">{{ authStore.currentUsername || '个人资料' }}</span>
                <span class="block max-w-24 truncate text-[10px] text-gray-400">{{ profileEmail }}</span>
              </span>
              <svg xmlns="http://www.w3.org/2000/svg" class="hidden sm:block h-3.5 w-3.5 text-gray-400 transition-transform duration-300" :class="profileOpen ? 'rotate-180' : ''" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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
                  <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-rose-500 to-pink-500 text-sm font-black text-white shadow-md">
                    {{ profileInitial }}
                  </span>
                  <div class="min-w-0">
                    <p class="text-sm font-extrabold text-gray-800 truncate">{{ authStore.currentUsername || '未命名账户' }}</p>
                    <p class="text-[11px] text-gray-400 truncate">{{ profileEmail }}</p>
                  </div>
                </div>

                <div class="mt-4 space-y-2">
                  <div class="flex items-center justify-between rounded-2xl bg-rose-50/70 px-3 py-2.5">
                    <span class="text-[11px] font-bold text-gray-500">用户名</span>
                    <span class="text-[11px] font-semibold text-gray-800">{{ authStore.currentUsername || '未设置' }}</span>
                  </div>
                  <div class="flex items-center justify-between rounded-2xl bg-white/80 px-3 py-2.5 border border-gray-100">
                    <span class="text-[11px] font-bold text-gray-500">邮箱账号</span>
                    <span class="text-[11px] font-semibold text-gray-400">即将开放</span>
                  </div>
                  <div class="flex items-center justify-between rounded-2xl bg-white/80 px-3 py-2.5 border border-gray-100">
                    <span class="text-[11px] font-bold text-gray-500">修改密码</span>
                    <span class="text-[11px] font-semibold text-gray-400">即将开放</span>
                  </div>
                </div>

                <div class="mt-4 rounded-2xl border border-rose-100 bg-rose-50/80 px-3 py-2 text-[11px] leading-relaxed text-rose-700">
                  后续会支持邮箱注册、找回密码和修改密码，个人资料入口先预留在这里。
                </div>
              </div>
            </transition>
          </div>

          <button
            @click="handleLogout"
            class="flex items-center justify-center h-9 w-9 rounded-full text-gray-400 hover:text-rose-500 hover:bg-rose-50 transition-all duration-300"
            title="退出登录"
          >
            <svg xmlns="http://www.w3.org/2000/svg" class="h-4.5 w-4.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-7.5A2.25 2.25 0 003 5.25v13.5A2.25 2.25 0 005.25 21h7.5A2.25 2.25 0 0015.75 18.75V15M9 12h12m0 0l-3-3m3 3l-3 3" />
            </svg>
          </button>
        </div>
      </div>
    </nav>
  </div>
</template>
